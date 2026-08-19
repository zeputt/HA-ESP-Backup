# ESPHome Backup 0.2.2

## Källa
Appen läser `/config/esphome` via `/ha_config/esphome` read-only. Originalkonfigurationen skrivs aldrig till.

## Destination
`destination` måste ligga under `/share`, `/media` eller `/backup`. För en Synology-share rekommenderas `/share/<mountnamn>/esphome-backup`.

## Struktur

```text
<destination>/
├── latest/
│   ├── config/          # verifierad spegel av /config/esphome
│   └── bundles/         # valfria ESPHome bundles
├── archive/             # versionerade .tar.zst
├── git/
│   └── repo/            # separat Git-repository
└── manifest.json        # status per komponent
```

## v0.2.2
- `latest/config` är nu en ren rsync-spegel. `--delete` kan därför inte radera manifest, bundles eller Git metadata.
- Bundles byggs från en temporär skrivbar arbetskopia. Det gör att ESPHome får skapa `.esphome` cache för exempelvis fonter, ljud och externa filer utan skrivaccess till originalet.
- Git ligger i ett separat repository under `git/repo` och initieras före `git config`.
- Git-, bundle- och arkivfel gör inte en verifierad filbackup falskt misslyckad. Status blir `ok_with_warnings`.
- `manifest.json` innehåller status för files, bundles, git och archive.
- Scheduler-fixen från 0.2.1 kvarstår.

## Säkerhet
Om `include_secrets: true` används kommer `secrets.yaml` att finnas i `latest/config`, arkiv och det lokala Git-repot. Aktivera inte `git_push` till ett externt repo utan att du avsiktligt accepterar detta.
