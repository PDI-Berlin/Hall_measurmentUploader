# Hall PC -> NOMAD Uploader

Processes Hall measurement folders and uploads them to a NOMAD Oasis as ELNMeasurement entries.

## Quick Start

```bash
python hall_uploader.py
```

Just run it. It will ask you what to do.

## How it works

```
d3.bat creates folder: 20260605_1401_m84317_C/
  ├── m84317_C_50uA_0_5T.dat
  ├── m84317_C_50uA_0_7T.dat
  ├── m84317_C_10uA_0_7T.dat
  └── Labbook-R722-HallSetup.ods
                │
                ▼
        hall_uploader.py
                │
                ├─ Parse folder name -> datetime + sample ID
                ├─ Read all .dat files, convert to HTML
                ├─ Build elnmeasurement.archive.json
                ├─ Package ALL files into .zip
                └─ Upload to NOMAD
```

## Interactive mode (no arguments)

```bash
python hall_uploader.py
```

1. **Folder** - shows saved folder from config, or asks for a new one
2. **Instrument** - confirms instrument name (default: PDI_Hall_Setup)
3. **Processing** - reads .dat files, builds archive JSON, creates zip
4. **Upload** - asks if you want to upload to NOMAD
   - If yes: asks for username, shows saved server/upload ID
   - Can upload to a new upload or add to an existing one
   - Waits for processing, shows link to view

## With arguments

```bash
python hall_uploader.py <folder>              # process and upload
python hall_uploader.py <folder> --dry-run    # build files only, no upload
```

## Config file (config.yml)

Saves your settings so you don't have to type them every time:

```yaml
folder_path: C:\Users\sina\Nextcloud\Nomad\Hall_PC\m84319_A
instrument: PDI_Hall_Setup
last_folder: C:\Users\sina\Nextcloud\Nomad\Hall_PC\m84319_A
last_user: sina

users:
  sina:
    base_url: http://intra8-02.pdi-berlin.de/nomad-oasis/api/v1
    upload_id: F19SpTc8TSyLYy2TNgH_zQ
```

- `folder_path` - last used folder, shown on startup
- `instrument` - default instrument name
- `users.<name>.base_url` - NOMAD server for this user
- `users.<name>.upload_id` - reuse an existing upload instead of creating a new one

Add more users by adding entries under `users:`.

## Folder naming

`d3.bat` creates folders named `YYYYMMDD_HHMM_<SampleIDs>`:

| Folder name | Datetime | Sample IDs |
|---|---|---|
| `20260605_1401_m84317_C` | 2026-06-05 14:01 | m84317_C |
| `20260605_1401_M81_M82` | 2026-06-05 14:01 | M81, M82 |

Folders without this pattern still work - datetime is set to now, sample ID is the folder name.

## Generated archive.json

Follows the `nomad.datamodel.metainfo.eln.ELNMeasurement` schema:

```json
{
  "data": {
    "m_def": "nomad.datamodel.metainfo.eln.ELNMeasurement",
    "name": "m84317_C__Hall_20260605_1401_norefs",
    "datetime": "2026-06-05T14:01:00+00:00",
    "samples": [{"lab_id": "m84317_C"}],
    "instruments": [{"lab_id": "PDI_Hall_Setup"}],
    "results": [
      {"name": "m84317_C_50uA_0_5T.dat", "result": "<p>...content...</p>"},
      {"name": "m84317_C_50uA_0_7T.dat", "result": "<p>...content...</p>"}
    ]
  }
}
```

## Requirements

- Python 3.8+
- `requests` (`pip install requests`)
- `pyyaml` (`pip install pyyaml`) - for config file support

## Windows Batch Interface (Recommended for Windows Users)

For Windows users who prefer a GUI-like interface, a batch file `hall_uploader.bat` is included in this repository. It provides:

### Features:
- **Interactive UI with colored terminal** - Resembles a modern GUI application
- **One-click access to all modes** - Interactive or CLI processing
- **Automatic dependency checks** - Verifies Python and required modules
- **Visual progress tracking** - Clear headers, subheaders, and progress messages
- **Configuration setup wizard** - Guided setup of your NOMAD server settings

### Usage:

**1. Initial Setup:**
```batch
# Run once to check dependencies and setup environment
hall_uploader.bat
```

**2. Interactive Mode (Recommended):**
```batch
# Interactive UI for guided uploads
hall_uploader.bat
# Select option 1 (Interactive Mode)
```

**3. Command Line Mode:**
```batch
# Process a specific folder with progress tracking
hall_uploader.bat process "C:\path\to\measurement\folder"

# Dry-run mode (test without uploading)
hall_uploader.bat process "C:\path\to\measurement\folder" --dry-run
```

**4. Help and Configuration:**
```batch
hall_uploader.bat --help     # Show help and options
hall_uploader.bat --version  # Show version information
```

### Benefits:
- **User-friendly** - Intuitive menu interface with visual feedback
- **Feature-rich** - All the functionality of the Python script with enhanced UX
- **Error handling** - Comprehensive error messages and recovery steps
- **Cross-platform support** - Works on any Windows system with Python
- **Zero configuration** - Automatically checks and installs dependencies

### Note for Windows Users:
The batch file is optimized for Windows environments and provides a much better user experience than running `python hall_uploader.py` directly in the command prompt.