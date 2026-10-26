
# Troubleshooting

## Nothing happens when i insert a disc

For me personally i had to add the `--privileged` flag to my container for it to fully work, However i'm very new to docker there may be a better work around to get it to work. But this is how i got it working.

You can check if your udev rules are working on the host machine via linux logs 

`tail -f /var/log/syslog | grep ARM`

This should show when you insert a disc
```
xxx ARM: container 'arm-rippers' status: "Up 24 seconds"
xxx ARM: Starting rip
```
If it doesnt you udev isnt setup on the host machine.

## Drives not found or discs not recognised on Debian 13 (Trixie)
Seen on Debian 13 hosts, including OpenMediaVault and Proxmox VMs based on it, where the same container worked on Debian 12. Any of these can happen:
- The Drives page shows no drives, or drives that are "not available"
- Inserting a disc does nothing, or the log says the disc type could not be determined (older versions: `Not CD, Blu-ray, DVD or Data. Bailing out`)
- An audio CD logs `mount: wrong fs type` and never starts ripping

The cause is an incomplete udev database inside the container. ARM reads the disc type from udev (the `ID_CDROM_MEDIA_*` properties), so when they are missing it can't tell what was inserted. With a disc in the drive, compare the host and the container (use your drive and container names):
```
sudo udevadm info --query=property --name=/dev/sr0
sudo docker exec arm-rippers udevadm info --query=property --name=/dev/sr0
```
If the container's list is much shorter and has no `ID_CDROM_MEDIA_*` lines, give the container the host's udev database, read-only, and pass the drive's SCSI generic device as well. `lsscsi -g` shows both devices of each drive:

`[2:0:0:0]    cd/dvd  HL-DT-ST BD-RE BP60NB10   1.02  /dev/sr0   /dev/sg0`

Add to your `start_arm_container.sh`:
```
    -v "/run/udev:/run/udev:ro" \
    --device="/dev/sr0:/dev/sr0" \
    --device="/dev/sg0:/dev/sg0" \
```
or, with docker compose:
```
    volumes:
      - /run/udev:/run/udev:ro
    devices:
      - /dev/sr0:/dev/sr0
      - /dev/sg0:/dev/sg0
```
Use the `/dev/sg#` that `lsscsi -g` lists on the same line as each `/dev/sr#`; the numbers often differ (e.g. `/dev/sr0` and `/dev/sg5`). Recreate the container afterwards (stop and remove it, then run the script again) and repeat the `udevadm` check.

Some users report that udev inside the container takes a minute or more, with high CPU, to start on these hosts. That is a separate problem from the drive detection.

## MakeMKV cant find drives
MakeMKV requires both drive identifiers to be passed into the container for example if `lsscsi -g` outputs

`cd/dvd  TEAC     DVD-ROM DV28SV   R.0C  /dev/sr0   /dev/sg5 `

You will need to add 
```
--device /dev/sr0
--device /dev/sg5
```
to the docker run command

Failing to do so may mean that the rest of ARM can find the drive but MakeMKV fails as it uses  SCSI commands to interact with the drive

## Docker is adding jobs but no files are created
Check the docker to make sure both the UID and GID match to a user outside the container, and the user has write permissions to the media directory.
You may need to chmod your media/music directories outside the container. 

## Changing where the docker puts files
**DO NOT try to change these paths in the arm.yaml** 

Instead change the containers volume paths. 
These can be changed to suit your needs
```
    -v "/my-music-path:/home/arm/Music" \
    -v "/my-config-path:/home/arm/config" \
    -v "/my-logs-path:/home/arm/logs" \
    -v "/my-media-path:/home/arm/media" \
```

## My volume paths point to a CIFS mount - but now the database is locked
This is caused by a byte-range lock on the mount by default.
To fix this, the CIFS mount of your host needs the `nobrl` flag. 

## NVENC doesn't work

Be sure that both variables for `NVIDIA_DRIVER_CAPABILITIES=all`
and `--gpus all` are set as NVENC won't work without them