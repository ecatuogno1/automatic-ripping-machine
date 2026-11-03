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

## Keeping the ARM online database identity (KEEP_CRC_IDENTITY)

When `GET_VIDEO_TITLE` is enabled, ARM computes a DVD's crc64 and asks the ARM online database for it.
If the database knows the disc, ARM fills in its title, year and IMDb id, and then still runs the OMDb/TMDB
title search on the disc label. The first result of that search replaces the database answer, and for a generic
or misleading label it can be a different film from the same year.

Set `KEEP_CRC_IDENTITY: true` (Settings / Ripper Settings, or arm.yaml) to keep the online database answer and
skip the title search for that disc. Discs the database does not know are searched by title as usual.
The default is `false`, which always runs the title search.
