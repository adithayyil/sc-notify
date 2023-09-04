from bs4 import BeautifulSoup
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
from discord import app_commands

# Loads environment variables
load_dotenv()

# Gets Discord token and SoundCloud client ID from .env
DISCORD_TOKEN = f"{os.getenv('DISCORD_TOKEN')}"
SOUNDCLOUD_CLIENT_ID = f"{os.getenv('SOUNDCLOUD_CLIENT_ID')}"
SOUNDCLOUD_AUTH_ID = f"{os.getenv('SOUNDCLOUD_AUTH_ID')}"

# Headers and parameters for API calls
headers = {
    'Pragma': 'no-cache',
    'Accept': 'application/json, text/javascript, */*; q=0.01',
    'Authorization': f'OAuth {SOUNDCLOUD_AUTH_ID}',
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
intents = discord.Intents.default()
intents.typing = False 
client = commands.Bot(command_prefix='!', help_command=None, intents=intents)

# Create the command group "tree"
@client.group(name="tree")
async def tree(ctx):
    if ctx.invoked_subcommand is None:
        await ctx.send('Invalid tree command. Available subcommands: add, remove, list')


# Message queing for handling discord rate limits
message_queue = asyncio.Queue()
previous_track_ids = {} # For checking previous track_ids

# Create or connect to the SQLite database for custom artist lists
conn = sqlite3.connect('artists.db', isolation_level='DEFERRED')
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS artists (guild_id INTEGER, artist_id INTEGER, latest_track_id INTEGER, artist_name TEXT)''')
conn.commit()

# Fetches stream url from a artist_id
async def fetch_track_with_stream_url(session, artist_id):
    url = f'https://api-v2.soundcloud.com/users/{artist_id}/tracks'
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

# Sets and queues track metadata to server channel
async def send_track_data(guild_id, track_data):
    target_channel = None
    guild = discord.utils.get(client.guilds, id=guild_id)
    if guild:
        target_channel = discord.utils.get(guild.channels, name='notifications')
    if target_channel:
        track_title = track_data.get('title')
        track_url = track_data.get('permalink_url')

        if not track_title or not track_url:
            print("Error: Invalid track data. Missing title or URL.")
            return

        track_artist_username = track_data['user']['permalink']
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

        message = f"New Upload from **{track_artist_username}**\n\n**Upload Title:** {track_title}\n**Release Date & Time:** {track_createdAt_formatted}\n**Duration:** {track_duration_converted}\n**Track ID:** {track_id}\n**Genre:** {track_genre}\n**Tags:** {track_tags}\n**Description:** ```{track_description}```\n**Artwork URL:** {track_ogart_url}\n**Link:** <{track_url}> "

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

# Queues authorized stream_url and downloaded song file to server channel
async def send_song_file(guild_id, track_data):
    target_channel = None
    guild = discord.utils.get(client.guilds, id=guild_id)
    if guild:
        target_channel = discord.utils.get(guild.channels, name='notifications')
    if target_channel:
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
async def notify_channel(guild_id, track):
    target_channel = None
    guild = discord.utils.get(client.guilds, id=guild_id)
    if guild:
        target_channel = discord.utils.get(guild.channels, name='notifications')
    if target_channel:
        await send_track_data(guild_id, track)
        await asyncio.sleep(1)

        # Check if the track has a valid stream URL before sending the song file
        if 'media' in track and 'transcodings' in track['media'] and len(track['media']['transcodings']) > 1:
            await send_song_file(guild_id, track)

# Gets track_id of the newest song that is uploaded
def get_latest_track_id(artist_id):
    url = f'https://api-v2.soundcloud.com/users/{artist_id}/tracks'
    response = requests.get(url, params=tracks_params, headers=headers)
    if response.status_code == 200:
        tracks_data = response.json()
        if 'collection' in tracks_data and len(tracks_data['collection']) > 0:
            return max(track['id'] for track in tracks_data['collection'])
    return None

# Updates previous track_ids after checking
async def update_previous_track_ids(session):
    for guild in client.guilds:
        guild_id = guild.id
        c.execute('SELECT artist_id, latest_track_id FROM artists WHERE guild_id = ?', (guild_id,))
        entries = c.fetchall()

        for artist_id, latest_track_id in entries:
            tracks_data = await fetch_track_with_stream_url(session, artist_id)
            if tracks_data:
                latest_track = tracks_data['collection'][0]
                latest_track_id_api = latest_track.get('id')
                if latest_track_id_api > latest_track_id:
                    await notify_channel(artist_id, latest_track)
                    c.execute('UPDATE artists SET latest_track_id = ? WHERE guild_id = ? AND artist_id = ?', (latest_track_id_api, guild_id, artist_id))

        conn.commit()

# Checks if a user has new tracks
async def check_artist_tracks(session, conn, guild_id, artist_id):
    tracks_data = await fetch_track_with_stream_url(session, artist_id)
    if tracks_data and 'collection' in tracks_data:
        latest_track_id = previous_track_ids.get((guild_id, artist_id))
        if not latest_track_id:
            latest_track_id = max(track['id'] for track in tracks_data['collection']) if tracks_data['collection'] else None
            previous_track_ids[(guild_id, artist_id)] = latest_track_id

        for track in tracks_data['collection']:
            track_id = track['id']
            if track_id > latest_track_id:
                await notify_channel(guild_id, track)
                latest_track_id = track_id

        previous_track_ids[(guild_id, artist_id)] = latest_track_id

# Creates a connection to database file (server side)
def create_db_connection():
    conn = sqlite3.connect('artists.db')
    return conn

# Gets custom artists for a guild from the database
async def get_artists_from_db(guild_id):
    c.execute('SELECT artist_id FROM artists WHERE guild_id = ?', (guild_id,))
    return [row[0] for row in c.fetchall()]

# Parses script tag content to get id
def get_artist_id(resp):
    html_content = resp.content
    soup = BeautifulSoup(html_content, 'html.parser')
    script_tags = soup.find_all('script')

    # Extract the script content containing the window.__sc_hydration data
    script_content = None
    for script_tag in script_tags:
        if script_tag.string and 'window.__sc_hydration' in script_tag.string:
            script_content = script_tag.string 
            break

    # Parses the string to get id
    start_index = script_content.find('[')
    end_index = script_content.rfind(']') + 1
    json_like_content = script_content[start_index:end_index]
    data = json.loads(json_like_content)

    for item in data:
        if 'id' in item['data']:
            id = item['data']['id']
            return id

# Adds a custom artist to the guild's list
@client.tree.command(name='add', description='Add a custom artist to the list for this server')
@app_commands.describe(artist = 'Artist username that you would like to add to the custom list for this server')
async def add_artist(interaction: discord.Interaction, artist: str):
    guild_id = interaction.guild.id
    conn = create_db_connection()
    c = conn.cursor()

    # Check if the artist is valid
    url = f'https://soundcloud.com/{artist}'
    resp = requests.get(url)

    if resp.status_code == 404:
        await interaction.response.send_message(f"Invalid artist ***{artist}***. The artist doesn't exist on SoundCloud.")
        return
    
    artist_id = get_artist_id(resp)
    artist_name = artist

    c.execute('SELECT artist_id FROM artists WHERE guild_id = ? AND artist_id = ?', (guild_id, artist_id))
    existing_entry = c.fetchone()

    if existing_entry is None:
        # Fetch the latest track ID from SoundCloud API for this artist
        latest_track_id = get_latest_track_id(artist_id)
        if latest_track_id is None:
            await interaction.response.send_message(f"Failed to fetch the latest track ID for ***{artist_id}***.")
            return

        # Convert guild_id and artist_id to int
        guild_id = int(guild_id)
        artist_id = int(artist_id)
        # Convert latest_track_id to int if it is not None
        latest_track_id = int(latest_track_id) if latest_track_id else None

        c.execute('INSERT INTO artists (guild_id, artist_id, latest_track_id, artist_name) VALUES (?, ?, ?, ?)', (guild_id, artist_id, latest_track_id, artist_name))
        conn.commit()
        await interaction.response.send_message(content=f"Added ***{artist_name}*** to the list of custom artists for this server.")
    else:
        await interaction.response.send_message(content=f"***{artist_name}*** is already in the list of custom artists for this server.")

    conn.close()

# Removes a custom artist from the guild's list
@client.tree.command(name='remove', description='Remove a custom artist from the list for this server')
@app_commands.describe(artist='Artist username that you would like to remove from the custom list for this server')
async def remove_artist(interaction: discord.Interaction, artist: str):
    guild_id = interaction.guild.id
    conn = create_db_connection()
    c = conn.cursor()

    # Get artist ID based on the artist's name
    c.execute('SELECT artist_id FROM artists WHERE guild_id = ? AND artist_name = ?', (guild_id, artist))
    artist_id = c.fetchone()

    if artist_id:
        c.execute('DELETE FROM artists WHERE guild_id = ? AND artist_id = ?', (guild_id, artist_id[0]))
        conn.commit()
        conn.close()
        await interaction.response.send_message(f"Removed ***{artist}*** from the list of custom artists for this server.")
    else:
        await interaction.response.send_message(f"***{artist}*** is not found in the list of custom artists for this server.")

# Lits all artist_ids being checked for new tracks
@client.tree.command(name='list', description='Get a list of artists currently being checked for new tracks')
async def list_artists(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    conn = create_db_connection()
    c = conn.cursor()
    c.execute('SELECT artist_name FROM artists WHERE guild_id = ?', (guild_id,))
    artist_names = [row[0] for row in c.fetchall()]
    conn.close()  # Close the connection after fetching data

    if len(artist_names) == 0:
        await interaction.response.send_message("There are no custom artists added for this server")
    else:
        artists = "\n".join(artist_name for artist_name in artist_names)
        await interaction.response.send_message(f"List of custom artists being checked:\n```\n{artists}\n```")

# Help command which lists all the commands and it's capabilities
@client.tree.command(name="help", description="Get the list of available commands in SoundCloud Notify")
async def help(interaction: discord.Interaction):
    prefix = "/"
    help_embed = discord.Embed(
        title="SoundCloud Notify Bot Help",
        description="Here's a list of available commands:",
        color=discord.Color.blue()
    )

    commands_info = [
        (f"{prefix}add [artist]", "Add a custom artist to the list for this server"),
        (f"{prefix}remove [artist]", "Remove a custom artist from the list for this server"),
        (f"{prefix}list", "List all artists being checked for new tracks")
    ]

    for command, description in commands_info:
        help_embed.add_field(
            name=f"**{command}**",
            value=f"{description}\n",
            inline=False
        )

    help_embed.set_footer(text="[artist] is the appropriate artist username")

    await interaction.response.send_message(embed=help_embed)

# Main function to check for new tracks and notify channels
async def check_for_new_tracks(conn):
    await client.wait_until_ready()
    async with aiohttp.ClientSession() as session:
        while not client.is_closed():
            try:
                for guild in client.guilds:
                    guild_id = guild.id
                    c.execute('SELECT artist_id FROM artists WHERE guild_id = ?', (guild_id,))
                    artist_ids = [row[0] for row in c.fetchall()]

                    for artist_id in artist_ids:
                        await check_artist_tracks(session, conn, guild_id, artist_id)  # Pass the connection to check_artist_tracks
            except Exception as e:
                print(f"Error during track checking: {e}")

            await asyncio.sleep(3)

@client.event
async def on_ready():
    print(f"\nWe have logged in as {client.user}")

    # Create or connect to the SQLite database
    conn = create_db_connection()

    # Fetch and store the latest track ID for each artist in the database
    for guild in client.guilds:
        guild_id = guild.id
        c.execute('SELECT artist_id FROM artists WHERE guild_id = ?', (guild_id,))
        artist_ids = [row[0] for row in c.fetchall()]

        for artist_id in artist_ids:
            latest_track_id = get_latest_track_id(artist_id)
            if latest_track_id is not None:
                c.execute('UPDATE artists SET latest_track_id = ? WHERE guild_id = ? AND artist_id = ?', (latest_track_id, guild_id, artist_id))
                conn.commit()

    # Syncing slash commands 
    try:
        synced = await client.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(e)
        
    # Start the background task to check for new tracks
    client.loop.create_task(check_for_new_tracks(conn))  # Pass the connection to the background task

    print("Database Connection Status:", conn is not None)

@client.event
async def on_guild_join(guild):
    print(f"Joined new guild: {guild.name} ({guild.id})")

client.run(DISCORD_TOKEN)