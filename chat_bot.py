import os
import asyncio
import sys
import fcntl
from dotenv import load_dotenv
import discord
from groq import Groq
 
load_dotenv()
groq_client = Groq(api_key=os.getenv("AI_TOKEN"))
token = os.getenv("BOT_TOKEN")
 
#Einzelinstanz-Schutz
lock_file = open("/tmp/discord_bot.lock", "w")
try:
    fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
except IOError:
    print("Bot läuft bereits! Beende diese Instanz.")
    sys.exit(1)
 
intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)
 
model = "llama-3.3-70b-versatile"
PREFIX = "//" 
 
system_prompt = '''
ENTER PROMPT HERE
''' 
responding_channels: set[int] = set()
 
@bot.event
async def on_ready():
    print(f"{bot.user.name} is online!")
 
@bot.event
async def on_message(msg):
    # Ignoriere alle Bots
    if msg.author.bot:
        return
 
    #Mention oder Prefix
    bot_mentioned = bot.user in msg.mentions
    has_prefix = msg.content.startswith(PREFIX)
 
    if not bot_mentioned and not has_prefix:
        return  
 
    #Verhindert parallele Antworten im selben Channel
    if msg.channel.id in responding_channels:
        return
    responding_channels.add(msg.channel.id)
 
    # Nachricht bereinigen (Prefix oder Mention entfernen)
    user_input = msg.content
    if has_prefix:
        user_input = user_input[len(PREFIX):].strip()
    if bot_mentioned:
        user_input = user_input.replace(f"<@{bot.user.id}>", "").strip()
 
    if not user_input:
        await msg.channel.send("Was willst du?")
        responding_channels.discard(msg.channel.id)
        return
 
    try:
        async with msg.channel.typing():
            response = await asyncio.to_thread(
                    groq_client.chat.completions.create,
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "system", "content": user_input},
                        ],
                        max_tokens=1024,
                    )

            content = response.choices[0].message.content

        if not content or not content.strip():
            return
 
        if len(content) <= 2000:
            await msg.channel.send(content)
        else:
            for i in range(0, len(content), 2000):
                chunk = content[i:i+2000]
                if chunk.strip():
                    await msg.channel.send(chunk)
 
    except Exception as e:
        print(f"Fehler bei Groq: {e}")
        await msg.channel.send("Probiers noch mal")
    finally:
        responding_channels.discard(msg.channel.id)
 
 
async def main():
    while True:
        try:
            await bot.start(token)
        except Exception as e:
            print(f"Verbindung verloren: {e} - reconnecting...")
            await asyncio.sleep(5)
 
 
asyncio.run(main())
