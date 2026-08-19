# Changelog

## 0.3.0

- Nytt Home Assistant Ingress GUI.
- Dashboard för backupstatus, schema, destination, filer, bundles, Git och arkiv.
- Ny **Backup now**-funktion.
- Manuell backup körs asynkront och GUI:t följer status live.
- Låsning hindrar samtidiga manuella/schemalagda backupjobb.
- Runtime-status sparas persistent under `/data`.
- Senaste manifest, Git-status och arkiv presenteras i GUI:t.
- Ingress-webbservern accepterar endast trafik från Home Assistant Supervisors Ingress-proxy.
- Inga webbportar exponeras på värden.

## 0.2.3

- Aktivt Git-repository flyttat till persistenta `/data/git/repo`.
- Portabel Git bundle exporteras till backupdestinationen.
- Git bundle verifieras efter kopiering till destinationen.
- `git-status.json` med commit, historiklängd och bundle-status.

## 0.2.2

- Ny destinationsstruktur med separat `latest/config`, `bundles`, `git`, `archive` och manifest.
- Bundle-byggning i skrivbar temporär workspace.
- Valfria komponentfel fäller inte en verifierad kärnbackup.

## 0.2.1

- NAS/SMB-vänlig rsync.
- SHA-256-verifiering.
- Förbättrad felloggning.
- Scheduler korrigerad till exakt konfigurerad minut.
