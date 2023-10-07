# SoundCloud Notify

Bot Status: **Online**

## Add this bot to your server!

- You can add the bot to your server [here](https://discord.com/api/oauth2/authorize?client_id=1130997040579620935&permissions=274877959184&scope=bot)!
- And please [report](https://github.com/adithayyil/sc-notify/issues) any bugs, thanks!



## Features

- Monitors SoundCloud artists and notifies users of new track uploads
- Utilizes Discord's API to send notifications to specific channels
- Fetches and displays metadata about the newly uploaded tracks
- Authorizes stream URL and auto uploads newly uploaded tracks
- Allows users to add and remove custom artists to monitor
- Supports listing all artists being checked for new tracks
- Provides a user-friendly help command for command explanations
- Uses asynchronous programming for efficient bot operations
- Uses SQLite database for storing custom artist data per server
- Background task to regularly check for new tracks
- Handles rate-limiting and exceptions for reliable performance

## Example

![LILAC-EXAMPLE](https://github.com/adithayyil/sc-notify/assets/90326965/b125a70f-6b79-4d85-a2c4-f8da290b5830)

## Todo

- [x] Figure out a way to handle artwork_url processing times
- [ ] When initial track amount = 0, store previous_track_id as NULL & add handling to checking
- [x] Find out if there is a way to upload music stream to discord
- [x] Add client based custom artist lists to check (with commands) [**IMPORTANT**]
  - Seperate and store each user lists of specific servers using server IDs
  - Make use of SQLite3 somehow to store and organize data
- [x] URL/Artist UserID as input instead of user ID, then convert to user ID and store in DB
- [x] Better handling for commands and change to shorter commands (length)
- [ ] Fix art_url retrieving as NULL -- add handling and await when art is processing
- [x] Utilize slash commands
- [ ] Add ability to 'link' commands to /help embed
- [ ] Fix and handle Database locking (important)

