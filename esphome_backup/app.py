#!/usr/bin/env python3
import datetime as dt
from collections import deque
import hashlib
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import tarfile
import tempfile
import time
from typing import Any

import requests

from web_ui import start_web_server

LOG = logging.getLogger("esphome-backup")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

OPTIONS = Path("/data/options.json")
SOURCE = Path("/ha_config/esphome")
SUPERVISOR = "http://supervisor/core/api"
TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
STATE_FILE = Path("/data/runtime-status.json")
BACKUP_LOCK = threading.Lock()
STATE_LOCK = threading.Lock()
LOG_BUFFER_LOCK = threading.Lock()
LOG_BUFFER: deque[dict[str, Any]] = deque(maxlen=600)
LOG_SEQUENCE = 0


class RuntimeLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        global LOG_SEQUENCE
        try:
            message = self.format(record)
            with LOG_BUFFER_LOCK:
                LOG_SEQUENCE += 1
                LOG_BUFFER.append({
                    "seq": LOG_SEQUENCE,
                    "time": dt.datetime.fromtimestamp(record.created).astimezone().isoformat(timespec="milliseconds"),
                    "level": record.levelname.lower(),
                    "message": message,
                })
        except Exception:
            pass


_runtime_handler = RuntimeLogHandler()
_runtime_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logging.getLogger().addHandler(_runtime_handler)


RUNTIME_STATE: dict[str, Any] = {
    "status": "starting",
    "version": "0.3.1",
    "running": False,
    "trigger": None,
    "last_run": None,
    "last_success": None,
    "last_failure": None,
    "next_run": None,
    "message": "ESPHome Backup startar",
    "warnings": [],
}


def save_runtime_state(**updates: Any) -> dict[str, Any]:
    with STATE_LOCK:
        RUNTIME_STATE.update(updates)
        snapshot = dict(RUNTIME_STATE)
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(snapshot, indent=2, default=str), encoding="utf-8")
        os.replace(tmp, STATE_FILE)
    except Exception as exc:
        LOG.debug("Kunde inte skriva runtime-status: %s", exc)
    return snapshot


def load_runtime_state() -> None:
    if not STATE_FILE.is_file():
        return
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            with STATE_LOCK:
                RUNTIME_STATE.update(data)
                RUNTIME_STATE["version"] = "0.3.1"
                RUNTIME_STATE["running"] = False
                if RUNTIME_STATE.get("status") == "running":
                    RUNTIME_STATE["status"] = "starting"
    except Exception as exc:
        LOG.debug("Kunde inte läsa runtime-status: %s", exc)


def runtime_snapshot() -> dict[str, Any]:
    with STATE_LOCK:
        state = dict(RUNTIME_STATE)
    try:
        opts = load_options()
    except Exception:
        opts = {}
    state["options"] = {
        "destination": opts.get("destination"),
        "destination_url": opts.get("destination_url", ""),
        "schedule": opts.get("schedule"),
        "create_archive": opts.get("create_archive"),
        "create_bundles": opts.get("create_bundles"),
        "include_secrets": opts.get("include_secrets"),
        "git_enabled": opts.get("git_enabled"),
        "git_push": opts.get("git_push"),
        "keep_daily": opts.get("keep_daily"),
        "keep_weekly": opts.get("keep_weekly"),
        "keep_monthly": opts.get("keep_monthly"),
    }
    destination = opts.get("destination")
    if destination:
        dest = Path(destination)
        for name, path in (("manifest", dest / "manifest.json"), ("git_status", dest / "git" / "git-status.json")):
            try:
                state[name] = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
            except Exception:
                state[name] = None
        try:
            archives = sorted((dest / "archive").glob("esphome-*.tar.zst"), key=lambda x: x.stat().st_mtime, reverse=True)
            state["archives"] = [
                {
                    "name": a.name,
                    "size": a.stat().st_size,
                    "modified": dt.datetime.fromtimestamp(a.stat().st_mtime).astimezone().isoformat(timespec="seconds"),
                }
                for a in archives[:8]
            ]
        except Exception:
            state["archives"] = []
    return state



def runtime_log_snapshot(after: int = 0, limit: int = 250) -> dict[str, Any]:
    with LOG_BUFFER_LOCK:
        lines = [dict(x) for x in LOG_BUFFER if int(x.get("seq", 0)) > after]
        current = LOG_SEQUENCE
    if len(lines) > limit:
        lines = lines[-limit:]
    return {"lines": lines, "last_seq": current}


def git_history_snapshot(limit: int = 40) -> dict[str, Any]:
    repo = Path("/data/git/repo")
    if not (repo / ".git").is_dir():
        return {"enabled": False, "commits": []}
    try:
        cp = run([
            "git", "log", f"-{max(1, min(limit, 100))}",
            "--date=iso-strict",
            "--pretty=format:%H%x1f%h%x1f%aI%x1f%an%x1f%s",
        ], cwd=repo)
        commits = []
        for line in cp.stdout.splitlines():
            parts = line.split("\x1f", 4)
            if len(parts) != 5:
                continue
            full, short, authored, author, subject = parts
            stat = run(["git", "show", "--shortstat", "--format=", full], cwd=repo, check=False).stdout.strip()
            commits.append({
                "commit": full, "short_commit": short, "date": authored,
                "author": author, "message": subject, "stat": stat,
            })
        return {"enabled": True, "commits": commits}
    except Exception as exc:
        LOG.warning("Kunde inte läsa Git-historik: %s", exc)
        return {"enabled": True, "commits": [], "error": str(exc)}


def load_options() -> dict[str, Any]:
    with OPTIONS.open("r", encoding="utf-8") as f:
        return json.load(f)


def ha_state(entity_id: str, state: Any, attrs: dict[str, Any] | None = None) -> None:
    if not TOKEN:
        LOG.warning("SUPERVISOR_TOKEN saknas; kan inte publicera HA-sensorer")
        return
    payload = {"state": str(state), "attributes": attrs or {}}
    try:
        r = requests.post(
            f"{SUPERVISOR}/states/{entity_id}",
            headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
            json=payload,
            timeout=10,
        )
        r.raise_for_status()
    except Exception as exc:
        LOG.warning("Kunde inte uppdatera %s: %s", entity_id, exc)


def publish_status(status: str, **extra: Any) -> None:
    common = {"friendly_name": "ESPHome Backup Status", **extra}
    ha_state("sensor.esphome_backup_status", status, common)


def run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    LOG.debug("Kör: %s", " ".join(cmd))
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=check,
        )
    except subprocess.CalledProcessError as exc:
        output = (exc.stdout or "").strip()
        LOG.error("Kommando misslyckades (exit %s): %s", exc.returncode, " ".join(cmd))
        if output:
            LOG.error("Kommando-output:\n%s", output)
        raise
    return result


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def collect_yaml(source: Path, include_secrets: bool) -> list[Path]:
    files: list[Path] = []
    for pattern in ("*.yaml", "*.yml"):
        files.extend(source.glob(pattern))
    files = sorted(set(files))
    if not include_secrets:
        files = [p for p in files if p.name not in {"secrets.yaml", "secrets.yml"}]
    return files


def sync_latest(source: Path, latest: Path, include_secrets: bool) -> None:
    latest.mkdir(parents=True, exist_ok=True)
    excludes = ["--exclude=.esphome/", "--exclude=.git/", "--exclude=*.bin", "--exclude=*.elf"]
    if not include_secrets:
        excludes += ["--exclude=secrets.yaml", "--exclude=secrets.yml"]

    # NAS/SMB-vänlig synk. Vi behöver innehåll, katalogstruktur och filtid, inte
    # Unix owner/group/permissions som ofta ger rsync exit 23 på nätverkslagring.
    cmd = [
        "rsync",
        "-rt",
        "--delete",
        "--no-perms",
        "--no-owner",
        "--no-group",
        "--omit-dir-times",
        "--itemize-changes",
        *excludes,
        f"{source}/",
        f"{latest}/",
    ]
    result = run(cmd)
    if result.stdout.strip():
        LOG.info("rsync:\n%s", result.stdout.strip())



def _excluded_from_backup(relative: Path, include_secrets: bool) -> bool:
    parts = relative.parts
    if ".esphome" in parts or ".git" in parts:
        return True
    if relative.suffix.lower() in {".bin", ".elf"}:
        return True
    if not include_secrets and relative.name in {"secrets.yaml", "secrets.yml"}:
        return True
    return False


def verify_latest(source: Path, latest: Path, include_secrets: bool) -> tuple[int, int]:
    """Verify that all regular source files copied to latest have identical content."""
    expected: dict[Path, Path] = {}
    for path in source.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(source)
        if _excluded_from_backup(rel, include_secrets):
            continue
        expected[rel] = path

    if not expected:
        raise RuntimeError("Inga filer hittades att verifiera efter backup")

    missing: list[str] = []
    mismatched: list[str] = []
    verified_bytes = 0

    for rel, src in expected.items():
        dst = latest / rel
        if not dst.is_file():
            missing.append(str(rel))
            continue
        if src.stat().st_size != dst.stat().st_size or sha256(src) != sha256(dst):
            mismatched.append(str(rel))
            continue
        verified_bytes += src.stat().st_size

    if missing or mismatched:
        details = []
        if missing:
            details.append("saknas: " + ", ".join(missing[:20]))
        if mismatched:
            details.append("avviker: " + ", ".join(mismatched[:20]))
        raise RuntimeError(
            f"Verifiering av destination misslyckades ({len(missing)} saknas, "
            f"{len(mismatched)} avviker): " + "; ".join(details)
        )

    LOG.info("Verifiering OK: %s filer, %s byte", len(expected), verified_bytes)
    return len(expected), verified_bytes

def prepare_bundle_workspace(source: Path, include_secrets: bool) -> Path:
    """Create a writable temporary copy of ESPHome config for bundle generation."""
    work_root = Path(tempfile.mkdtemp(prefix="esphome-backup-bundle-"))
    work = work_root / "esphome"
    excludes = ["--exclude=.esphome/", "--exclude=.git/", "--exclude=*.bin", "--exclude=*.elf"]
    if not include_secrets:
        excludes += ["--exclude=secrets.yaml", "--exclude=secrets.yml"]
    run([
        "rsync", "-rt", "--no-perms", "--no-owner", "--no-group", "--omit-dir-times",
        *excludes, f"{source}/", f"{work}/",
    ])
    return work


def make_bundles(source: Path, bundle_dir: Path, yamls: list[Path], include_secrets: bool) -> tuple[int, list[str]]:
    bundle_dir.mkdir(parents=True, exist_ok=True)
    ok = 0
    failures: list[str] = []
    work: Path | None = None
    try:
        work = prepare_bundle_workspace(source, include_secrets)
        for yaml in yamls:
            if yaml.name.startswith("secrets."):
                continue
            rel = yaml.relative_to(source)
            work_yaml = work / rel
            output = bundle_dir / f"{yaml.stem}.esphomebundle.tar.gz"
            try:
                cp = run(["/opt/venv/bin/esphome", "bundle", str(work_yaml), "-o", str(output)], cwd=work)
                ok += 1
                if cp.stdout.strip():
                    LOG.info("Bundle %s: %s", yaml.name, cp.stdout.strip().splitlines()[-1])
            except subprocess.CalledProcessError as exc:
                failures.append(yaml.name)
                tail = (exc.stdout or "").strip().splitlines()[-12:]
                LOG.warning("Bundle misslyckades för %s:\n%s", yaml.name, "\n".join(tail))
    finally:
        if work is not None:
            shutil.rmtree(work.parent, ignore_errors=True)
    return ok, failures

def create_manifest(dest: Path, yamls: list[Path], components: dict[str, Any]) -> Path:
    manifest = {
        "created": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": "/config/esphome",
        "yaml_count": len([p for p in yamls if not p.name.startswith("secrets.")]),
        "files": [{"name": p.name, "sha256": sha256(p), "size": p.stat().st_size} for p in yamls],
        "components": components,
    }
    path = dest / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path

def make_archive(latest: Path, archives: Path) -> Path:
    archives.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    tar_path = archives / f"esphome-{stamp}.tar"
    zst_path = archives / f"esphome-{stamp}.tar.zst"
    def archive_filter(info: tarfile.TarInfo):
        parts = Path(info.name).parts
        if ".git" in parts:
            return None
        return info

    with tarfile.open(tar_path, "w") as tf:
        tf.add(latest, arcname="esphome", filter=archive_filter)
    run(["zstd", "-q", "-T0", "-6", "-f", str(tar_path), "-o", str(zst_path)])
    tar_path.unlink(missing_ok=True)
    return zst_path


def archive_time(path: Path) -> dt.datetime | None:
    try:
        stamp = path.name.removeprefix("esphome-").removesuffix(".tar.zst")
        return dt.datetime.strptime(stamp, "%Y%m%d-%H%M%S")
    except ValueError:
        return None


def prune_archives(archives: Path, keep_daily: int, keep_weekly: int, keep_monthly: int) -> int:
    entries = [(p, archive_time(p)) for p in archives.glob("esphome-*.tar.zst")]
    entries = [(p, t) for p, t in entries if t is not None]
    entries.sort(key=lambda x: x[1], reverse=True)
    keep: set[Path] = set()

    def select_by_key(limit: int, keyfn):
        if limit <= 0:
            return
        seen = set()
        for p, t in entries:
            key = keyfn(t)
            if key in seen:
                continue
            keep.add(p)
            seen.add(key)
            if len(seen) >= limit:
                break

    select_by_key(keep_daily, lambda t: t.date())
    select_by_key(keep_weekly, lambda t: (t.isocalendar().year, t.isocalendar().week))
    select_by_key(keep_monthly, lambda t: (t.year, t.month))

    removed = 0
    for p, _ in entries:
        if p not in keep:
            p.unlink(missing_ok=True)
            removed += 1
    return removed


def _git_head(repo: Path) -> str:
    return run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()


def _git_commit_count(repo: Path) -> int:
    return int(run(["git", "rev-list", "--count", "HEAD"], cwd=repo).stdout.strip())


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def export_git_bundle(git_repo: Path, destination_git: Path, branch: str) -> dict[str, Any]:
    """Export the local persistent Git history as a portable bundle on backup storage."""
    destination_git.mkdir(parents=True, exist_ok=True)
    bundle_target = destination_git / "esphome-config.bundle"
    status_target = destination_git / "git-status.json"

    # Build the bundle on the app's local persistent filesystem first. This keeps
    # active Git metadata and temporary Git writes away from SMB/NFS entirely.
    local_bundle = git_repo.parent / "esphome-config.bundle.tmp"
    local_bundle.unlink(missing_ok=True)
    run(["git", "bundle", "create", str(local_bundle), "--all"], cwd=git_repo)
    run(["git", "bundle", "verify", str(local_bundle)], cwd=git_repo)

    # Copy to the network destination using a temporary name and then publish it.
    network_tmp = destination_git / ".esphome-config.bundle.tmp"
    shutil.copyfile(local_bundle, network_tmp)
    os.replace(network_tmp, bundle_target)
    local_bundle.unlink(missing_ok=True)

    # Verify the exact file that now resides on backup storage, not merely the
    # locally generated temporary bundle.
    verify = run(["git", "bundle", "verify", str(bundle_target)], cwd=git_repo)
    head = _git_head(git_repo)
    commits = _git_commit_count(git_repo)
    now = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    status = {
        "status": "ok",
        "branch": branch,
        "commit": head,
        "short_commit": head[:12],
        "commits": commits,
        "last_export": now,
        "bundle": str(bundle_target),
        "bundle_size": bundle_target.stat().st_size,
        "bundle_verified": True,
        "verify_output": (verify.stdout or "").strip(),
    }
    write_json_atomic(status_target, status)
    LOG.info(
        "Git bundle verifierad: %s commits, HEAD %s, %s byte",
        commits, head[:12], bundle_target.stat().st_size,
    )
    return status


def git_commit(config_source: Path, git_repo: Path, destination_git: Path, opts: dict[str, Any]) -> dict[str, Any]:
    """Version verified config locally under /data and export a portable bundle."""
    git_repo.mkdir(parents=True, exist_ok=True)
    git_dir = git_repo / ".git"
    branch = str(opts["git_branch"])

    if not git_dir.is_dir():
        run(["git", "init", "-b", branch], cwd=git_repo)

    run(["git", "config", "user.name", opts["git_user_name"]], cwd=git_repo)
    run(["git", "config", "user.email", opts["git_user_email"]], cwd=git_repo)

    # Mirror only the verified backup into the working tree. The active .git
    # directory stays on /data and is never placed on the Synology share.
    run([
        "rsync", "-rt", "--delete", "--no-perms", "--no-owner", "--no-group",
        "--omit-dir-times", "--exclude=.git/", f"{config_source}/", f"{git_repo}/",
    ])
    run(["git", "add", "-A"], cwd=git_repo)
    status = run(["git", "status", "--porcelain"], cwd=git_repo).stdout.strip()
    action = "unchanged"
    if status:
        stamp = dt.datetime.now().astimezone().isoformat(timespec="seconds")
        run(["git", "commit", "-m", f"ESPHome backup {stamp}"], cwd=git_repo)
        action = "committed"

    remote = str(opts.get("git_remote", "")).strip()
    pushed = False
    if remote:
        existing = run(["git", "remote"], cwd=git_repo).stdout.split()
        if "origin" in existing:
            run(["git", "remote", "set-url", "origin", remote], cwd=git_repo)
        else:
            run(["git", "remote", "add", "origin", remote], cwd=git_repo)
        if opts.get("git_push"):
            run(["git", "push", "-u", "origin", branch], cwd=git_repo)
            pushed = True

    bundle_status = export_git_bundle(git_repo, destination_git, branch)
    return {
        "action": action,
        "pushed": pushed,
        "repo": str(git_repo),
        **bundle_status,
    }

def backup_once(opts: dict[str, Any]) -> dict[str, Any]:
    started = dt.datetime.now().astimezone()
    publish_status("running", started=started.isoformat())

    if not SOURCE.is_dir():
        raise RuntimeError(f"ESPHome-katalogen finns inte: {SOURCE}")

    destination = Path(opts["destination"])
    allowed = ("/share/", "/media/", "/backup/")
    dest_s = str(destination.resolve()) + "/"
    if not any(dest_s.startswith(prefix) for prefix in allowed):
        raise RuntimeError("destination måste ligga under /share, /media eller /backup")

    latest = destination / "latest"
    latest_config = latest / "config"
    bundles = latest / "bundles"
    archives = destination / "archive"
    git_repo = Path("/data/git/repo")
    destination_git = destination / "git"
    destination.mkdir(parents=True, exist_ok=True)

    yamls = collect_yaml(SOURCE, opts["include_secrets"])
    if not yamls:
        raise RuntimeError("Inga ESPHome YAML-filer hittades")

    # Core backup. Any failure here is fatal.
    sync_latest(SOURCE, latest_config, opts["include_secrets"])
    verified_files, verified_bytes = verify_latest(SOURCE, latest_config, opts["include_secrets"])

    warnings: list[str] = []
    components: dict[str, Any] = {
        "files": {"status": "ok", "verified_files": verified_files, "verified_bytes": verified_bytes},
        "bundles": {"status": "disabled", "created": 0, "failures": []},
        "git": {"status": "disabled", "result": "disabled"},
        "archive": {"status": "disabled", "path": None, "pruned": 0},
    }

    bundles_ok = 0
    bundle_failures: list[str] = []
    if opts.get("create_bundles"):
        try:
            bundles_ok, bundle_failures = make_bundles(SOURCE, bundles, yamls, opts["include_secrets"])
            bstatus = "ok" if not bundle_failures else "warning"
            components["bundles"] = {"status": bstatus, "created": bundles_ok, "failures": bundle_failures}
            if bundle_failures:
                warnings.append(f"bundles misslyckades för {len(bundle_failures)} enhet(er)")
        except Exception as exc:
            LOG.exception("Bundle-steget misslyckades")
            components["bundles"] = {"status": "error", "created": bundles_ok, "failures": bundle_failures, "error": str(exc)}
            warnings.append(f"bundle-steget: {exc}")

    git_result: dict[str, Any] | str = "disabled"
    if opts.get("git_enabled"):
        try:
            git_result = git_commit(latest_config, git_repo, destination_git, opts)
            components["git"] = {"status": "ok", "result": git_result, "repo": str(git_repo), "bundle": str(destination_git / "esphome-config.bundle")}
        except Exception as exc:
            LOG.exception("Git-versionering misslyckades, men den verifierade filbackupen behålls")
            components["git"] = {"status": "error", "result": "failed", "error": str(exc), "repo": str(git_repo), "bundle": str(destination_git / "esphome-config.bundle")}
            warnings.append(f"git: {exc}")

    archive_path = None
    removed = 0
    if opts.get("create_archive"):
        try:
            archive_path = make_archive(latest, archives)
            removed = prune_archives(archives, opts["keep_daily"], opts["keep_weekly"], opts["keep_monthly"])
            components["archive"] = {"status": "ok", "path": str(archive_path), "pruned": removed}
        except Exception as exc:
            LOG.exception("Arkivering misslyckades, men den verifierade filbackupen behålls")
            components["archive"] = {"status": "error", "path": None, "pruned": removed, "error": str(exc)}
            warnings.append(f"archive: {exc}")

    manifest_path = create_manifest(destination, yamls, components)

    duration = (dt.datetime.now().astimezone() - started).total_seconds()
    device_count = len([p for p in yamls if not p.name.startswith("secrets.")])
    total_size = sum(p.stat().st_size for p in yamls)
    overall = "ok" if not warnings else "ok_with_warnings"

    ha_state("sensor.esphome_backup_last_run", started.isoformat(), {
        "friendly_name": "ESPHome Backup Last Run",
        "device_class": "timestamp",
    })
    ha_state("sensor.esphome_backup_devices", device_count, {
        "friendly_name": "ESPHome Backup Devices",
        "unit_of_measurement": "devices",
    })
    ha_state("sensor.esphome_backup_size", total_size, {
        "friendly_name": "ESPHome Backup Source Size",
        "unit_of_measurement": "B",
        "device_class": "data_size",
    })
    publish_status(overall,
        last_run=started.isoformat(),
        destination=str(destination),
        devices=device_count,
        yaml_files=len(yamls),
        verified_files=verified_files,
        verified_bytes=verified_bytes,
        bundles_created=bundles_ok,
        bundle_failures=bundle_failures,
        git=git_result,
        archive=str(archive_path) if archive_path else components["archive"]["status"],
        manifest=str(manifest_path),
        warnings=warnings,
        duration_seconds=round(duration, 2),
    )
    if warnings:
        LOG.warning(
            "Backup verifierad med varningar: %s enheter, %s filer, destination %s, %.1fs. %s",
            device_count, verified_files, destination, duration, "; ".join(warnings)
        )
    else:
        LOG.info(
            "Backup klar och verifierad: %s enheter, %s filer, destination %s, %.1fs",
            device_count, verified_files, destination, duration
        )

    return {
        "overall": overall,
        "warnings": warnings,
        "devices": device_count,
        "verified_files": verified_files,
        "verified_bytes": verified_bytes,
        "bundles_created": bundles_ok,
        "bundle_failures": bundle_failures,
        "duration_seconds": round(duration, 2),
        "destination": str(destination),
    }

def _run_backup_locked(trigger: str) -> bool:
    started = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    save_runtime_state(
        status="running", running=True, trigger=trigger, last_run=started,
        message=f"Backup startad ({trigger})", warnings=[], error=None,
    )
    try:
        result = backup_once(load_options())
        overall = result.get("overall", "ok")
        warnings = result.get("warnings", [])
        save_runtime_state(
            status=overall, running=False, trigger=trigger,
            last_success=dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            message="Backup klar och verifierad" if not warnings else "Backup verifierad med varningar",
            **result,
        )
        return True
    except Exception as exc:
        LOG.exception("%s backup misslyckades", trigger.capitalize())
        failure = dt.datetime.now().astimezone().isoformat(timespec="seconds")
        save_runtime_state(
            status="error", running=False, trigger=trigger, last_failure=failure,
            message=str(exc), error=str(exc),
        )
        publish_status("error", error=str(exc), last_failure=failure)
        return False
    finally:
        BACKUP_LOCK.release()


def run_backup_safe(trigger: str) -> bool:
    if not BACKUP_LOCK.acquire(blocking=False):
        LOG.warning("Backup begärd (%s), men en körning pågår redan", trigger)
        return False
    return _run_backup_locked(trigger)


def request_manual_backup() -> bool:
    # Reserve the backup slot before returning HTTP 202, avoiding a race where
    # two browser clicks could both be accepted before the worker grabs the lock.
    if not BACKUP_LOCK.acquire(blocking=False):
        return False
    threading.Thread(target=_run_backup_locked, args=("manual",), daemon=True, name="manual-backup").start()
    return True


def next_scheduled_run(schedule: str, now: dt.datetime | None = None) -> dt.datetime:
    hour, minute = map(int, schedule.split(":"))
    now = now or dt.datetime.now().astimezone()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += dt.timedelta(days=1)
    return target


def main() -> int:
    load_runtime_state()
    opts = load_options()
    LOG.info("ESPHome Backup 0.3.1 startar. Källa: %s, destination: %s", SOURCE, opts["destination"])
    start_web_server(runtime_snapshot, request_manual_backup, runtime_log_snapshot, git_history_snapshot, port=8099)

    if opts.get("run_on_start"):
        run_backup_safe("startup")

    while True:
        opts = load_options()
        now = dt.datetime.now().astimezone()
        next_run = next_scheduled_run(opts["schedule"], now)
        wait = max(1.0, (next_run - now).total_seconds())
        save_runtime_state(next_run=next_run.isoformat(timespec="seconds"))
        ha_state("sensor.esphome_backup_next_run", next_run.isoformat(), {
            "friendly_name": "ESPHome Backup Next Run",
            "device_class": "timestamp",
        })
        LOG.info("Nästa backup: %s", next_run.isoformat(timespec="minutes"))
        time.sleep(wait)
        run_backup_safe("scheduled")


if __name__ == "__main__":
    sys.exit(main())
