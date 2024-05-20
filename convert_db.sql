-- Converts V0 database to V1 database

ALTER TABLE artists RENAME TO original_table;

CREATE TABLE IF NOT EXISTS artists (
    artist_id INTEGER PRIMARY KEY,
    artist_name TEXT,
    latest_track_id INTEGER
);

INSERT INTO artists (artist_id, artist_name, latest_track_id)
SELECT artist_id, artist_name, MAX(latest_track_id) AS latest_track_id
FROM original_table
GROUP BY artist_id, artist_name;

CREATE TABLE IF NOT EXISTS artist_guilds (
    id INTEGER PRIMARY KEY,
    artist_id INTEGER,
    guild_id INTEGER,
    FOREIGN KEY (artist_id) REFERENCES artists (artist_id),
    FOREIGN KEY (guild_id) REFERENCES guilds (guild_id)
);

INSERT INTO artist_guilds (artist_id, guild_id)
SELECT artist_id, guild_id
FROM original_table;