# ESPHome Backup

Automatisk och verifierad backup av Home Assistants ESPHome-konfigurationer till `/share`, `/media` eller `/backup`.

Version 0.3.1 introducerar ett Ingress-baserat webbgränssnitt i Home Assistant med statusöversikt och manuell **Backup now**.

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


### GUI 0.3.1
Git-historik och live runtime-logg visas i Ingress-gränssnittet. Sätt `destination_url` till en webbadress för NAS:ens File Station eller motsvarande om destinationen ska vara klickbar.


## Git commit-detaljer (0.3.3)
Git-historiken i GUI:t visar endast commits när ESPHome-konfigurationen faktiskt har ändrats. En backup utan konfigurationsändringar skapar alltså arkiv men ingen ny Git-commit. Klicka på en commitrad för att öppna en modal med ändrade filer, additions/deletions och full diff.
