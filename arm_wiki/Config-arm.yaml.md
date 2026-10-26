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

## Completed folders per media type

By default every finished rip goes to a sub-folder of `COMPLETED_PATH`:

| Job                      | Folder                                   |
|--------------------------|------------------------------------------|
| Identified movie         | `COMPLETED_PATH/movies/Title (Year)`     |
| Identified series        | `COMPLETED_PATH/tv/Title (Year)`         |
| Unidentified video       | `COMPLETED_PATH/unidentified/<title>`    |
| Data disc (ISO image)    | `COMPLETED_PATH/unidentified/<label>`    |
| Music CD                 | `OUTPUTDIR` from [abcde.conf](Config-abcde.conf) |

If your media server keeps movies and TV in separate libraries, point these settings at them and ARM moves the
files there directly:

```yaml
COMPLETED_MOVIES_PATH: "/mnt/media/Movies"
COMPLETED_TV_PATH: "/mnt/media/TV Shows"
COMPLETED_DATA_PATH: "/mnt/media/ISO"
```

Each one that is left empty (the default) keeps the `COMPLETED_PATH` sub-folder above. Unidentified videos always
stay in `COMPLETED_PATH/unidentified`, and the transcode folder layout under `TRANSCODE_PATH` is unchanged.
With Docker, mount the library folders into the container and use the paths as the container sees them.
