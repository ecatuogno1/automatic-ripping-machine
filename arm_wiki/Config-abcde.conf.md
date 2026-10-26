# The .abcde.conf config file

 This is the config file for abcde, it only contains settings for the ripping of music CD's. 

The default location for this file is `/home/arm/.abcde.conf`

[Abcde Manual](https://linux.die.net/man/1/abcde) This is the full manual/user-guide covering each of the settings in the abcde.conf file. 
Here is some of the changes you can make with this file.

  - Metadata provider (default is musicbrainz - **Do not change this unless you know what you're doing** )
  - Output-type
    - 11 to choose from (ogg, mp3**, flac, aac, opus, etc.)
  - Output directory
  - Output formatting (artist-album or artist/album, etc.) 
  - Playlist
  - Merge CD into single track (for live albums)
  - Eject disc after rip is complete
  - Number of encoders to run at once
  - Lots of advanced settings



You can view the full file here  [.abcde.conf](https://github.com/automatic-ripping-machine/automatic-ripping-machine/blob/main/setup/.abcde.conf)


## Verifying rips with AccurateRip

Set `ACCURATERIP_VERIFY: true` in arm.yaml to check every finished music rip against the
[AccurateRip](https://www.accuraterip.com) database. ARM decodes the FLAC files abcde wrote, computes each
track's AccurateRip checksums and compares them with the checksums other people submitted for the same pressing.
The result (for example `AccurateRip: 11 of 12 tracks accurately ripped; track(s) 7 did not match`) is written to
the job log and sent as a notification. With `ACCURATERIP_FAIL_ON_MISMATCH: true` a track that does not match
fails the job (the files are kept). A disc that isn't in the database, or a lookup that fails, never fails the job.

The checks need three things in abcde.conf:

  - `OUTPUTTYPE=flac` (lossy formats can't be verified; `flac,mp3` works too)
  - an absolute `OUTPUTDIR` (the default `/home/arm/music/` is fine)
  - a rip corrected for your drive's read offset: look your drive up in the
    [AccurateRip drive offset list](https://www.accuraterip.com/driveoffsets.htm) and add it to the cdparanoia
    options, e.g. `CDPARANOIAOPTS="-O 6"` for a +6 drive. Without it every track of a drive with a non-zero
    offset will be reported as not matching.

Enhanced CDs (with a data session) are looked up by their audio tracks only and may be reported as not in
the database.
