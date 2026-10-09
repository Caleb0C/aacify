# aacify

A command-line utility that converts video files' audio streams to AAC using FFmpeg while copying the video streams without re-encoding them.

`aacify` is designed for batch processing video libraries, including folders containing multiple seasons or nested directories.

## Features

- **AAC audio conversion** — converts audio streams to AAC at a configurable bitrate.
- **No video re-encoding** — copies video streams to avoid unnecessary quality loss and processing time.
- **Automatic recursive searching** — searches nested directories by default.
- **Automatic output folders** — creates a sibling output folder instead of modifying the originals.
- **Preserves directory structure** — retains nested folders when converting a directory.
- **Progress bar** — displays conversion progress, elapsed time, estimated remaining time, and the current file number.
- **Safe output handling** — skips existing output files instead of intentionally overwriting them.
- **Temporary-file cleanup** — removes incomplete temporary outputs after normal failures and interruptions.
- **macOS metadata filtering** — ignores hidden files and AppleDouble files such as `._filename.mkv`.
- **Dry-run mode** — previews output paths without converting files.

## Requirements

- Python 3.10 or newer
- [FFmpeg](https://ffmpeg.org/download.html), including `ffmpeg` and `ffprobe`
- macOS, Linux, or another platform supported by Python and FFmpeg

On macOS, install FFmpeg using Homebrew:

```bash
brew install ffmpeg
```

## Installation

Install from a local Git repository using `pipx`:

```bash
pipx install .
```

For development, install in editable mode:

```bash
pipx install --editable .
```

The project must include packaging metadata, such as a `pyproject.toml`, defining the `aacify` command.

## Usage

### Convert a TV show folder

```bash
aacify "/Volumes/Media/Example Show"
```

Directory searching is recursive by default. Videos in nested season folders are discovered automatically.

The output is created alongside the source directory:

```text
/Volumes/Media/
├── Example Show/
│   ├── Season 1/
│   │   ├── Example.Show.S01E01.mkv
│   │   └── Example.Show.S01E02.mkv
│   └── Season 2/
│       └── Example.Show.S02E01.mkv
└── aacified - Example Show/
    ├── Season 1/
    │   ├── Example.Show.S01E01.mkv
    │   └── Example.Show.S01E02.mkv
    └── Season 2/
        └── Example.Show.S02E01.mkv
```

Original files are left untouched.

### Convert a single file

```bash
aacify "/Volumes/Media/recording.mkv"
```

The output is placed at:

```text
/Volumes/Media/aacified - recording/recording.mkv
```

### Convert without searching subdirectories

Use `--no-recursive` to process only files directly inside the specified directory:

```bash
aacify "/Volumes/Media/Example Show" --no-recursive
```

### Preview a conversion

Use `--dry-run` to display planned conversions without creating output files:

```bash
aacify "/Volumes/Media/Example Show" --dry-run
```

### Choose an output directory

Use `-o` or `--output` to specify a custom output directory:

```bash
aacify "/Volumes/Media/Example Show" \
  --output "/Volumes/Media/Converted Show"
```

### Change the AAC bitrate

The default bitrate is `192k` per audio stream.

```bash
aacify "/Volumes/Media/Example Show" --bitrate 256k
```

### Convert multiple files or directories

```bash
aacify "/Volumes/Media/video1.mkv" "/Volumes/Media/video2.mp4"
```

Multiple inputs are grouped into a single automatically named output directory based on the first input.

## Command-line options

| Option | Description |
|---|---|
| `paths` | One or more video files or directories |
| `-o`, `--output` | Specify the output directory |
| `-b`, `--bitrate` | AAC bitrate; default is `192k` |
| `-r`, `--recursive` | Search recursively; this is already the default |
| `--no-recursive` | Search only the specified directory's top level |
| `--dry-run` | Preview conversions without writing files |
| `-h`, `--help` | Display command-line help |

Display the options at any time:

```bash
aacify --help
```

## How it works

1. Finds supported video files.
2. Uses FFprobe to check whether each file contains audio and determine its duration.
3. Uses FFmpeg to copy streams and metadata while encoding audio streams as AAC.
4. Writes the conversion to a temporary file.
5. Publishes the completed file without intentionally overwriting an existing output.
6. Removes the temporary file after completion or failure.

Video streams are copied rather than re-encoded. Audio streams are encoded as AAC at the selected bitrate.

The output retains the source file's extension. However, not every container supports every codec combination, so conversion can fail for incompatible formats.

## Safety and limitations

- Source files are never intentionally modified.
- Existing destination files are skipped.
- Failed conversions are reported in the terminal.
- Normal conversion failures and handled interruptions trigger temporary-file cleanup. A forced termination or system crash may still leave temporary files behind.
- Conversion may fail if FFmpeg cannot mux AAC into the selected output container.
- Multiple files with the same filename targeting the same output directory may conflict; existing destinations are skipped.

## License

`aacify` is released under the [MIT License](LICENSE).