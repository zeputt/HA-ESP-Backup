# ESPHome Backup 0.2.0

## Källa
Appen läser `/config/esphome` genom Home Assistants `homeassistant_config`-mount i read-only-läge.

## Destination
`destination` måste ligga under `/share`, `/media` eller `/backup`.

Standard:

```yaml
destination: /share/esphome-backup
schedule: "03:30"
run_on_start: true
create_archive: true
create_bundles: false
include_secrets: true
keep_daily: 14
keep_weekly: 8
keep_monthly: 12
git_enabled: true
git_remote: ""
git_branch: main
git_push: false
```

För Synology rekommenderas att en nätverkslagring monteras i Home Assistant och att appens destination pekar på den mount som exponeras under `/share`, `/media` eller `/backup`.

## Resultat

```text
<destination>/
├── latest/
│   ├── *.yaml
│   ├── manifest.json
│   ├── bundles/        # om aktiverat
│   └── .git/           # om Git aktiverat
└── archive/
    └── esphome-YYYYMMDD-HHMMSS.tar.zst
```

## Statussensorer
- `sensor.esphome_backup_status`
- `sensor.esphome_backup_last_run`
- `sensor.esphome_backup_next_run`
- `sensor.esphome_backup_devices`
- `sensor.esphome_backup_size`

## Säkerhet
Om `include_secrets: true` används kommer `secrets.yaml` att finnas i backupen. Destinationen ska därför behandlas som känslig backupdata.
