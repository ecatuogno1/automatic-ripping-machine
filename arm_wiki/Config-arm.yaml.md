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

## Spaces or dashes in titles (TITLE_SPACES)

When ARM names a job from the metadata lookup (OMDb/TMDB) or from a Blu-ray's disc title, it joins the words
with dashes, so folders and files are named `The-Matrix (1999)`. Set `TITLE_SPACES: true` to keep the spaces
instead: `The Matrix (1999)`. Titles you set yourself in the web UI already keep their spaces.

The default is `false`, so existing libraries keep their naming. Whichever you choose, ARM replaces `_`, `-` and
`+` with spaces when it searches for a title, because the providers match `The Batman` but not always `The-Batman`.
