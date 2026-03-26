# Spotify MCP

## Purpose
Provides deep integration with Spotify for music playback, search, and playlist management.

## SOPs (Standard Operating Procedures)
The agent follows strict rules for Spotify:
1. **Check State**: Always call `get_playback_state` before attempting to play music.
2. **Context vs Track**: Prefer playing an album or artist (`context_uri`) over a single track (`uris`) for a continuous experience.
3. **Device Check**: Ensure a device is active before sending playback commands.

## Tools
- `playback_control`: Play, pause, next, previous.
- `playback_mode`: Repeat, shuffle.
- `spotify_search`: Search tracks, artists, albums, playlists.
- `create_playlist` / `add_to_playlist`: Manage user collections.
- `get_lyrics`: Fetches lyrics for the current or specified track.

## Data Requirement
Requires a `data/spotify_secrets.json` file with valid OAuth tokens and client credentials.

## Examples
- "Play some jazz" -> Searches for a jazz playlist/artist and starts playback.
- "What song is this?" -> Calls `get_playback_state`.
- "Create a workout playlist" -> Calls `create_playlist`.
