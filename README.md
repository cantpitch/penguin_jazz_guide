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

4. **Create your config**

   ```bash
   cp config.example.toml config.toml
   ```

   Then edit `config.toml`:

   ```toml
   [discogs]
   token = "YOUR_DISCOGS_TOKEN"
   country_preference = ["US", "Japan", "Europe", "UK"]

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
4. Show the tracklist and, on confirmation, append **one row per track** to the
   next available rows of the sheet with the columns:
   `Listened | Artist Name | Album Name | Song Name | Album URL`.

The header row is created automatically if the worksheet is empty. The
`Listened` and `Album URL` columns are left blank for you to fill in manually.

## Troubleshooting Google Sheets access

If you see `Google Sheets error: Failed to open Google Sheet`, check:

* The sheet is shared with the `client_email` value from your service account
  JSON file.
* `google.spreadsheet_id` contains only the ID from the URL, not the full URL.
* The Google Sheets API and Google Drive API are enabled in the service
  account's Google Cloud project.
* `google.service_account_file` points to the correct JSON key file. Relative
  paths are resolved from the folder containing `config.toml`.

# Development

```bash
uv sync --extra dev
uv run pytest
```
