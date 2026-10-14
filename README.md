# Penguin Jazz Guide Python Utility

This project is designed to download album details from discogs.com and 
add them to a Google Sheet so you can track progress, notes, etc.

# Implementation Notes

* Use the discogs.com API for album information
    * Use the Python library for discogs.com available here: https://github.com/joalla/discogs_client
    * Use token-based authentication
    * discogs.com API information available here: https://www.discogs.com/developers?srsltid=AfmBOorzN6XRFmK8J4IF8NVJpTqXlMzzrSc9S1zjA_Tz6urON7WxMDDZ
* The Google Sheet will have at least the following columns starting from the left side:
    * Listened (indicates if the user has listened to the song. blank by default)
    * Artist Name (the named artist from the book)
    * Album Name (the album name from discogs)
    * Song Name (the song name from discogs)
    * Album URL (spotify/youtube/etc. Manually entered)
* Workflow:
    * Run the script which requests an artist name and album search information. 
    * That information is run against discogs.com to find possible matches.
    * If more than one is available present a list with album name, issue date, and country of release that the user can manually select.
    * Download the album song list and upload into the next available row in the google sheet.
    * Search Spotify for the selected album and put the album URL in the first track row if found.
* Only interested in CDs. Preferably US, but sometimes rely on Japan, Europe, etc. releases.
* Configuration should be available to specify google sheet, discogs.com api key, and any other required config information.

# Setup

This project uses [uv](https://docs.astral.sh/uv/) and Python 3.12.

1. **Install dependencies**

   ```bash
   uv sync
   ```

2. **Get a Discogs token**

   Create a personal access token at
   https://www.discogs.com/settings/developers.

3. **Create a Google service account**

   * In the [Google Cloud Console](https://console.cloud.google.com/), enable
     the **Google Sheets API** and **Google Drive API**.
   * Create a **service account** and download its JSON key file.
   * Share your target Google Sheet with the service account's email address
     (found in the JSON file) so it has edit access.

4. **Optional: create a Spotify app**

   Spotify album URL lookup uses the Client Credentials flow. Create an app at
   https://developer.spotify.com/dashboard and copy its client ID and client
   secret. If Spotify credentials are omitted, the tool skips Spotify lookup and
   still uploads the album to Google Sheets.

   For playlist mode (`--playlist`), also add the redirect URI
   `http://127.0.0.1:8888/callback` to the app's settings in the Spotify
   dashboard. Apps in Development Mode need the app owner to have Spotify
   Premium, and any other account that uses the app must be added under the
   app's *Users Management*.

5. **Create your config**

   ```bash
   cp config.example.toml config.toml
   ```

   Then edit `config.toml`:

   ```toml
   [discogs]
   token = "YOUR_DISCOGS_TOKEN"
   country_preference = ["US", "Japan", "Europe", "UK"]

   [spotify]
   client_id = "YOUR_SPOTIFY_CLIENT_ID"
   client_secret = "YOUR_SPOTIFY_CLIENT_SECRET"

   [google]
   service_account_file = "service_account.json"
   spreadsheet_id = "YOUR_SPREADSHEET_ID"   # from the sheet URL
   worksheet_name = "Sheet1"
   ```

   `config.toml` and `service_account.json` are git-ignored so your secrets
   stay local.

# Usage

```bash
uv run penguin-jazz-guide          # uses ./config.toml
uv run penguin-jazz-guide -c path/to/config.toml
```

The tool will:

1. Prompt for an artist name and album search text.
2. Search Discogs for matching **CD** releases (US preferred, then Japan,
   Europe, etc.).
3. If several match, present a numbered list (album, year, country) to choose
   from.
4. Search Spotify for the selected album if Spotify credentials are configured.
   If several Spotify albums match, present a numbered list to choose from. If
   none match, continue without a Spotify URL.
5. Show the tracklist and, on confirmation, append **one row per track** to the
   next available rows of the sheet with the columns:
   `Listened | Artist Name | Album Name | Song Name | Album URL`.

The header row is created automatically if the worksheet is empty. The
`Listened` column is left blank for you to fill in manually. When Spotify lookup
finds a selected album, the Spotify album URL is written only to the `Album URL`
cell on the first track row for that album.

## Adding an album to a Spotify playlist

```bash
uv run penguin-jazz-guide --playlist
```

Album search and selection work the same as above (Discogs, then Spotify).
Instead of writing to the sheet, the tool then:

1. Shows the Spotify album's tracklist.
2. Lists the playlists you own or collaborate on. Pick one by number, or
   enter `n` to name a new playlist (default name: `Penguin Jazz Guide`).
3. On confirmation, adds every track on the album to the playlist. New
   playlists are created only after you confirm and are private by default.

The first run opens a browser to log in to Spotify. The token is cached in
`.spotify_token.json` next to `config.toml` (git-ignored) and refreshed
automatically. Playlist mode needs no Google settings.

### Adding to both the sheet and a playlist

```bash
uv run penguin-jazz-guide --playlist --sheet
```

With `--sheet` (`-s`), the tool first writes the album to the sheet as usual,
then adds the same Spotify album to a playlist. Cancelling the sheet write
also skips the playlist. This mode needs both the Google and Spotify settings.
`--sheet` only works together with `--playlist`.

## Troubleshooting Google Sheets access

If you see `Google Sheets error: Failed to open Google Sheet`, check:

* The sheet is shared with the `client_email` value from your service account
  JSON file.
* `google.spreadsheet_id` contains only the ID from the URL, not the full URL.
* The Google Sheets API and Google Drive API are enabled in the service
  account's Google Cloud project.
* `google.service_account_file` points to the correct JSON key file. Relative
  paths are resolved from the folder containing `config.toml`.
* If the message says it cannot read the service-account JSON file, move the
  key into a readable folder and update `google.service_account_file`.
* If the message says Google denied access to the spreadsheet, share the sheet
  with the service account's `client_email` and give it Editor access.

# Development

```bash
uv sync --extra dev
uv run pytest
```
