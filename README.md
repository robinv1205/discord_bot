# Discord Music Bot

## Setup

1. Python 3.9+ installieren
2. Virtuelle Umgebung erstellen

```bash
    python -m venv venv
    source venv/bin/activate 
    # venv\Scripts\activate #Windows
```

3. Pakete installieren
```bash
pip install -r requirements.txt
```

4. `.env.`-Datei erstellen
```text
DISCORD_TOKEN=TOKEN
```

## FFmpeg installieren
```bash
sudo pacman -S ffmpeg
```

# Commands
- `/play <query>` -> Song von Youtube starten
- `/skip` -> Aktuellen Song skippen
- `/pause` -> pausieren
- `/resume` -> fortsetzen
- `/stop` -> Bot stoppen und disconnect

