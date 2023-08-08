# SoundCloud Notify (WIP 🛠️)

## Features

- Checks for newly added tracks for artists in SoundCloud
- Sends metadata for those newly uploaded tracks like title, date, duration, description, etc...
- Sends artist uploaded song file!

## Example

![LILAC-EXAMPLE](https://github.com/adithayyil/sc-notify/assets/90326965/b125a70f-6b79-4d85-a2c4-f8da290b5830)

## Todo

- [x] Figure out a way to handle artwork_url processing times
- [ ] Send notification when previous track amount = 0
- [x] Find out if there is a way to upload music stream to discord
- [x] Add client based custom artist lists to check (with commands) [**IMPORTANT**]
  - Seperate and store each user lists of specific servers using server IDs
  - Make use of SQLite3 somehow to store and organize data
- [x] URL/Artist UserID as input instead of user ID, then convert to user ID and store in DB
- [x] Better handling for commands and change to shorter commands (length)
- [ ] Fix art_url retrieving as NULL -- add handling and await when art is processing
