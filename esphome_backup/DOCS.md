# ESPHome Backup 0.3.1

ESPHome Backup säkerhetskopierar `/config/esphome` från Home Assistant till en skrivbar Home Assistant-lagringsmount.

## Webbgränssnitt

Version 0.3.1 har ett Ingress-gränssnitt. Efter uppdatering och start visas **OPEN WEB UI** på appens infosida och ESPHome Backup kan även visas som en Home Assistant-panel.

GUI:t visar:

- övergripande backupstatus
- senaste och nästa körning
- destination och schema
- antal ESPHome-konfigurationer
- verifierade filer och datamängd
- bundle-status
- Git commits, HEAD och bundle-verifiering
- status för filer, bundles, Git och arkiv var för sig
- retentionpolicy
- senaste arkiven
- varningar från senaste körningen
- **Backup now** för en manuell backup

Manuell och schemalagd backup kan inte köras samtidigt.

## Destination

Exempel för en Synology-share monterad i Home Assistant som `HA_ESP_Backup`:

```yaml
destination: /share/HA_ESP_Backup/esphome-backup
```

Destinationen måste ligga under `/share`, `/media` eller `/backup`.

## Struktur

```text
esphome-backup/
├── latest/
│   ├── config/
│   └── bundles/
├── archive/
├── git/
│   ├── esphome-config.bundle
│   └── git-status.json
└── manifest.json
```

`latest/config` är en ren spegel av ESPHome-katalogen. Git-motorn ligger lokalt i appens persistenta `/data/git/repo`; endast den portabla och verifierade Git-bundlen skrivs till nätverkslagringen.

## Git restore

```bash
git clone esphome-config.bundle esphome-restored
```

## Säkerhet

Home Assistant-konfigurationen är monterad read-only. GUI:t använder Home Assistant Ingress och accepterar endast trafik från Supervisors Ingress-proxy. Ingen separat webbport publiceras på Home Assistant-värden.


### GUI 0.3.1
Git-historik och live runtime-logg visas i Ingress-gränssnittet. Sätt `destination_url` till en webbadress för NAS:ens File Station eller motsvarande om destinationen ska vara klickbar.
