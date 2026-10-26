# Disc identification

When `GET_VIDEO_TITLE` is enabled, ARM names a DVD in two steps:

1. It computes the disc's crc64 and asks the ARM online database for it.
2. It searches the configured `METADATA_PROVIDER` (OMDb or TMDB) for the disc label and takes the first result.

The first result is not always the disc's film. A label such as `THE_KINGDOM` matches several films of that
name, and a generic label can match an unrelated one.

## Confirming the title by runtime (IDENTIFY_BY_RUNTIME)

With `IDENTIFY_BY_RUNTIME: true` (Settings / Ripper Settings, or arm.yaml) ARM first tries to confirm the
identity of a DVD by the length of its longest title, as reported by `lsdvd`:

- It looks up every film named like the cleaned label, with or without a leading "The", "A" or "An"
  (`FAMILY_MAN` also matches *The Family Man*), and the runtime of each.
- A film is accepted when its runtime is within 5 minutes (or 5% for long films) of the disc and it is the only
  film that fits. If several fit, one within 2 minutes wins when every other is at least 3 minutes further off.
  A film without a known runtime, or without a release year and IMDb id, is never accepted.
- The ARM online database answer for the crc64 is a hint. It is kept when its runtime fits and the label agrees
  with it (or the label is unusable, such as `not identified`). If the label and the database name different
  films that both fit, nothing is confirmed.
- If a TV series has the label's name, the film is accepted only on a feature-length disc (75 minutes or more)
  that runs within 2 minutes of a well-known film (500 or more votes on the provider). Labels with a season
  marker (`S1`, `SEASON 2`) are left to the usual search, as is every disc while `VIDEOTYPE` is `series`.

When a film is confirmed, ARM sets the title, year, IMDb id and poster and skips the title search. When nothing
is confirmed, or the provider cannot be reached, identification continues exactly as without the setting.

The check uses the API key of the selected `METADATA_PROVIDER` and makes a few extra requests per disc
(one search, plus one details request for each film named like the label, at most 10). Blu-ray discs are
identified as before: their title length is not known until MakeMKV scans the disc.

The default is `false`.

## Skipping the manual wait for confirmed discs (MANUAL_WAIT_SKIP_VERIFIED)

With `MANUAL_WAIT` enabled, every disc waits `MANUAL_WAIT_TIME` seconds so you can correct its title in the
ARM ui. Set `MANUAL_WAIT_SKIP_VERIFIED: true` to start ripping at once when `IDENTIFY_BY_RUNTIME` confirmed the
disc's title by its runtime. Discs it did not confirm (including every Blu-ray, and every disc identified by the
usual title search) still wait. The default is `false`, which waits for every disc.
