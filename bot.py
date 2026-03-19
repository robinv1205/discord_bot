import os
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import yt_dlp
import asyncio
from collections import deque

# dotenv laden
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

SONG_QUEUES = {}

# yt_dlp‑Funktionen
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

#on_ready
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"{bot.user} is online!")

#Greet‑Command 
@bot.tree.command(name="greet", description="Sends a greeting to the user")
async def greet(interaction: discord.Interaction):
    username = interaction.user.mention
    await interaction.response.send_message(f"Hello there, {username}")

#Play Command
@bot.tree.command(name="play", description="Play a song or add it to the queue.")
@app_commands.describe(song_query="Search query")
async def play(interaction: discord.Interaction, song_query: str):
    try:
        await interaction.response.defer()
    except discord.NotFound:
        return

    # yt_dlp‑Optionen
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
        try:
            await interaction.followup.send(f"Error while searching: `{e}`")
        except discord.NotFound:
            pass
        return

    tracks = results.get("entries", [])

    if not tracks:
        try:
            await interaction.followup.send("No results found.")
        except discord.NotFound:
            pass
        return

    first_track = tracks[0]
    audio_url = first_track.get("url")
    title = first_track.get("title", "Untitled")

    if not audio_url:
        try:
            await interaction.followup.send("Could not get a playable URL.")
        except discord.NotFound:
            pass
        return

    # Queue setzen
    guild_id = str(interaction.guild_id)
    if SONG_QUEUES.get(guild_id) is None:
        SONG_QUEUES[guild_id] = deque()

    SONG_QUEUES[guild_id].append((audio_url, title))

    # User in Voice‑Channel?
    voice_state = interaction.user.voice
    if voice_state is None or voice_state.channel is None:
        try:
            await interaction.followup.send("You must be in a voice channel.")
        except discord.NotFound:
            pass
        return

    voice_channel = voice_state.channel
    voice_client = interaction.guild.voice_client

    if voice_client is None:
        voice_client = await voice_channel.connect()
    elif voice_channel != voice_client.channel:
        await voice_client.move_to(voice_channel)

    # Wiedergabe / Queue
    if voice_client.is_playing() or voice_client.is_paused():
        try:
            await interaction.followup.send(f"Added to queue: **{title}**")
        except discord.NotFound:
            pass
    else:
        try:
            await interaction.followup.send(f"Now playing: **{title}**")
        except discord.NotFound:
            pass
        await play_next_song(voice_client, guild_id, interaction.channel)

#Skip Command
@bot.tree.command(name="skip", description="Skips the current playing song")
async def skip(interaction: discord.Interaction):
    try:
        await interaction.response.defer()
    except discord.NotFound:
        return

    voice_client = interaction.guild.voice_client

    if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
        voice_client.stop()
        try:
            await interaction.followup.send("Skipped the current song.")
        except discord.NotFound:
            pass
    else:
        try:
            await interaction.followup.send("Not playing anything to skip.")
        except discord.NotFound:
            pass

#Pause Command
@bot.tree.command(name="pause", description="Pause the currently playing song")
async def pause(interaction: discord.Interaction):
    try:
        await interaction.response.defer()
    except discord.NotFound:
        return

    voice_client = interaction.guild.voice_client

    if voice_client is None:
        try:
            await interaction.followup.send("I'm not in a voice channel.")
        except discord.NotFound:
            pass
        return

    if not voice_client.is_playing():
        try:
            await interaction.followup.send("Nothing is currently playing.")
        except discord.NotFound:
            pass
        return

    voice_client.pause()
    try:
        await interaction.followup.send("Song paused.")
    except discord.NotFound:
        pass

#Resume Command
@bot.tree.command(name="resume", description="Resume currently paused song")
async def resume(interaction: discord.Interaction):
    try:
        await interaction.response.defer()
    except discord.NotFound:
        return

    voice_client = interaction.guild.voice_client

    if voice_client is None:
        try:
            await interaction.followup.send("I'm not in a voice channel.")
        except discord.NotFound:
            pass
        return

    if not voice_client.is_paused():
        try:
            await interaction.followup.send("I'm not paused right now.")
        except discord.NotFound:
            pass
        return

    voice_client.resume()
    try:
        await interaction.followup.send("Playback resumed.")
    except discord.NotFound:
        pass

#Stop Command 
@bot.tree.command(name="stop", description="Stop playback and clear the queue")
async def stop(interaction: discord.Interaction):
    try:
        await interaction.response.defer()
    except discord.NotFound:
        return

    voice_client = interaction.guild.voice_client

    if voice_client is None:
        try:
            await interaction.followup.send("I'm not in a voice channel.")
        except discord.NotFound:
            pass
        return

    guild_id = str(interaction.guild_id)
    if guild_id in SONG_QUEUES:
        SONG_QUEUES[guild_id].clear()

    if voice_client.is_playing() or voice_client.is_paused():
        voice_client.stop()

    try:
        await interaction.followup.send("Stopped playback and disconnected.")
    except discord.NotFound:
        pass

    await voice_client.disconnect()

#play next song
async def play_next_song(voice_client, guild_id, channel):
    if not voice_client.is_connected():
        if SONG_QUEUES.get(guild_id):
            SONG_QUEUES[guild_id].clear()
        return

    if SONG_QUEUES.get(guild_id):
        audio_url, title = SONG_QUEUES[guild_id].popleft()

        ffmpeg_options = {
            "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
            "options": "-vn -c:a libopus -b:a 96k -f opus",
        }

        source = discord.FFmpegOpusAudio(audio_url, **ffmpeg_options)

        def after_play(error):
            if error:
                print(f"Error playing {title}: {error}")
            asyncio.run_coroutine_threadsafe(play_next_song(voice_client, guild_id, channel), bot.loop)

        voice_client.play(source, after=after_play)
        await channel.send(f"Now playing: **{title}**")
    else:
        await voice_client.disconnect()
        SONG_QUEUES[guild_id] = deque()

# Bot starten
bot.run(TOKEN)
