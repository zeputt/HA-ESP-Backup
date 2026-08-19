# ESPHome Backup 0.2.3

## Källa
Appen läser `/config/esphome` via `/ha_config/esphome` read-only. Originalkonfigurationen skrivs aldrig till.

## Destination
`destination` måste ligga under `/share`, `/media` eller `/backup`. För en Synology-share rekommenderas `/share/<mountnamn>/esphome-backup`.

## Struktur på backupdestinationen

```text
<destination>/
├── latest/
│   ├── config/                 # verifierad spegel av /config/esphome
│   └── bundles/                # valfria ESPHome bundles
├── archive/                    # versionerade .tar.zst
├── git/
│   ├── esphome-config.bundle   # komplett portabel Git-historik
│   └── git-status.json         # commit, antal commits och verifieringsstatus
└── manifest.json               # status per komponent
```

Det aktiva Git-repot ligger **inte** på nätverkslagringen. Det ligger persistent i appens privata lagring:

```text
/data/git/repo/
└── .git/
```

Efter varje backup skapas och verifieras `esphome-config.bundle`, som sedan kopieras atomärt till backupdestinationen. Detta undviker Git-metadata på SMB/NFS samtidigt som hela versionshistoriken finns off-host på Synologyn.

## Återställ Git-historik

```bash
git clone esphome-config.bundle esphome-restored
```

Bundlen innehåller HEAD och alla refs så en normal `git clone` checkar ut aktuell branch direkt.

## v0.2.3
- Aktivt Git-repository flyttat till persistent `/data/git/repo`.
- Nätverkslagringen innehåller inte längre ett aktivt `.git`-repo.
- Efter varje Git-commit skapas en komplett `esphome-config.bundle`.
- Bundlen verifieras lokalt och därefter igen från den faktiska backupdestinationen.
- `git-status.json` innehåller branch, HEAD, commit count, bundle size och verifieringsstatus.
- Git bundle skapas med alla refs/HEAD och kan klonas direkt.
- Git-fel fortsätter att degradera resultatet till `ok_with_warnings`; verifierad kärnbackup påverkas inte.

## Säkerhet
Om `include_secrets: true` används kommer `secrets.yaml` att versionshanteras i det lokala Git-repot och finnas i Git-bundlen. Aktivera inte `git_push` till ett externt repo utan att du avsiktligt accepterar detta.

## Uppgradering från 0.2.2
En eventuell gammal `<destination>/git/repo` från 0.2.2 används inte längre. Den kan tas bort manuellt efter att 0.2.3 har genomfört en lyckad körning och `git/esphome-config.bundle` har verifierats.
