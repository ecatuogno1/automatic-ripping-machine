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
  - Optional verification of ripped files before they are moved (see below)



You can view the full sample file here  [arm.yaml](https://github.com/automatic-ripping-machine/automatic-ripping-machine/blob/main/setup/arm.yaml)

## Verifying ripped output (VERIFY_RIP_OUTPUT)

When `VERIFY_RIP_OUTPUT: true`, ARM checks the video files with `ffprobe` after MakeMKV and HandBrake/FFmpeg
finish and before anything is moved to `COMPLETED_PATH`, deleted, or reported as complete. Each video file must:

  - open as a media file and contain video packets
  - run about as long as the disc scan reported for that title (the largest file may be up to 2 seconds or 1% shorter,
    other files up to 8 seconds or 2% shorter, and any file up to 5 seconds or 2% longer)
  - have readable, decodable video in its last 30 seconds, ending near the video track's duration
    (this catches files that were cut short but kept a full-length header)

Files other than the largest that hold only a few pictures, such as photo galleries and menu stills, are recognised
as still-image extras and are not failed for their runtime.

If any file fails, the job fails with a message naming each file and the reason, and the raw and transcode files are
kept so you can inspect or re-use them. Only the end of each file is decoded, so the check takes a few seconds to a
few minutes per disc; it is not a full decode. Folder-style backups (`RIPMETHOD: backup` with `SKIP_TRANSCODE`) are
not checked. `ffprobe` is installed with ffmpeg in the ARM docker image; if it can't be found, ARM logs a warning and
skips the check. The setting is off by default.
