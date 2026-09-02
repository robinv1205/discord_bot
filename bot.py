import os
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import yt_dlp
import asyncio
from collections import deque

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))

SONG_QUEUES = {}
PENDING_INTERACTIONS = set()  # Verhindert doppelte Interaction-Verarbeitung

YDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "outtmpl": "downloads/%(id)s.%(ext)s",
    "extractor_args": {"youtube": {"player_client": ["tv", "web_safari", "web"]}},
    # "force_ipv4": True,
}


# yt_dlp-Funktionen
def _extract(query, ydl_opts):
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(query, download=True)
        entry = info["entries"][0] if "entries" in info else info
        filename = ydl.prepare_filename(entry)
        return entry, filename


async def search_ytdlp_async(query, ydl_opts, retries=3, timeout=60):
    loop = asyncio.get_running_loop()
    last_error = None
    for attempt in range(retries):
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(None, lambda: _extract(query, ydl_opts)),
                timeout=timeout,
            )
        except asyncio.TimeoutError as e:
            # Do NOT retry on timeout: the background thread is still
            # running (run_in_executor can't be cancelled), and firing
            # another attempt would collide with it against the same
            # PO-token server / video. Fail cleanly instead.
            raise TimeoutError("Extraction took too long and was abandoned.") from e
        except yt_dlp.utils.DownloadError as e:
            last_error = e
            if "page needs to be reloaded" in str(e).lower():
                await asyncio.sleep(2)
                continue
            raise
    raise last_error


def cleanup_file(filename):
    try:
        os.remove(filename)
    except OSError:
        pass


async def warm_up_ytdlp():
    """Primes the PO-token provider, deno JS-challenge solver, and yt-dlp's
    player-JS cache in the background so the first real /play isn't the
    slow cold-start request (which risks tripping the extraction timeout)."""
    try:
        print("[WARMUP] Priming yt-dlp / PO-token provider...")
        loop = asyncio.get_running_loop()
        warm_opts = dict(YDL_OPTIONS)
        warm_opts["skip_download"] = True
        await loop.run_in_executor(
            None,
            lambda: yt_dlp.YoutubeDL(warm_opts).extract_info(
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ", download=False
            ),
        )
        print("[WARMUP] Done.")
    except Exception as e:
        print(f"[WARMUP] Failed (non-fatal): {e}")


# Intents
intent = discord.Intents.default()
intent.message_content = True

bot = commands.Bot(command_prefix="!", intents=intent)


@bot.event
async def on_ready():
    try:
        guild = discord.Object(id=GUILD_ID)
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        print(f"Synced {len(synced)} commands to guild {GUILD_ID}")
    except Exception as e:
        print(f"Failed to sync commands: {e}")
    print(f"{bot.user} is online!")
    asyncio.create_task(warm_up_ytdlp())


@bot.event
async def on_interaction(interaction: discord.Interaction):
    print(
        f"[RAW] Interaction received: type={interaction.type},"
        f"command={interaction.data.get('name') if interaction.data else None}"
    )


@bot.event
async def on_message(message):
    print(f"[MSG] {message.author}: {message.content}")


# Greet-Command
@bot.tree.command(name="greet", description="Sends a greeting to the user")
async def greet(interaction: discord.Interaction):
    username = interaction.user.mention
    await interaction.response.send_message(f"Hello there, {username}")


# Play Command
@bot.tree.command(name="play", description="Play a song or add it to the queue.")
@app_commands.describe(song_query="Search query")
async def play(interaction: discord.Interaction, song_query: str):
    print(f"[DEBUG] /play triggered by {interaction.user}, id={interaction.id}")
    # Doppelte Interaction verhindern
    if interaction.id in PENDING_INTERACTIONS:
        return
    PENDING_INTERACTIONS.add(interaction.id)

    try:
        if not interaction.response.is_done():
            await interaction.response.defer()

        # Check voice channel membership BEFORE downloading anything,
        # so we don't waste a download if the user isn't even connected.
        voice_state = interaction.user.voice
        if voice_state is None or voice_state.channel is None:
            await interaction.followup.send("You must be in a voice channel.")
            return

        voice_channel = voice_state.channel

        query = "ytsearch1: " + song_query

        try:
            entry, filename = await search_ytdlp_async(query, YDL_OPTIONS)
        except Exception as e:
            await interaction.followup.send(
                f"Couldn't fetch that song after retries: `{e}`"
            )
            return

        if not entry:
            await interaction.followup.send("No results found.")
            return

        title = entry.get("title", "Untitled")

        guild_id = str(interaction.guild_id)
        if SONG_QUEUES.get(guild_id) is None:
            SONG_QUEUES[guild_id] = deque()

        SONG_QUEUES[guild_id].append((filename, title))

        voice_client = interaction.guild.voice_client

        if voice_client is None:
            voice_client = await voice_channel.connect()
        elif voice_channel != voice_client.channel:
            await voice_client.move_to(voice_channel)

        if voice_client.is_playing() or voice_client.is_paused():
            await interaction.followup.send(f"Added to queue: **{title}**")
        else:
            await interaction.followup.send(f"Now playing: **{title}**")
            await play_next_song(voice_client, guild_id, interaction.channel)

    except Exception as e:
        print(f"Unexpected error in /play: {e}")
        try:
            await interaction.followup.send(f"Something went wrong: `{e}`")
        except Exception:
            pass
    finally:
        PENDING_INTERACTIONS.discard(interaction.id)


# Skip Command
@bot.tree.command(name="skip", description="Skips the current playing song")
async def skip(interaction: discord.Interaction):
    if not interaction.response.is_done():
        await interaction.response.defer()

    voice_client = interaction.guild.voice_client

    if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
        voice_client.stop()
        await interaction.followup.send("Skipped the current song.")
    else:
        await interaction.followup.send("Not playing anything to skip.")


# Pause Command
@bot.tree.command(name="pause", description="Pause the currently playing song")
async def pause(interaction: discord.Interaction):
    if not interaction.response.is_done():
        await interaction.response.defer()

    voice_client = interaction.guild.voice_client

    if voice_client is None:
        await interaction.followup.send("I'm not in a voice channel.")
        return

    if not voice_client.is_playing():
        await interaction.followup.send("Nothing is currently playing.")
        return

    voice_client.pause()
    await interaction.followup.send("Song paused.")


# Resume Command
@bot.tree.command(name="resume", description="Resume currently paused song")
async def resume(interaction: discord.Interaction):
    if not interaction.response.is_done():
        await interaction.response.defer()

    voice_client = interaction.guild.voice_client

    if voice_client is None:
        await interaction.followup.send("I'm not in a voice channel.")
        return

    if not voice_client.is_paused():
        await interaction.followup.send("I'm not paused right now.")
        return

    voice_client.resume()
    await interaction.followup.send("Playback resumed.")


# Stop Command
@bot.tree.command(name="stop", description="Stop playback and clear the queue")
async def stop(interaction: discord.Interaction):
    if not interaction.response.is_done():
        await interaction.response.defer()

    voice_client = interaction.guild.voice_client

    if voice_client is None:
        await interaction.followup.send("I'm not in a voice channel.")
        return

    guild_id = str(interaction.guild_id)
    if guild_id in SONG_QUEUES:
        for filename, _ in SONG_QUEUES[guild_id]:
            cleanup_file(filename)
        SONG_QUEUES[guild_id].clear()

    if voice_client.is_playing() or voice_client.is_paused():
        voice_client.stop()

    await interaction.followup.send("Stopped playback and disconnected.")
    await voice_client.disconnect()


# Play next song
async def play_next_song(voice_client, guild_id, channel):
    if not voice_client.is_connected():
        if SONG_QUEUES.get(guild_id):
            for filename, _ in SONG_QUEUES[guild_id]:
                cleanup_file(filename)
            SONG_QUEUES[guild_id].clear()
        return

    if SONG_QUEUES.get(guild_id):
        filename, title = SONG_QUEUES[guild_id].popleft()

        source = discord.FFmpegOpusAudio(filename)

        def after_play(error):
            if error:
                print(f"Error playing {title}: {error}")
            # File is removed only after playback of THIS song finishes,
            # since FFmpegOpusAudio streams from disk while playing.
            cleanup_file(filename)
            asyncio.run_coroutine_threadsafe(
                play_next_song(voice_client, guild_id, channel), bot.loop
            )

        voice_client.play(source, after=after_play)
        await channel.send(f"Now playing: **{title}**")
    else:
        await voice_client.disconnect()
        SONG_QUEUES[guild_id] = deque()


bot.run(TOKEN)
