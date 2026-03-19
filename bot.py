import os
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import yt_dlp
import asyncio
from collections import deque

#Get auth for Discord Bot
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

#Set Queue
SONG_QUEUES = {}

async def search_ytdlp_async(query, ydl_opts):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: _extract(query, ydl_opts))

def _extract(query, ydl_opts):
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(query, download=False)

intent = discord.Intents.default()
intent.message_content = True

bot = commands.Bot(command_prefix="!", intents=intent)

#set bot online
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"{bot.user} is online!")

#greet command
@bot.tree.command(name="greet", description="Sends a greeting to the user")
async def play(interaction: discord.Interaction):
    username = interaction.user.mention
    await interaction.response.send_message(f"Hello there, {username}")

#play command
@bot.tree.command(name="play", description="Play a song or add it to the queue.")
@app_commands.describe(song_query="Search query")
async def play(interaction: discord.Interaction, song_query: str):
    await interaction.response.defer()

#check if user is in a voice channel
    voice_state = interaction.user.voice
    if voice_state is None or voice_state.channel is None:
        await interaction.followup.send("You must be in a voice channel")
        return

    voice_channel = voice_state.channel
    voice_client = interaction.guild.voice_client

#connect bot to user voice channel
    if voice_client is None:
        voice_client = await voice_channel.connect()
    elif voice_channel != voice_client.channel:
        await voice_client.move_to(voice_channel)

#Set options for yt streaming
    ydl_options = {
            "format": "bestaudio[abr<=96]/bestaudio",
            "noplaylist": True,
            "youtube_include_dash_manifest": False,
            "youtube_include_hls_manifest": False,
        }

#Seach query
    query = "ytsearch1: " + song_query
    results = await search_ytdlp_async(query, ydl_options)
    tracks = results.get("entries", [])

#if no tracks were found
    if tracks is None:
        await interaction.followup.send("No results found.")
        return

#set track info
    first_track = tracks[0]
    audio_url = first_track["url"]
    title = first_track.get("title", "Untitled")

    guild_id = str(interaction.guild_id)
    if SONG_QUEUES.get(guild_id) is None:
        SONG_QUEUES[guild_id] = deque()

#add songs to queue
    SONG_QUEUES[guild_id].append((audio_url, title))

    if voice_client.is_playing() or voice_client.is_paused():
        await interaction.followup.send(f"Added to queue: **{title}**")
    else:
        await interaction.followup.send(f"Now playing: **{title}**")
        await play_next_song(voice_client, guild_id, interaction.channel)

#skip command
@bot.tree.command(name="skip", description="Skips the current playing song")
async def skip(interaction: discord.Interaction):
    if interaction.guild.voice_client and (interaction.guild.voice_client.is_playing() or interaction.guild.voice_client.is_paused()):
        interaction.guild.voice_client.stop()
        await interaction.response.send_message("Skipped the current song")
    else:
        await interaction.response.send_message("Not playing anything to skip")

#pause command
@bot.tree.command(name="pause", description="Pause the currently playing song")
async def pause(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client

    #Check if the bot is in a voice channel
    if voice_client is None:
        return await interaction.response.send_message("I'm not in a voice channel")

    #Check if something is playing
    if not voice_client.is_playing():
        return await interactin.response.send_message("Nothing is currently playing")

    #Pause track
    voice_client.pause()
    await interaction.response.send_message("Song paused")

#resume command
@bot.tree.command(name="resume", description="Resume currently paused song")
async def resume(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    
    #Check if bot is in voice channel
    if voice_client is None:
        return await interaction.response.send_message("I'm not in a voice channel")

    #Check if paused
    if not voice_client.is_paused():
        return await interactin.response.send_message("I'm not paused right now")

    #Resume playback
    voice_client.resume()
    await interaction.response.send_message("Playback resumed")

#stop command
@bot.tree.command(name="stop", description="Stop playback and clear the queue")
async def stop(interaction: discord.Interaction):
    await interaction.response.defer()
    voice_client = interaction.guild.voice_client

    #Check if bot is in voice channel
    if voice_client is None:
        return await interaction.followup.send("I'm not in a voice channel")

    #Clear the queue
    guild_id_str = str(interaction.guild_id)
    if guild_id_str in SONG_QUEUES:
        SONG_QUEUES[guild_id_str].clear()

    #If something is playing or paused, stop it
    if voice_client.is_playing() or voice_client.is_paused():
        voice_client.stop()

    await interaction.followup.send("Stopped playback and disconnected")

    #Disconnect from channel
    await voice_client.disconnect()


async def play_next_song(voice_client, guild_id, channel):
    if SONG_QUEUES[guild_id]:
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

bot.run(TOKEN)
