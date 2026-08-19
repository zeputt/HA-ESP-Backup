#!/usr/bin/env python3
import datetime as dt
import hashlib
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import time
from typing import Any

import requests

LOG = logging.getLogger("esphome-backup")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

OPTIONS = Path("/data/options.json")
SOURCE = Path("/ha_config/esphome")
SUPERVISOR = "http://supervisor/core/api"
TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")


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
    return subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=check)


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
    cmd = ["rsync", "-a", "--delete", *excludes, f"{source}/", f"{latest}/"]
    result = run(cmd)
    if result.stdout.strip():
        LOG.info(result.stdout.strip())


def make_bundles(source: Path, bundle_dir: Path, yamls: list[Path]) -> tuple[int, list[str]]:
    bundle_dir.mkdir(parents=True, exist_ok=True)
    ok = 0
    failures: list[str] = []
    for yaml in yamls:
        if yaml.name.startswith("secrets."):
            continue
        output = bundle_dir / f"{yaml.stem}.esphomebundle.tar.gz"
        try:
            cp = run(["/opt/venv/bin/esphome", "bundle", str(yaml), "-o", str(output)], cwd=source)
            ok += 1
            if cp.stdout.strip():
                LOG.info("Bundle %s: %s", yaml.name, cp.stdout.strip().splitlines()[-1])
        except subprocess.CalledProcessError as exc:
            failures.append(yaml.name)
            LOG.warning("Bundle misslyckades för %s: %s", yaml.name, exc.stdout.strip())
    return ok, failures


def create_manifest(dest: Path, yamls: list[Path], bundles_ok: int, bundle_failures: list[str]) -> Path:
    manifest = {
        "created": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": "/config/esphome",
        "yaml_count": len([p for p in yamls if not p.name.startswith("secrets.")]),
        "files": [{"name": p.name, "sha256": sha256(p), "size": p.stat().st_size} for p in yamls],
        "bundles_created": bundles_ok,
        "bundle_failures": bundle_failures,
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


def git_commit(latest: Path, opts: dict[str, Any]) -> str:
    git_dir = latest / ".git"
    if not git_dir.exists():
        run(["git", "init", "-b", opts["git_branch"]], cwd=latest)
    run(["git", "config", "user.name", opts["git_user_name"]], cwd=latest)
    run(["git", "config", "user.email", opts["git_user_email"]], cwd=latest)
    run(["git", "add", "-A"], cwd=latest)
    status = run(["git", "status", "--porcelain"], cwd=latest).stdout.strip()
    if not status:
        return "unchanged"
    stamp = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    run(["git", "commit", "-m", f"ESPHome backup {stamp}"], cwd=latest)

    remote = str(opts.get("git_remote", "")).strip()
    if remote:
        existing = run(["git", "remote"], cwd=latest).stdout.split()
        if "origin" in existing:
            run(["git", "remote", "set-url", "origin", remote], cwd=latest)
        else:
            run(["git", "remote", "add", "origin", remote], cwd=latest)
        if opts.get("git_push"):
            run(["git", "push", "-u", "origin", opts["git_branch"]], cwd=latest)
    return "committed"


def backup_once(opts: dict[str, Any]) -> None:
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
    archives = destination / "archive"
    bundles = latest / "bundles"
    destination.mkdir(parents=True, exist_ok=True)

    yamls = collect_yaml(SOURCE, opts["include_secrets"])
    if not yamls:
        raise RuntimeError("Inga ESPHome YAML-filer hittades")

    sync_latest(SOURCE, latest, opts["include_secrets"])

    bundles_ok = 0
    bundle_failures: list[str] = []
    if opts.get("create_bundles"):
        bundles_ok, bundle_failures = make_bundles(SOURCE, bundles, yamls)

    create_manifest(latest, yamls, bundles_ok, bundle_failures)

    git_result = "disabled"
    if opts.get("git_enabled"):
        git_result = git_commit(latest, opts)

    archive_path = None
    removed = 0
    if opts.get("create_archive"):
        archive_path = make_archive(latest, archives)
        removed = prune_archives(archives, opts["keep_daily"], opts["keep_weekly"], opts["keep_monthly"])

    duration = (dt.datetime.now().astimezone() - started).total_seconds()
    device_count = len([p for p in yamls if not p.name.startswith("secrets.")])
    total_size = sum(p.stat().st_size for p in yamls)

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
    publish_status("ok",
        last_run=started.isoformat(),
        destination=str(destination),
        devices=device_count,
        yaml_files=len(yamls),
        bundles_created=bundles_ok,
        bundle_failures=bundle_failures,
        archive=str(archive_path) if archive_path else "disabled",
        archives_pruned=removed,
        git=git_result,
        duration_seconds=round(duration, 2),
    )
    LOG.info("Backup klar: %s enheter, destination %s, %.1fs", device_count, destination, duration)


def seconds_until(schedule: str) -> int:
    hour, minute = map(int, schedule.split(":"))
    now = dt.datetime.now().astimezone()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += dt.timedelta(days=1)
    return max(1, int((target - now).total_seconds()))


def main() -> int:
    opts = load_options()
    LOG.info("ESPHome Backup 0.2.0 startar. Källa: %s, destination: %s", SOURCE, opts["destination"])

    if opts.get("run_on_start"):
        try:
            backup_once(opts)
        except Exception as exc:
            LOG.exception("Backup vid start misslyckades")
            publish_status("error", error=str(exc), last_failure=dt.datetime.now().astimezone().isoformat())

    while True:
        opts = load_options()
        wait = seconds_until(opts["schedule"])
        next_run = dt.datetime.now().astimezone() + dt.timedelta(seconds=wait)
        ha_state("sensor.esphome_backup_next_run", next_run.isoformat(), {
            "friendly_name": "ESPHome Backup Next Run",
            "device_class": "timestamp",
        })
        LOG.info("Nästa backup: %s", next_run.isoformat(timespec="minutes"))
        time.sleep(wait)
        opts = load_options()
        try:
            backup_once(opts)
        except Exception as exc:
            LOG.exception("Schemalagd backup misslyckades")
            publish_status("error", error=str(exc), last_failure=dt.datetime.now().astimezone().isoformat())


if __name__ == "__main__":
    sys.exit(main())
