# ESPHome Backup

Home Assistant App för automatisk backup av ESPHome-konfigurationer från `/config/esphome`.

Funktioner:
- verifierad spegel under `latest/config`
- SHA-256-verifiering efter synk
- valfria ESPHome bundles byggda i skrivbar temporär workspace
- komprimerade `.tar.zst`-arkiv med daily/weekly/monthly retention
- separat lokalt Git-repository under `git/repo`
- komponentbaserad status: `ok`, `ok_with_warnings` eller `error`
- status till Home Assistant via Core API
- destination under `/share`, `/media` eller `/backup`

## 0.2.2
Denna version separerar kärnbackup från Git, bundles och arkiv. En verifierad filbackup förblir lyckad även om en valfri extrafunktion misslyckas.
