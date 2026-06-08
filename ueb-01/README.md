# 🖥️ DigSig Prototype

Monorepo mit zwei getrennten Teilprojekten:

| Ordner | Inhalt |
|--------|--------|
| [`arduino/`](arduino/) | Arduino **UNO Q** App (App Lab: `app.yaml`, `python/`, `sketch/`) |
| [`api/`](api/) | **FastAPI** Service (eigenes Python-Projekt) |

## Arduino-App aufs Board syncen

```bash
./rsync.sh push            # Laptop -> Board (synct nur arduino/)
./rsync.sh push --dry-run  # Testlauf
./rsync.sh pull            # Board -> Laptop
```

## API lokal starten

Siehe [`api/README.md`](api/README.md).

## Hinweise für die Entwicklung

Board- und App-Lab-Wissen liegt in [`.claude/knowledge/`](.claude/knowledge/) —
vor der Arbeit lesen (siehe [`CLAUDE.md`](CLAUDE.md)).
