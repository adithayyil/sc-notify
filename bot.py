import discord
import requests
import asyncio
import json
from dotenv import load_dotenv
import os
from datetime import datetime
import aiohttp
import sqlite3
from discord.ext import commands

# Loads environment variables
load_dotenv()

# Gets Discord token and SoundCloud client ID from .env
DISCORD_TOKEN = f"{os.getenv('DISCORD_TOKEN')}"
SOUNDCLOUD_CLIENT_ID = f"{os.getenv('SOUNDCLOUD_CLIENT_ID')}"

# Headers and parameters for API calls
headers = {
    'Pragma': 'no-cache',
    'Accept': 'application/json, text/javascript, */*; q=0.01',
    'Authorization': 'OAuth 2-294078-1161185545-Ia3hn6Kjs1uh3',
    'Sec-Fetch-Site': 'same-site',
    'Accept-Language': 'en-CA,en-US;q=0.9,en;q=0.8',
    'Cache-Control': 'no-cache',
    'Sec-Fetch-Mode': 'cors',
    'Origin': 'https://soundcloud.com',
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Safari/605.1.15',
    'Referer': 'https://soundcloud.com/',
    'Connection': 'keep-alive',
    'Host': 'api-v2.soundcloud.com',
    'Sec-Fetch-Dest': 'empty',
}
tracks_params = {
    'representation': '',
    'client_id': SOUNDCLOUD_CLIENT_ID,
    'limit': '1000',
    'app_version': '1689322736',
    'app_locale': 'en',
}

# Initializes Discord Bot
client = commands.Bot(command_prefix='!')

# Message queing for handling discord rate limits
message_queue = asyncio.Queue()
previous_track_ids = {} # For checking previous track_ids

# Create or connect to the SQLite database for custom artist lists
conn = sqlite3.connect('artists.db')
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS artists (guild_id INTEGER, user_id INTEGER)''')
conn.commit()

# Fetches stream url from a user_id
async def fetch_track_with_stream_url(session, user_id):
    url = f'https://api-v2.soundcloud.com/users/{user_id}/tracks'
    async with session.get(url, params=tracks_params, headers=headers) as response:
        if response.status == 200:
            try:
                tracks_data = await response.json()
                if all('media' in track and 'transcodings' in track['media'] and len(track['media']['transcodings']) > 1 for track in tracks_data.get('collection', [])):
                    return tracks_data
            except json.JSONDecodeError as e:
                print(f"JSON decoding error: {e}")
                return None

# Authorizes a stream_url with a track_authID
def authorize_stream_url(stream_url_unauthorized, track_authID):
    track_params = {
        'client_id': SOUNDCLOUD_CLIENT_ID,
        'track_authorization': track_authID,
    }

    response = requests.get(
        stream_url_unauthorized,
        params=track_params,
        headers=headers,
    )
    response_json = response.json()

    if response.status_code == 200 and 'url' in response_json:
        return response_json['url']

    return None

# Temporarily downloads song with authorized stream_url (server side)
def download_stream_url(url):
    response = requests.get(url)
    if response.status_code == 200:
        with open("temp.mp3", "wb") as file:
            file.write(response.content)
        return True
    return False

# Sets and queues track metadata to channel
async def send_track_data(target_channel, track_data, user):
    track_title = track_data.get('title')
    track_url = track_data.get('permalink_url')

    if not track_title or not track_url:
        print("Error: Invalid track data. Missing title or URL.")
        return

    track_art_url = track_data.get('artwork_url')
    track_ogart_url = track_art_url.replace("large", "original") if track_art_url and "large" in track_art_url else track_art_url

    track_createdAt_unformatted = track_data.get('created_at')
    track_createdAt_formatted = datetime.strptime(track_createdAt_unformatted, '%Y-%m-%dT%H:%M:%SZ').strftime('%A, %B %d, %Y %I:%M:%S %p -0400')
    track_description = track_data.get('description')
    track_id = track_data.get('id')

    track_duration = track_data.get('duration')
    track_duration_converted = f"{(track_duration // (1000 * 60 * 60)) % 24:02}:{(track_duration // (1000 * 60)) % 60:02}:{(track_duration // 1000) % 60:02}"

    track_genre = track_data.get('genre')
    track_tags = track_data.get('tag_list')

    message = f"New Upload from **{user}**\n\n**Upload Title:** {track_title}\n**Release Date & Time:** {track_createdAt_formatted}\n**Duration:** {track_duration_converted}\n**Track ID:** {track_id}\n**Genre:** {track_genre}\n**Tags:** {track_tags}\n**Description:** ```{track_description}```\n**Artwork URL:** {track_ogart_url}\n**Link:** <{track_url}> "

    try:
        await target_channel.send(message)
    except discord.errors.HTTPException as e:
        if e.status == 429:
            # Handle rate-limiting error with exponential backoff
            print(f"Rate-limiting error during send_track_data. Retrying in 1 second.")
            await asyncio.sleep(1)
            await target_channel.send(message)
        else:
            print(f"HTTP exception during send_track_data: {e}")

# Queues authorized stream_url and downloaded song file to channel
async def send_song_file(target_channel, track_data):
    track_authID = track_data.get('track_authorization')
    stream_url_unauthorized = track_data['media']['transcodings'][1]['url']
    stream_url = authorize_stream_url(stream_url_unauthorized, track_authID)

    async with aiohttp.ClientSession() as session:
        async with session.get(stream_url) as response:
            if response.status == 200:
                with open("temp.mp3", "wb") as file:
                    file.write(await response.read())
                try:
                    with open("temp.mp3", "rb") as music_file:
                        await target_channel.send(file=discord.File(music_file, filename=f"{track_data['title']}.mp3"))
                    os.remove("temp.mp3")  # Remove the file after sending successfully
                except Exception as e:
                    print(f"Error during send_song_file: {e}")
            else:
                print("Error: Failed to download the song file.")

# Sends metadata and song to channel
async def notify_channel(user, track):
    target_channel = discord.utils.get(client.get_all_channels(), name='notifications')
    if target_channel:
        await send_track_data(target_channel, track, user)
        await asyncio.sleep(1)

        # Check if the track has a valid stream URL before sending the song file
        if 'media' in track and 'transcodings' in track['media'] and len(track['media']['transcodings']) > 1:
            await send_song_file(target_channel, track)


# Gets track_id of the newest song that is uploaded
async def get_latest_track_id(session, user_id):
    url = f'https://api-v2.soundcloud.com/users/{user_id}/tracks'
    async with session.get(url, params=tracks_params, headers=headers) as response:
        if response.status == 200:
            tracks_data = await response.json()
            if 'collection' in tracks_data and len(tracks_data['collection']) > 0:
                latest_track_id = max(track['id'] for track in tracks_data['collection'])
                return latest_track_id
    return None

# Updates previous track_ids after checking
async def update_previous_track_ids(session):
    for guild in client.guilds:
        guild_id = guild.id
        c.execute('SELECT user_id FROM artists WHERE guild_id = ?', (guild_id,))
        user_ids = [row[0] for row in c.fetchall()]

        for user_id in user_ids:
            latest_track_id = await get_latest_track_id(session, user_id)
            # Initialize the set for this artist if it's not in previous_track_ids
            previous_track_ids.setdefault((guild_id, user_id), set())
            previous_track_ids[(guild_id, user_id)].add(latest_track_id)

# Checks if a user has new tracks
async def check_user_tracks(session, guild_id, user_id):
    tracks_data = await fetch_track_with_stream_url(session, user_id)
    if tracks_data:
        latest_track_id = previous_track_ids.get((guild_id, user_id))
        if not latest_track_id:
            # If no previous track ID found, store the latest track ID
            latest_track_id = max(track['id'] for track in tracks_data['collection'])
            previous_track_ids[(guild_id, user_id)] = latest_track_id

        for track in tracks_data['collection']:
            track_id = track['id']
            if track_id > latest_track_id:
                await notify_channel(user_id, track)
                latest_track_id = track_id

        previous_track_ids[(guild_id, user_id)] = latest_track_id

# Creates a connection to database file (server side)
def create_db_connection():
    conn = sqlite3.connect('artists.db')
    return conn

# Gets custom artists for a guild from the database
async def get_artists_from_db(guild_id):
    c.execute('SELECT user_id FROM artists WHERE guild_id = ?', (guild_id,))
    return [row[0] for row in c.fetchall()]

# Function to add a custom artist to the guild's list
@client.command()
async def add_artist(ctx, user_id: int):
    guild_id = ctx.guild.id
    conn = create_db_connection()
    c = conn.cursor()
    
    # Check if the user_id is valid 
    url = f'https://api-v2.soundcloud.com/users/{user_id}/tracks'
    response = requests.get(url, params=tracks_params, headers=headers)
    tracks_data = response.json()
    
    if 'collection' not in tracks_data or not tracks_data['collection']:
        await ctx.send(f"Invalid user ID ***{user_id}***. The user doesn't exist on SoundCloud")
        return
    
    c.execute('SELECT user_id FROM artists WHERE guild_id = ? AND user_id = ?', (guild_id, user_id))
    existing_entry = c.fetchone()

    if existing_entry is None:
        c.execute('INSERT INTO artists (guild_id, user_id) VALUES (?, ?)', (guild_id, user_id))
        conn.commit()
        await ctx.send(f"Added user ***{user_id}*** to the list of custom artists for this server.")
    else:
        await ctx.send(f"User ***{user_id}*** is already in the list of custom artists for this server.")

    conn.close()

# Command to remove a custom artist from the guild's list
@client.command()
async def remove_artist(ctx, user_id: int):
    guild_id = ctx.guild.id
    conn = create_db_connection()
    c = conn.cursor()
    c.execute('DELETE FROM artists WHERE guild_id = ? AND user_id = ?', (guild_id, user_id))
    conn.commit()
    conn.close()  # Close the connection after committing changes
    await ctx.send(f"Removed user ***{user_id}*** from the list of custom artists for this server.")

# Function to list all user_ids being checked for new tracks
@client.command()
async def list_artists(ctx):
    guild_id = ctx.guild.id
    conn = create_db_connection()
    c = conn.cursor()
    c.execute('SELECT user_id FROM artists WHERE guild_id = ?', (guild_id,))
    user_ids = [row[0] for row in c.fetchall()]
    conn.close()  # Close the connection after fetching data

    if len(user_ids) == 0:
        await ctx.send("There are no custom artists added for this server.")
    else:
        users = "\n".join(str(user_id) for user_id in user_ids)
        await ctx.send(f"List of custom artist user IDs being checked:\n```\n{users}\n```")

# Main function to check for new tracks and notify channels
async def check_for_new_tracks():
    await client.wait_until_ready()
    async with aiohttp.ClientSession() as session:
        while not client.is_closed():
            try:
                for guild in client.guilds:
                    guild_id = guild.id
                    user_ids = await get_artists_from_db(guild_id)

                    for user_id in user_ids:
                        await check_user_tracks(session, guild_id, user_id)
            except Exception as e:
                print(f"Error during track checking: {e}")

            await asyncio.sleep(1)


@client.event
async def on_ready():
    print(f"We have logged in as {client.user}")

    # Start the background task to check for new tracks
    client.loop.create_task(check_for_new_tracks())

    # Print database status
    print("Database Connection Status:", conn is not None)

@client.event
async def on_guild_join(guild):
    print(f"Joined new guild: {guild.name}")

    # Add a placeholder entry (user ID 0) to the artists table for the new guild
    c.execute('INSERT OR IGNORE INTO artists (guild_id, user_id) VALUES (?, ?)', (guild.id, 0))
    await conn.commit()

client.run(DISCORD_TOKEN)