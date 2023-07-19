import discord
import requests
import asyncio
import json
from dotenv import load_dotenv
import os

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

params = {
    'representation': '',
    'client_id': SOUNDCLOUD_CLIENT_ID,
    'limit': '1000',
    'app_version': '1689322736',
    'app_locale': 'en',
}

client = discord.Client(intents=discord.Intents.default())

# Dictionary to store the previous fetched track IDs for each user
previous_track_ids = {user: None for user in SOUNDCLOUD_USERS}

def fetch_tracks(user_id):
    url = f'https://api-v2.soundcloud.com/users/{user_id}/tracks'
    response = requests.get(url, params=params, headers=headers)
    if response.status_code == 200:
        return response.json()
    return None

async def check_new_tracks():
    await client.wait_until_ready()
    while not client.is_closed():
        for user, user_id in SOUNDCLOUD_USERS.items():
            tracks_data = fetch_tracks(user_id)
            if tracks_data:
                latest_track_id = None
                for track in tracks_data['collection']:
                    track_id = track['id']
                    if latest_track_id is None or track_id > latest_track_id:
                        latest_track_id = track_id
                    if previous_track_ids[user] is None:
                        previous_track_ids[user] = latest_track_id
                    elif track_id > previous_track_ids[user]:
                        track_title = track.get('title')
                        track_url = track.get('permalink_url')
                        track_art_url = track.get('artwork_url')
                        track_ogart_url = track_art_url.replace("large", "original") if "large" in track_art_url else track_art_url
                        track_createdAt = track.get('created_at')
                        track_description = track.get('description')

                        # Only sends notifications to target channel 'notifications'
                        target_channel = discord.utils.get(client.get_all_channels(), name="notifications")
                        if target_channel:
                            await target_channel.send(f"New Upload from **{user}**\n\n**Upload Title:** {track_title}\n**Release Date & Time:** {track_createdAt}\n**Description:** {track_description}\n**Artwork URL:** {track_ogart_url}\n**Link:** <{track_url}> ")
                        else:
                            print("Error: Channel 'notifications' not found.")   
                                                
                        # Update the previous track ID for the user
                        previous_track_ids[user] = track_id
                # Update the latest track ID for the user
                previous_track_ids[user] = latest_track_id
            else:
                print(f"Error: Unable to fetch tracks for {user}")

        # Check for new tracks every 3s
        await asyncio.sleep(3)

@client.event
async def on_ready():
    print(f"We have logged in as {client.user}")
    # Start the background task to check for new tracks
    client.loop.create_task(check_new_tracks())

client.run(DISCORD_TOKEN)