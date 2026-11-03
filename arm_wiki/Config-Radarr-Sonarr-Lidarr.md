# Importing rips into Radarr, Sonarr and Lidarr

ARM can hand a finished rip to [Radarr](https://radarr.video/) (movies), [Sonarr](https://sonarr.tv/) (series)
or [Lidarr](https://lidarr.audio/) (music CDs), the same way a download client hands over a finished download.
The app then renames the files and moves (or copies) them into its library.

This is optional and off by default. Each app is used only when both its URL and API key are set.

## Settings

All settings are in [arm.yaml](Config-arm.yaml) and on the [Settings](Web-Settings) page, in the
"Radarr / Sonarr / Lidarr Import" section.

| Setting | Meaning |
|---|---|
| `RADARR_URL`, `RADARR_API_KEY` | Radarr address and API key, used for discs identified as a movie |
| `SONARR_URL`, `SONARR_API_KEY` | Sonarr address and API key, used for discs identified as a series |
| `LIDARR_URL`, `LIDARR_API_KEY` | Lidarr address and API key, used for music CDs |
| `ARR_IMPORT_MODE` | `Move` (default) moves the files into the library and removes ARM's copy, `Copy` leaves ARM's copy in place |
| `ARR_PATH_MAP` | Only needed when the app sees ARM's folders under a different path, see below |

The URL is the address you open the app with, including any URL base, for example `http://192.168.1.10:7878`
or `https://example.com/radarr`. The API key is in each app under **Settings > General > Security**.
ARM sends the key in the `X-Api-Key` header and never writes it to the logs.

## What happens after a rip

- **DVD / Blu-ray:** after the files were moved to the completed folder (`COMPLETED_PATH/movies/Title (Year)` or
  `COMPLETED_PATH/tv/Title (Year)`), ARM sends Radarr the `DownloadedMoviesScan` command or Sonarr the
  `DownloadedEpisodesScan` command for that folder. Discs ARM couldn't identify as a movie or series are skipped.
- **Music CD:** after abcde finished, ARM looks in abcde's `OUTPUTDIR` (from your
  [.abcde.conf](Config-abcde.conf)) for the album folder it just wrote and sends Lidarr the `DownloadedAlbumsScan`
  command for it. `OUTPUTDIR` must be a plain absolute path (the default `/home/arm/music/` is). If two CDs finish at the
  same time, or the folder can't be told apart, ARM skips the import and logs why.
- **Data discs** are never sent anywhere.

The request has a 30 second timeout. If the app is unreachable or rejects the request (for example a wrong API key),
ARM logs a warning in the job log and the job still finishes as a success. The files stay where ARM put them so
you can import them with the app's own Manual Import.

What the app does with the folder is up to the app: it imports what it can match to a movie, episode or album in its
library and leaves the rest. Check the app's **Activity** and **System > Events** if nothing shows up. In particular,
Sonarr needs episode numbers it can parse from the file names, which MakeMKV's title names usually don't have, so
series rips often need a manual import.

## "In library" label

With Radarr or Sonarr configured, the History page and the job details page show an **In library** label on a
successful job when Radarr has a file for that movie, or Sonarr has at least one episode file for that series.
Titles are matched by the job's IMDb id, so jobs without one never get the label. ARM reads each app's list at most
every two minutes; if the app can't be reached, the label is simply not shown.

## Docker and different paths

The app opens the folder ARM gives it, so it must see the same files. If ARM and the app run in different containers
or on different machines, the path may differ. Map ARM's path to the app's path with `ARR_PATH_MAP`: one or more
`ARM path=app path` pairs separated by `;`. For example, if ARM's completed folder `/home/arm/media/completed`
is mounted at `/data/completed` in Radarr and Sonarr, and ARM's music folder `/home/arm/music` at `/data/music` in Lidarr:

```yaml
ARR_PATH_MAP: "/home/arm/media/completed=/data/completed;/home/arm/music=/data/music"
```

The first pair whose ARM path the folder is under is used. Paths that match no pair are sent unchanged.
