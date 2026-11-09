# Procreate Tools

Extract PNG previews from `.procreate` files, or recover individual canvases from a completed local iPad backup. Everything runs offline using Python's standard library.

| Tool | Input | Output |
| --- | --- | --- |
| `extract_previews.py` | A `.procreate` file or folder | Embedded PNG previews |
| `archive_library.py` | A completed, unencrypted Finder/iPad backup | Verified `.procreate` files in dated folders |

**Python 3.11 or newer. No packages to install.** Tested locally on macOS; automated tests cover synthetic backups and files. This is an unofficial project, unaffiliated with Procreate.

## Get started

Download this repository with **Code → Download ZIP**, then extract it. Or clone it:

```sh
git clone https://github.com/jpwhitaker/procreate-tools.git
cd procreate-tools
```

Open a terminal in the downloaded folder. On Windows, use `py -3` instead of `python3` in the commands below. Quote paths that contain spaces.

## Extract PNG previews

You only need **[extract_previews.py](extract_previews.py)** for this feature.

```sh
python3 extract_previews.py "/path/to/artwork" --output "./previews"
```

For one file:

```sh
python3 extract_previews.py "/path/to/Drawing.procreate" --output "./previews"
```

Include subfolders and preserve their structure:

```sh
python3 extract_previews.py "/path/to/artwork" --output "./previews" --recursive
```

The script copies the embedded `QuickLook/Thumbnail.png` from each document without changing its pixels. Previews are often around 1,024 pixels on the long edge; the actual resolution and orientation are whatever Procreate stored. They are lower-resolution previews, not full-resolution layer renders. Animated canvases produce a still image.

Each PNG keeps the artwork's base filename. Existing identical PNGs are skipped; different existing files are never overwritten. Missing or invalid thumbnails are reported individually, and any failures produce a nonzero exit code.

To save a report as well:

```sh
python3 extract_previews.py "/path/to/artwork" --output "./previews" --report "./preview-report.json"
```

Reports include local paths. They are never overwritten; use a new filename or omit `--report` when repeating a run.

## Recover canvases from an iPad backup

This workflow avoids selecting and exporting every canvas on the iPad. It uses `archive_library.py` and `procreate_backup.py` together.

### 1. Make a local backup

Create a local iPad backup using Finder on macOS or Apple's device-backup tools on Windows, then wait for it to finish. See [Apple's Mac backup instructions](https://support.apple.com/108796).

The extractor currently supports **unencrypted backups only**. Unencrypted backups are not password-protected and omit some sensitive device data. Encrypted backup decryption is not implemented.

Locate the device folder containing `Manifest.db`, `Manifest.plist`, and `Status.plist`. On macOS, Finder's **Manage Backups** dialog can reveal a backup in Finder. The usual parent directory is:

```text
~/Library/Application Support/MobileSync/Backup/
```

### 2. Extract the artwork

```sh
python3 archive_library.py \
  --backup "/path/to/device-backup-folder" \
  --output "./artwork-backups"
```

On Windows, enter this as one line with `py -3`. The output disk must support hard links, such as APFS or NTFS; exFAT is not supported for this step.

Each backup gets a folder containing:

```text
artwork-backups/
  <device-id>/
    <backup-date-in-UTC>/
      canvases/       # Individual .procreate files
      verification/   # Per-canvas checksums and metadata
      catalog.json    # Canvas inventory
      complete.json   # Written after the whole run succeeds
```

Filenames include canvas IDs so artwork with identical names remains distinct. The original document bytes, layer files, and stored time-lapse files are preserved. The script checks archive members against the source with SHA-256 before marking the run complete.

### 3. Check recovery and make previews

Import representative recovered canvases into Procreate and check their appearance, layers, and time-lapse. Keep the original iPad backup too. The format is undocumented and may change between app versions.

To generate preview PNGs, run `extract_previews.py` against the new `canvases` folder.

## Repeat runs and storage

- The source backup is read-only. Do not run another device backup during extraction.
- Repeating the same completed backup verifies existing archives against their source and resumes missing canvases.
- Each new device backup creates a separate full artwork snapshot. There is no deduplication, automatic retention policy, or deletion.
- The script checks free space before extraction and keeps a 2 GB reserve in its estimate.
- These scripts process files already on the computer. They do not connect to the iPad, start backups, install schedules, or bypass device-passcode prompts.

The canvas extractor does not recreate gallery stacks, export a brush library, or restore every Procreate setting.

## If a run fails

Read the error before retrying. Incomplete or encrypted backups are rejected. Missing source data, changed backups, checksum failures, and conflicting output files also stop extraction.

A hard crash can leave `.running` or `.partial` files. Inspect them and confirm no extractor is running before removing those generated files. A `.procreate` file without its verification receipt also requires inspection: the script refuses to overwrite it. Do not remove files from the source backup to resolve an extraction error.

## Development

```sh
python3 -m unittest -v test_extract_previews test_archive_library
```

Tests use temporary synthetic documents. They check exact byte preservation, repeat runs, corruption detection, missing data, and incomplete backup rejection.

Please use synthetic files in bug reports. Artwork, backup databases, and generated reports can contain private information.

## Related projects

- [Procreate Thumbnails Extractor](https://github.com/raffe1234/Procreate-Thumbnails-Extractor) — other scripts for extracting embedded PNG previews.
- [Procreate Exporter](https://github.com/alcor6502/Procreate-Exporter) — reconstructs canvases from previously extracted backup data.

## License

[MIT](LICENSE).
