# ESPHome Backup

Home Assistant App för automatisk backup av ESPHome-konfigurationer från `/config/esphome`.

Funktioner:
- speglar aktuell ESPHome-konfiguration till vald backupdestination
- komprimerade `.tar.zst`-arkiv
- daily/weekly/monthly-retention
- valfri lokal Git-historik
- valfria `esphome bundle`-paket
- status till Home Assistant via Core API
- stöd för destination under `/share`, `/media` eller `/backup`


## v0.2.1
NAS-vänligare rsync, destinationsverifiering och korrigerad schemaläggning.
