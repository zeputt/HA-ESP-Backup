# ESPHome Backup

Automatisk och verifierad backup av Home Assistants ESPHome-konfigurationer till `/share`, `/media` eller `/backup`.

Version 0.3.0 introducerar ett Ingress-baserat webbgränssnitt i Home Assistant med statusöversikt och manuell **Backup now**.

## Funktioner

- NAS/SMB-vänlig rsync av `/config/esphome`
- SHA-256-verifiering av varje kopierad fil
- ESPHome bundles i skrivbar temporär workspace
- zstd-komprimerade arkiv och retention
- lokal Git-historik under appens persistenta `/data`
- verifierad portabel Git bundle på backupdestinationen
- Home Assistant-statussensorer
- Ingress GUI, utan exponerad webbport
- manuell backup med överlappningsskydd

Se `DOCS.md` för installation och konfiguration.
