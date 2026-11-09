# Procreate Tools

**Turn a local iPad backup into an archive of editable Procreate artwork.**

Backing up a large Procreate collection by selecting and exporting canvases in the app is tedious. A whole-device backup can protect that work, but it does not present the artwork as a folder of individual `.procreate` files that you can browse, copy, or import on their own.

This project bridges that gap. After you make a local iPad backup, it finds the Procreate canvas data inside it and reconstructs individual `.procreate` files, including their stored layers and time-lapse data. It processes the collection in a batch, saves a dated archive, and verifies each file's contents against the backup. You do not need to select and export each artwork on the iPad.

An optional second script extracts the embedded PNG previews from those files, making the archive easier to browse. **Artwork backup and recovery are the main purpose; previews are a supporting feature.**

```text
iPad → local device backup → individual .procreate files → optional PNG previews
       Finder / other tool   this project's main script    preview script
```

The scripts handle extraction and verification after the device backup is complete. Creating or scheduling the iPad backup is a separate step. Everything here runs offline; your artwork is never uploaded.

| Tool | Purpose | Input | Output |
| --- | --- | --- | --- |
| `archive_library.py` | Archive the Procreate collection | A completed, unencrypted local iPad backup | Verified `.procreate` files in dated folders |
| `extract_previews.py` | Browse the archived artwork | A `.procreate` file or folder | Embedded PNG previews |

**Python 3.11 or newer. No packages to install.** This is an unofficial project, unaffiliated with Procreate.

## Platform support and what has been tested

The extraction scripts run on macOS, Windows, and Linux. They read an existing local backup; they do not need Procreate installed on the computer or a live connection to an iPad.

| Platform | Creating the device backup | Validation so far |
| --- | --- | --- |
| macOS | [Finder](https://support.apple.com/108796) | Real iPad backup extracted, representative canvases imported into Procreate; automated tests pass |
| Windows | [Apple Devices or iTunes](https://support.apple.com/en-us/108967) | Automated extraction and preview tests pass; a real Windows-created backup has not been tested end to end here |
| Linux | Copy a completed compatible backup from another computer, or use a separate tool such as [`idevicebackup2`](https://github.com/libimobiledevice/libimobiledevice) | Automated extraction and preview tests pass; Linux device-backup creation has not been tested here |

[CI](https://github.com/jpwhitaker/procreate-tools/actions/workflows/tests.yml) runs the seven tests on all three operating systems with Python 3.11 and 3.14. These use synthetic backup data and verify file handling and recovery logic. They do not prove compatibility with every iPadOS, Procreate, or backup-tool version. A Linux backup tool's ability to connect to a particular iPad is separate from this project's extraction support.

The backup extractor needs an output filesystem that supports hard links, such as APFS, NTFS, or ext4. exFAT is not supported for backup extraction. The standalone preview script does not have this hard-link requirement.

## Get started

Download this repository with **Code → Download ZIP**, then extract it. Or clone it:

```sh
git clone https://github.com/jpwhitaker/procreate-tools.git
cd procreate-tools
```

Open a terminal in the downloaded folder. On Windows, use `py -3` instead of `python3` in the commands below. Quote paths that contain spaces.

## Recover canvases from an iPad backup

This workflow avoids selecting and exporting every canvas on the iPad. It uses `archive_library.py` and `procreate_backup.py` together.

### 1. Make a local backup

Create a local iPad backup using the appropriate tool for your platform, then wait for it to finish. See the platform table above. On Linux, you can also work with a completed backup copied from a Mac or Windows computer.

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

On Windows, enter this as one line with `py -3`. The output disk must support hard links; see the platform requirements above.

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

## Optional: extract PNG previews

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
