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

SONG_QUEUES = {}
PENDING_INTERACTIONS = set()  # Verhindert doppelte Interaction-Verarbeitung

# yt_dlp-Funktionen
async def search_ytdlp_async(query, ydl_opts):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: _extract(query, ydl_opts))

def _extract(query, ydl_opts):
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(query, download=False)

# Intents
intent = discord.Intents.default()
intent.message_content = True

bot = commands.Bot(command_prefix="!", intents=intent)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"{bot.user} is online!")

# Greet-Command
@bot.tree.command(name="greet", description="Sends a greeting to the user")
async def greet(interaction: discord.Interaction):
    username = interaction.user.mention
    await interaction.response.send_message(f"Hello there, {username}")

# Play Command
@bot.tree.command(name="play", description="Play a song or add it to the queue.")
@app_commands.describe(song_query="Search query")
async def play(interaction: discord.Interaction, song_query: str):
    # Doppelte Interaction verhindern
    if interaction.id in PENDING_INTERACTIONS:
        return
    PENDING_INTERACTIONS.add(interaction.id)

    try:
        if not interaction.response.is_done():
            await interaction.response.defer()

        ydl_options = {
            "format": "bestaudio/best",
            "noplaylist": True,
            "youtube_include_dash_manifest": False,
            "youtube_include_hls_manifest": False,
        }

        query = "ytsearch1: " + song_query

        try:
            results = await search_ytdlp_async(query, ydl_options)
        except Exception as e:
            await interaction.followup.send(f"Error while searching: `{e}`")
            return

        tracks = results.get("entries", [])
        if not tracks:
            await interaction.followup.send("No results found.")
            return

        first_track = tracks[0]
        audio_url = first_track.get("url")
        title = first_track.get("title", "Untitled")

        if not audio_url:
            await interaction.followup.send("Could not get a playable URL.")
            return

        guild_id = str(interaction.guild_id)
        if SONG_QUEUES.get(guild_id) is None:
            SONG_QUEUES[guild_id] = deque()

        SONG_QUEUES[guild_id].append((audio_url, title))

        voice_state = interaction.user.voice
        if voice_state is None or voice_state.channel is None:
            await interaction.followup.send("You must be in a voice channel.")
            return

        voice_channel = voice_state.channel
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
        SONG_QUEUES[guild_id].clear()

    if voice_client.is_playing() or voice_client.is_paused():
        voice_client.stop()

    await interaction.followup.send("Stopped playback and disconnected.")
    await voice_client.disconnect()

# Play next song
async def play_next_song(voice_client, guild_id, channel):
    if not voice_client.is_connected():
        if SONG_QUEUES.get(guild_id):
            SONG_QUEUES[guild_id].clear()
        return

    if SONG_QUEUES.get(guild_id):
        audio_url, title = SONG_QUEUES[guild_id].popleft()

        ffmpeg_options = {
            "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
            "options": "-vn -c:a libopus -b:a 96k -f opus -loglevel quiet",
        }

        source = discord.FFmpegOpusAudio(audio_url, **ffmpeg_options)

        def after_play(error):
            if error:
                print(f"Error playing {title}: {error}")
            asyncio.run_coroutine_threadsafe(
                play_next_song(voice_client, guild_id, channel), bot.loop
            )

        voice_client.play(source, after=after_play)
        await channel.send(f"Now playing: **{title}**")
    else:
        await voice_client.disconnect()
        SONG_QUEUES[guild_id] = deque()

bot.run(TOKEN)
