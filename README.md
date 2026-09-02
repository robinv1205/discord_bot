<div align="center">
<h1>Discord Music and Groq ChatBot</h1>
<img alt="Static Badge" src="https://img.shields.io/badge/discord--141414?style=for-the-badge&logo=discord&logoColor=1dc7b5">
<img alt="Static Badge" src="https://img.shields.io/badge/python--141414?style=for-the-badge&logo=python&logoColor=1dc7b5">
</div>

---

> [!WARNING] CURRENTLY BROKEN
> UNFORTUNATELY THE MUSIC BOT DOES NOT WORK ATM - YOUTUBE IMPLEMENTED AN ANTI-BOT FEATURE THAT PREVENTS ytdlp FROM ACCESSING YOUTUBE

<!-- TODO: add demo video -->

## Setup

<details open>
  <summary><b>Requirements</b></summary>

1. Python 3.9+
2. Install packages

```bash
pip install -r requirements.txt
```

1. Put tokens in `.env.`

```text
DISCORD_TOKEN=TOKEN
BOT_TOKEN
GROQ_API
```

<h2>Install FFmpeg</h2>

```bash
sudo pacman -S ffmpeg
```

</details>

# I have added a new ChatBot with Groq

You'll need to install Groq, as well as create an account to get the API key

```bash
pip install groq --break-system-packages
```

<details open>
  <summary><b>Commands</b></summary>

- `/play <query>` -> Start song from YouTube
- `/skip` -> Skip currently played song
- `/pause` -> Pause
- `/resume` -> Resume
- `/stop` -> Stops Bot and disconnects from channel
- `//` -> address AI-Bot

</details>
