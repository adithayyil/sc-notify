import discord
import requests
import asyncio
import json
from dotenv import load_dotenv
import os
from datetime import datetime


load_dotenv()

DISCORD_TOKEN = f"{os.getenv('DISCORD_TOKEN')}"
SOUNDCLOUD_CLIENT_ID = f"{os.getenv('SOUNDCLOUD_CLIENT_ID')}"


with open('users.json', 'r') as file:
    SOUNDCLOUD_USERS = json.load(file)

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

client = discord.Client(intents=discord.Intents.default())

previous_track_ids = {user: None for user in SOUNDCLOUD_USERS}

async def fetch_track_with_stream_url(user_id):
    while True:
        url = f'https://api-v2.soundcloud.com/users/{user_id}/tracks'
        response = requests.get(url, params=tracks_params, headers=headers)
        if response.status_code == 200:
            tracks_data = response.json()
            # Check if the stream_url_unauthorized is available in the tracks data
            if all('media' in track and 'transcodings' in track['media'] and len(track['media']['transcodings']) > 1 for track in tracks_data['collection']):
                return tracks_data
        await asyncio.sleep(2)  # Wait for a short duration before retrying


def authorize_stream_url(stream_url_unauthorized, track_authID):
    track_params = {
        'client_id': SOUNDCLOUD_CLIENT_ID,
        'track_authorization': track_authID,
    }

    stream_url = requests.get(
        stream_url_unauthorized,
        params=track_params,
        headers=headers,
    ).json()['url']

    return stream_url

def download_stream_url(url):
    response = requests.get(url)
    if response.status_code == 200:
        with open("temp.mp3", "wb") as file:
            file.write(response.content)
        return True
    return False

async def notify_channel(user, track):
    # Gets a bunch of track data from 'tracks'
    track_title = track.get('title')
    track_url = track.get('permalink_url')
    track_art_url = track.get('artwork_url')
    track_ogart_url = track_art_url.replace("large", "original") if track_art_url and "large" in track_art_url else track_art_url
    track_createdAt_unformatted = track.get('created_at')
    track_createdAt_formatted = datetime.strptime(track_createdAt_unformatted, '%Y-%m-%dT%H:%M:%SZ').strftime('%A, %B %d, %Y %I:%M:%S %p -0400')
    track_description = track.get('description')
    track_id = track.get('id')
    track_iscommentable = track.get('commentable')

    # Only sends notifications to target channel 'notifications'
    target_channel = discord.utils.get(client.get_all_channels(), name='notifications')
    if target_channel:
        # Sends music data
        await target_channel.send(f"New Upload from **{user}**\n\n**Upload Title:** {track_title}\n**Release Date & Time:** {track_createdAt_formatted}\n**Description:** {track_description}\n**Track ID:** {track_id}\n**Is Track Commentable?:** {track_iscommentable}\n**Artwork URL:** {track_ogart_url}\n**Link:** <{track_url}> ")

        # Use stream url here
        track_authID = track.get('track_authorization')
        stream_url_unauthorized = track['media']['transcodings'][1]['url']
        stream_url = authorize_stream_url(stream_url_unauthorized, track_authID)

        if download_stream_url(stream_url):
            # Sends .mp3
            with open("temp.mp3", "rb") as music_file:
                await target_channel.send(file=discord.File(music_file, filename=f"{track_title}.mp3"))
            os.remove("temp.mp3")
    else:
        print("Error: Channel 'notifications' not found.")

def update_previous_track_id(user, track_id):
    previous_track_ids[user] = track_id

async def check_new_tracks():
    await client.wait_until_ready()
    while not client.is_closed():
        for user, user_id in SOUNDCLOUD_USERS.items():
            tracks_data = await fetch_track_with_stream_url(user_id)
            if tracks_data:
                latest_track_id = None
                for track in tracks_data['collection']:
                    track_id = track['id']
                    if latest_track_id is None or track_id > latest_track_id:
                        latest_track_id = track_id
                    if previous_track_ids[user] is None:
                        previous_track_ids[user] = latest_track_id
                    elif track_id > previous_track_ids[user]:
                        await notify_channel(user, track)
                        update_previous_track_id(user, track_id)
                # Update the latest track ID for the user
                update_previous_track_id(user, latest_track_id)
            else:
                print(f"Error: Unable to fetch tracks for {user}")

        # Check for new tracks every 1s
        await asyncio.sleep(1)

@client.event
async def on_ready():
    print(f"We have logged in as {client.user}")
    # Start the background task to check for new tracks
    client.loop.create_task(check_new_tracks())

client.run(DISCORD_TOKEN)