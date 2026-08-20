# Changelog

## 0.3.3
- Klickbar Git-historik med commit-detaljer i modal.
- Commit-modal med översikt, filnivåstatistik och full textdiff.
- Per fil visas additions/deletions; binära filer markeras separat.
- Diffrespons begränsas till 2 MB för att skydda Ingress-GUI:t från mycket stora commits.
- GUI:t förklarar att Git registrerar konfigurationsändringar, inte varje backupkörning.
- Nytt Ingress-API: `/api/git-commit?commit=<sha>`.

## 0.3.1
- Git-historik visas direkt i Ingress-GUI:t.
- Live runtime-logg visas under körning och behåller de senaste loggraderna.
- Ny valfri `destination_url` gör destinationen klickbar och öppnar den i ny flik.
- Nya Ingress-API:er: `/api/log` och `/api/git-history`.

## 0.3.1

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
