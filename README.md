# ProSave

ProSave saves the Procreate artwork from an iPad backup as individual, editable `.procreate` files, including stored layers and time-lapse data. This lets you back up your gallery without selecting and exporting each canvas in Procreate.

First, make an iPad backup on your computer using Finder on Mac or Apple Devices on Windows. ProSave reads that backup, saves the artwork in a dated folder, and checks the saved contents against the source. It runs locally and leaves the original backup unchanged.

By default, artwork is organised into folders matching your gallery stacks. You can use `--flat` to save everything in one folder instead.

You can also extract PNG previews to browse the saved artwork. The instructions below cover both steps, including how to run ProSave if you haven't used scripts before.

- [Before you begin](#before-you-begin)
- [Mac walkthrough](#walkthrough-mac)
- [Stack folders or a flat directory](#stack-folders-or-a-flat-directory)
- [PNG previews](#optional-save-png-previews)
- [Making another backup](#making-another-backup)
- [Windows (untested)](#using-windows-untested)
- [Troubleshooting](#if-something-doesnt-work)
- [Limitations](#limitations)
- [Technical details, Linux, and tests](#technical-details)

## Before you begin

You'll need:

- Your iPad, a cable, and a computer for making the initial backup.
- Space for **both the iPad backup and the extracted artwork**. The device backup includes data from other apps too.
- **Python 3.11 or newer**, the program that runs ProSave. Installation is covered below.
- A completed **unencrypted local backup**. “Local” means saved on your computer, rather than in iCloud. “Unencrypted” means the backup isn't protected by a backup password.

ProSave can't read encrypted backups. If you already use them, read Apple's explanation of [backup encryption](https://support.apple.com/108353) before changing that setting; it affects both password protection and which device data is included.

For your first run, save the extracted artwork to your computer's built-in drive. Some external drives use a format called exFAT that ProSave's artwork extractor doesn't support. You can copy the finished artwork to an external drive afterwards.

## Walkthrough: Mac

### 1. Make an iPad backup

If you already have a completed, unencrypted backup, skip to step 2. ProSave will save the artwork as it was when that backup was made.

1. Connect your iPad to your Mac and open **Finder**.
2. Select your iPad in Finder's sidebar. Follow any **Trust This Computer** prompts.
3. In **General**, choose **Back up all of the data on your iPad to this Mac**.
4. ProSave requires **Encrypt local backup** to be unchecked. If you choose to make an unencrypted backup and Finder asks, choose **Don't Encrypt**.
5. Click **Back Up Now** and wait for it to finish. Keep the iPad connected during the backup.

Apple's [Mac backup guide](https://support.apple.com/108796) has pictures of these screens.

Once the backup has finished, ProSave no longer needs the iPad connected. Don't start another device backup while ProSave is reading this one.

### 2. Find the backup folder

In your iPad's Finder window, click **Manage Backups**. Right-click the backup you just made and choose **Show in Finder**.

The folder usually has a long name made of letters and numbers. It should contain `Manifest.db`, `Manifest.plist`, and `Status.plist`, along with other folders.

Keep this Finder window open. You'll use the entire device backup folder in step 6.

See Apple's [guide to locating backups](https://support.apple.com/108809) if you can't find it.

### 3. Download ProSave

On the [project's GitHub page](https://github.com/jpwhitaker/procreate-tools), click the green **Code** button, then **Download ZIP**. Open the downloaded ZIP to unpack it.

The downloaded folder is called `procreate-tools-main`, after the project's earlier name.

Keep the files together. The `.py` files are the scripts you'll run; you don't need to edit them.

### 4. Open Terminal and check Python

**Terminal** is the Mac app where you type a command to start ProSave.

Press **Command–Space**, type **Terminal**, and press **Return**. Copy this line into its window, then press Return:

```sh
python3 --version
```

You should see `Python 3.11` or a newer version. If Python is missing or older, or you're prompted to install developer tools, use the macOS Python installer from [python.org](https://www.python.org/downloads/macos/). Then reopen Terminal and check again.

### 5. Open the ProSave folder in Terminal

1. Type `cd` followed by a **space**. Don't press Return yet.
2. Drag the **unpacked ProSave folder** from Finder into Terminal. Its location will appear automatically.
3. Press **Return**.

`cd` tells Terminal which folder to work in. It finishes without a confirmation message.

### 6. Save your artwork

The full command is:

```sh
python3 archive_library.py --backup "<path to your iPad backup folder>" --output ./artwork-backups
```

Text inside `<angle brackets>` is a placeholder for your own information. Replace `<path to your iPad backup folder>`, including the brackets, with the folder's full location. Keep the quotation marks: they allow spaces in folder names.

To copy that location, select the device backup folder in Finder and press **Option–Command–C**. Use the folder with the long name that contains `Manifest.db`.

For example, after replacing the placeholder, the command might look like this:

```sh
python3 archive_library.py --backup "/Users/alex/Library/Application Support/MobileSync/Backup/00008101-001234567890001E" --output ./artwork-backups
```

Your username and backup folder name will be different. Enter your completed command in Terminal as one line, then press **Return**.

ProSave will read the backup and save the artwork in an `artwork-backups` folder inside your ProSave folder.

There may be a pause while ProSave reads the backup. Then you'll see progress like this example:

```text
Archiving 120 canvases (3.40 GB)
1/120 extracted: Afternoon sketch
2/120 extracted: Garden study
...
COMPLETE: 120 canvases, 2.80 GB at ...
```

Leave Terminal open and keep your Mac awake until you see **`COMPLETE`**. The numbers and names will reflect your gallery.

### 7. Find and check your saved artwork

Open the ProSave folder in Finder, then open:

**artwork-backups → your device's folder → the dated folder → canvases**

The `canvases` folder contains a subfolder for each gallery stack. Unstacked artwork sits directly in `canvases`. File and stack folder names include identifiers so repeated names remain distinct. The date uses UTC, so it may differ from your local date.

Keep the accompanying `verification` folder and `.json` files. ProSave uses these records to check its work on later runs. `layout.json` also records stack names, membership, and the original gallery order; Finder may display the files in a different order.

Send a few `.procreate` files to your iPad with AirDrop and open them in Procreate. Check their appearance, layers, and time-lapse, including a complicated drawing. This checks that the saved files open correctly; importing adds copies to your gallery.

Keep the original iPad backup. Copy the finished dated artwork folder to another drive or storage service so it isn't only on this computer.

## Stack folders or a flat directory

Stack folders are the default. For example:

```text
canvases/
  Studies--<stack-id>/
    Drawing--<canvas-id>.procreate
  Unstacked drawing--<canvas-id>.procreate
```

To put all artwork directly in `canvases`, add `--flat` to the command:

```sh
python3 archive_library.py --backup "<path to your iPad backup folder>" --output ./artwork-backups --flat
```

On Windows, use `py -3` in place of `python3`.

Each saved backup keeps the layout chosen on its first run. Older ProSave archives keep their flat layout. To extract the same backup with a different layout, use a different output folder, such as `--output ./artwork-backups-flat`.

If the backup has no gallery metadata, ProSave reports this and saves the artwork directly in `canvases`. If gallery metadata is present but cannot be read consistently, extraction stops; `--flat` lets you extract the artwork without it.

These folders preserve your organisation on the computer. Importing the artwork into Procreate does not automatically recreate its stacks.

## Optional: save PNG previews

To save a PNG preview of each artwork, run this in the same Terminal window:

```sh
python3 extract_previews.py ./artwork-backups --output ./previews --recursive
```

The images appear in a `previews` folder, following the artwork's device, date, and stack folders.

These are Procreate's stored previews. Their size and orientation depend on the document, and animations produce a still image. Keep the `.procreate` files: the PNGs don't contain editable layers and aren't full-resolution exports.

## Making another backup

Make a fresh iPad backup and repeat the extraction step. If you've closed Terminal, repeat the step that opens your ProSave folder in Terminal first.

- **Same device backup:** ProSave checks the files it already saved and continues with missing artwork.
- **New device backup:** ProSave creates another dated folder with a full copy of that backup's artwork. Older folders stay in place, so allow space for each new copy.

You can run the preview command again too. Identical previews are skipped.

You need to start each iPad backup and ProSave run yourself; there is no automatic schedule.

## Using Windows (untested)

The full backup and recovery process hasn't been tested on Windows. I'm happy to accept pull requests for Windows fixes and improvements to these instructions.

On Windows, use these steps in place of the Mac walkthrough:

1. Make a completed, unencrypted backup using **Apple Devices** or **iTunes**. Follow Apple's [Windows backup guide](https://support.apple.com/en-us/108967), then its [backup location guide](https://support.apple.com/108809) to find the device folder containing `Manifest.db`.
2. Download and unpack ProSave as described above. Install **Python 3.11 or newer** from [python.org](https://www.python.org/downloads/windows/) if needed.
3. Open the unpacked ProSave folder in File Explorer. Click its address bar, type `powershell`, and press Enter. This opens a command window in that folder.
4. Run `py -3 --version` to check Python is available and is version 3.11 or newer.
5. In File Explorer, right-click the device backup folder and choose **Copy as path**. On some Windows versions, hold Shift while right-clicking to see it.
6. Use the command below, replacing the entire quoted example location with the copied path. Keep one pair of quotes around the location. Enter it as one line:

```powershell
py -3 archive_library.py --backup "C:\replace-this-with-your-backup-folder" --output .\artwork-backups
```

Wait for `COMPLETE`, then find and check your `.procreate` files as described in the Mac walkthrough. To make optional previews:

```powershell
py -3 extract_previews.py .\artwork-backups --output .\previews --recursive
```

Automated tests pass on Windows, Mac, and Linux using generated backups. Extraction from a real iPad backup and sample imports into Procreate have been tested on Mac. That full process hasn't yet been tested with a Windows-created backup.

## If something doesn't work

| What you see | What to check |
| --- | --- |
| Python isn't found | Install Python, then close and reopen your command window. On Windows, use `py -3`; on Mac, use `python3`. |
| “Can't open file” followed by `archive_library.py` | Your command window may be in the wrong folder. Repeat the step that opens the unpacked ProSave folder in Terminal or PowerShell. |
| The backup can't be found or read | Select the device folder containing `Manifest.db`, rather than the parent `Backup` folder or an individual file. |
| The backup is encrypted or incomplete | ProSave needs a finished, unencrypted local backup. An iCloud backup alone won't work. |
| There isn't enough space | Make room for the extracted artwork while keeping the source backup intact. |
| A file conflicts, data is missing, or verification fails | Stop and keep the error message. Don't delete files from the original backup to fix it. |

If you're stuck, [open an issue](https://github.com/jpwhitaker/procreate-tools/issues) with your operating system, Python version, and the error text. Remove personal information from the message, and don't upload your iPad backup or private artwork.

## Limitations

- ProSave preserves stacks as folders, but doesn't recreate stacks inside Procreate when you import the files. It doesn't export your brush library or restore all Procreate settings.
- Procreate's internal file format can change. Keep the original backup and check sample imports.
- This is an independent, unofficial project, unaffiliated with Procreate.

<a id="technical-details"></a>

<details>
<summary>Technical details, Linux, and tests</summary>

ProSave uses Python's standard library and requires Python 3.11 or newer.

`archive_library.py` uses `procreate_backup.py` to read the completed device backup, reconstruct `.procreate` archives, and verify their contents against the source using SHA-256. The backup is opened for reading only. A `complete.json` record is written after the full run succeeds.

Stack membership and order come from Procreate's `Finder.archive` gallery metadata. `layout.json` records the output mode and, in stack mode when metadata is available, the gallery tree and source checksum. Stack folder names are sanitised for cross-platform use and include unique IDs. Unnamed stacks use `Stack` as their folder name prefix. Verification records mirror the artwork folders.

The output filesystem must support hard links, such as APFS, NTFS, or ext4. exFAT is not supported for artwork extraction. The separate preview script doesn't have this requirement.

On Linux, use a completed compatible backup copied from Mac or Windows, or a separate backup tool such as [`idevicebackup2`](https://github.com/libimobiledevice/libimobiledevice). Creating the iPad backup on Linux has not been tested here. From the unpacked project folder:

```sh
python3 archive_library.py --backup "/path/to/device-backup-folder" --output ./artwork-backups
python3 extract_previews.py ./artwork-backups --output ./previews --recursive
```

Each new backup produces a full artwork snapshot. There is no automatic deletion of old snapshots or sharing of unchanged data between snapshots.

A hard crash can leave `.running` or `.partial` files. Conflicting output and archives without verification records require inspection before retrying; ProSave refuses to overwrite them.

Run the tests with:

```sh
python3 -m unittest -v test_extract_previews test_archive_library
```

[Automated tests](https://github.com/jpwhitaker/procreate-tools/actions/workflows/tests.yml) run on macOS, Windows, and Linux with Python 3.11 and 3.14. They check byte preservation, repeat runs, corruption detection, missing data, and incomplete backup rejection using generated test data. They don't establish compatibility with every Procreate or iPadOS version.

</details>

## License

[MIT](LICENSE).
