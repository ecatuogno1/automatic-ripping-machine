# The arm.yaml config file

This is the config file for almost all changeable settings of ARM, all of these are very well documented in the file itself.  

The default location for this file is `/etc/arm/config/arm.yaml`
 
However for clarity they are listed here.

They include 

  - UDF disc check
  - Contacting [OMdb](http://www.omdbapi.com/)/auto identify movies or series
  - HandBrake Settings (profile, arguments, and file extention)
  - MakeMKV settings (rip method, arguments)
  - A manual wait time (useful for overriding the OMdb identify or disc mode)
  - Enable or disable ripping of the same disc
  - Media directory settings (identified, unidentified, raw disc files locations)
  - All of the logging level settings and directory
  - The ARM web-server ip and port
  - Emby notification/server details (allowing emby refresh after rips)
  - Notification settings (Pushbullet, IFTTT, Pushover)
  - The location of your [apprise.yaml](https://github.com/automatic-ripping-machine/automatic-ripping-machine/wiki/apprise.yaml) (allows notifications to Discord, Slack, Telegram, Kodi, and lots of others)



You can view the full sample file here  [arm.yaml](https://github.com/automatic-ripping-machine/automatic-ripping-machine/blob/main/setup/arm.yaml)

## IMDb id in folder and file names

By default ARM names a movie or series folder, and the main feature file in it, `Title (Year)`. Media servers
match such names by searching for the title, which can pick the wrong film when titles are shared. Set
`IMDB_ID_IN_NAME` to add the job's IMDb id in the form your media server reads:

| `IMDB_ID_IN_NAME` | Folder / main feature name           | Read by        |
|-------------------|--------------------------------------|----------------|
| `""` (default)    | `The Matrix (1999)`                  |                |
| `"jellyfin"`      | `The Matrix (1999) [imdbid-tt0133093]` | Jellyfin       |
| `"plex"`          | `The Matrix (1999) {imdb-tt0133093}`   | Plex           |

The id is only added when the job has one: identified through OMDb or TMDB, or chosen in the web UI title search.
A title typed in with "Custom title" has no id of its own, so it is named `Title (Year)`.
