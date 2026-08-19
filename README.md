# Putte Home Assistant Apps

Repository för egna Home Assistant Apps.

## Lokal installation på Home Assistant OS

Home Assistants lokala repository är `/addons`. Kopiera appkatalogen direkt dit:

```text
/addons/
└── esphome_backup/
    ├── config.yaml
    ├── Dockerfile
    ├── run.sh
    ├── app.py
    └── ...
```

Kopiera alltså **`esphome_backup`**, inte hela repository-roten, till `/addons`.

Efter kopiering: öppna **Settings -> Apps -> App store**, välj menyn och kör **Check for updates**. Appen visas under **Local apps**.

## Repository-installation via Git-URL

Hela denna katalog är samtidigt ett giltigt Home Assistant App Repository tack vare `repository.yaml` i roten. Lägg repositoryt på en Git-server som Home Assistant kan nå och lägg sedan Git-URL:en i App stores repository-dialog.

Struktur:

```text
putte-ha-apps/
├── repository.yaml
└── esphome_backup/
    ├── config.yaml
    ├── Dockerfile
    ├── run.sh
    ├── app.py
    ├── README.md
    ├── DOCS.md
    └── CHANGELOG.md
```
