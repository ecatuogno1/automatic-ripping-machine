# Automatic Ripping Machine and MakeMKV
A.R.M. uses MakeMKV under the hood to decrypt and copy the content of optical disks (DVDs and Blu-rays).  You can find 
more information about MakeMKV in the links below.

* [MakeMKV Website](https://www.makemkv.com/)
* [MakeMKV EULA (End User Licence Agreement)](https://github.com/automatic-ripping-machine/automatic-ripping-machine/wiki/MakeMKV-EULA)
* [MakeMKV Forums](https://forum.makemkv.com/forum/)

## MakeMKV Licence
MakeMKV is free while in Beta.  However, if you wish to support this wonderful project you can do so by purchasing a 
licence from MakeMKV here: https://www.makemkv.com/buy/

If you purchased a licence key, you can enter it in the A.R.M. settings by navigating to your A.R.M. installation, 
choose "Arm Settings" from the navigation bar, go to the "Ripper Settings" tab and scroll down to the 
"MAKEMKV_PERMA_KEY" field.  In this field enter your purchased licence key. A.R.M. will make use going forward.  
If you leave the feild empty, A.R.M. will use a Beta key instead.

## MakeMKV Settings

### `settings.conf`
`makemkvcon` respects the `~/.MakeMKV/settings.conf` created by the MakeMKV GUI, which makes it possible to configure certain aspects of MakeMKV through the GUI on your Desktop.

> [!WARNING]
> It is however ***not*** recommended to simply copy an existing `settings.conf` into A.R.M.'s `~/.MakeMKV` directory as the file contains some machine-specific settings that may or may not interfere with ripping via A.R.M.

Two specific settings that may be particularly useful to create or copy are the `app_DefaultSelectionString` and `app_DefaultOutputFileName` keys, which store the GUI's ["Default selection rule"](https://forum.makemkv.com/forum/viewtopic.php?t=4386) and ["Output file name template"](https://forum.makemkv.com/forum/viewtopic.php?t=18313) under Preferences > Advanced respectively. Check the linked MakeMKV forum threads for their syntax.

> [!NOTE]
> * While the `dvd_MinimumTitleLength` (corresponding to the GUIs Preferences > Video > "Minimum title length (seconds)" setting) is harmless to create, it has no effect as it is overriden by A.R.M.'s `MINLENGTH` setting.
> * The `app_Key` should be left untouched. If you have a permanent key see [MakeMKV Licence](#makemkv-licence) above.

### Profiles
MakeMKV can also use the concept of profiles to decide which audio tracks and which subtitle tracks to include in the 
*.mkv files. The defaults are usually sufficient. However, A.R.M. allows you to change these defaults if needed.  This is 
considered advance usage of MakeMKV and A.R.M. The list below contains some information as to where to start, these 
are links to MakeMKV forum pages.
* [Conversion Profiles](https://forum.makemkv.com/forum/viewtopic.php?f=10&t=4385)
* [Changing Default Track Selection](https://forum.makemkv.com/forum/viewtopic.php?f=10&t=4386)
* [Changing Default Track Order In Output File](https://forum.makemkv.com/forum/viewtopic.php?f=10&t=4566)

You can use the information above to learn how to create an MakeMKV conversion profile xml file.  You can then go to 
your A.R.M. installation URL, choose "Arm Settings" from the navigation bar, go to the "Ripper Settings" tab and scroll 
down to the MKV_ARGS field. In this field enter `--profile=/<path-to-your-custom-makemkv-profile.mmcp.xml>` Note that 
the file location must be accessible by the arm user and must be owned by the arm user (or at the very least readable). 
It is recommended to place it in the `/home/arm/` directory.

## Reading a DVD once (`READ_ONCE_DVD`)
When MakeMKV rips every title of a DVD (`RIPMETHOD: "mkv"`, `MAINFEATURE: false`), it opens and reads each title
from the disc separately. Titles on a DVD share video cells, so the drive seeks back and forth and reads the same
parts of the disc several times. On worn discs and slow drives this is the slowest part of a rip.

With `READ_ONCE_DVD: true` A.R.M. instead:

1. copies the whole disc (the decrypted `VIDEO_TS` folder, menus included) into a new folder in `RAW_PATH` with
   [dvdbackup](https://dvdbackup.sourceforge.net/), in one sequential pass;
2. checks the copy (`VIDEO_TS.IFO` and every title set's navigation file are valid, no member is empty);
3. lets MakeMKV make the titles from the copy (`file:` source) with the usual `MKV_ARGS`, `MINLENGTH`, `MAXLENGTH`,
   `MAINFEATURE` and manual-mode track selection;
4. removes the copy. The MKV files land in the job's raw folder, named after the disc label, and the rest of the
   job (transcode, move, notifications) runs as for a rip from the disc.

If the copy can't be made (dvdbackup missing, not enough space, a read error, an incomplete copy) A.R.M. logs the
reason, removes the partial copy and rips the titles from the disc as usual. If the copy was made but MakeMKV fails
on it, the copy is kept in `RAW_PATH` (the log names the folder) and the titles are ripped from the disc.

Requirements and limits:
* `dvdbackup` must be installed (`apt install dvdbackup`); it decrypts with the same libdvdcss that HandBrake uses.
* `RAW_PATH` needs free space for about twice the disc size (the copy plus the titles).
* Discs with 99-title protection are always ripped from the disc, because their deliberately unreadable sectors
  stop dvdbackup.
* Blu-ray discs are not affected; `RIPMETHOD: "backup"` already copies a Blu-ray once and transcodes from the copy.
  MakeMKV's `backup` mode does not copy DVDs, which is why dvdbackup is used here.
