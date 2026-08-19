# Changelog

## 0.2.2
- Ny destinationslayout med separat config, bundles, Git och manifest.
- Writable temp-workspace för ESPHome bundle.
- Robust Git-init i separat repo.
- Komponentfel degraderas till `ok_with_warnings` efter verifierad kärnbackup.
- Manifest med komponentstatus.


## 0.2.1
- Gör rsync kompatiblare med SMB/NFS/NAS genom att inte försöka bevara Unix owner/group/permissions eller katalogtider.
- Loggar full rsync-output och kommando vid fel, inklusive exit-kod.
- Verifierar efter synk att alla relevanta filer finns på destinationen och har identiskt SHA-256-innehåll.
- Backup markeras inte som lyckad om verifieringen misslyckas.
- Fixar scheduler-visningen så att 03:30 rapporteras som 03:30 i stället för 03:29.
- Statussensorn får verified_files och verified_bytes.

## 0.2.0
- Paketerad som Git-ready Home Assistant app repository.
- Repository-metadata korrigerad för lokal/publicerad repository-användning.
- Dokumentation för lokal installation och repository-installation.
- Behåller lokal build utan `image:` så Home Assistant bygger appen själv.
- Versionssträng uppdaterad.

## 0.1.0
- Första versionen.
