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

## Notification script and job webhook

### BASH_SCRIPT

`BASH_SCRIPT` is run with `bash` for every ARM notification. It gets two arguments, the notification title and
body. The job the notification is about is described in these environment variables (each is empty when it is
not known yet, and none are set for messages without a job, such as a failure during job setup):

| Variable          | Contents                                                        |
|-------------------|-----------------------------------------------------------------|
| `ARM_JOB_ID`      | Job id, as shown in the web UI                                  |
| `ARM_TITLE`       | Title of the movie, series or album                             |
| `ARM_YEAR`        | Year                                                            |
| `ARM_VIDEO_TYPE`  | `movie`, `series`, `unknown` ...                                |
| `ARM_IMDB_ID`     | IMDb id, e.g. `tt0133093`                                       |
| `ARM_DISCTYPE`    | `dvd`, `bluray`, `music`, `data` ...                            |
| `ARM_LABEL`       | Disc label                                                      |
| `ARM_OUTPUT_PATH` | Folder the job's files are moved to                             |
| `ARM_STATUS`      | Job status when the notification was sent (`ripping`, `fail` ...) |

Example script that only acts on finished movie rips:

```bash
#!/usr/bin/env bash
# $1 = title, $2 = body
if [ "$ARM_VIDEO_TYPE" = "movie" ] && [ -n "$ARM_OUTPUT_PATH" ]; then
    echo "$(date) job $ARM_JOB_ID: $ARM_TITLE ($ARM_YEAR) in $ARM_OUTPUT_PATH" >> /home/arm/logs/finished.log
fi
```

### JOB_WEBHOOK_URL

When `JOB_WEBHOOK_URL` is set, ARM sends one HTTP `POST` to it when a job has finished, after the job's final
status is saved. The body is JSON:

```json
{
  "event": "job_completed",
  "job": {
    "job_id": 42, "status": "success", "title": "The Matrix", "year": "1999", "video_type": "movie",
    "imdb_id": "tt0133093", "disctype": "bluray", "label": "THE_MATRIX", "path": "/home/arm/media/completed/movies/The Matrix (1999)",
    "start_time": "2025-01-01T20:00:00", "stop_time": "2025-01-01T21:10:00", "job_length": "1:10:00", "errors": null,
    "tracks": [{"track_number": "0", "length": 8160, "filename": "title_t00.mkv", "ripped": true, "main_feature": true}]
  }
}
```

`event` is `job_completed` for a successful job and `job_failed` otherwise. `job` holds all of the job's database
fields (the example is shortened) and its tracks. The job's configuration is never sent, since it contains API keys
and passwords. ARM waits `JOB_WEBHOOK_TIMEOUT` seconds (default 10) for an answer; a webhook that fails or times out
is logged and does not change the job's result.
