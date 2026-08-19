# ESPHome Backup

Home Assistant App för automatisk backup av ESPHome-konfigurationer från `/config/esphome`.

Funktioner:
- verifierad spegel under `latest/config`
- SHA-256-verifiering efter synk
- ESPHome bundles byggda i skrivbar temporär workspace
- komprimerade `.tar.zst`-arkiv med daily/weekly/monthly retention
- persistent lokalt Git-repository under `/data/git/repo`
- verifierad portabel Git bundle på backupdestinationen
- komponentbaserad status: `ok`, `ok_with_warnings` eller `error`
- status till Home Assistant via Core API
- destination under `/share`, `/media` eller `/backup`

## 0.2.3
Git arbetar nu endast mot appens persistenta lokala `/data`. Efter varje körning exporteras hela Git-historiken som `git/esphome-config.bundle` till Synology/NAS och verifieras därifrån. Det eliminerar beroendet av fungerande `.git`-metadata på SMB/NFS.
