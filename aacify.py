#!/usr/bin/env python3
"""Replace video audio streams with AAC using FFmpeg."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path


DEFAULT_BITRATE = "192k"

VIDEO_EXTENSIONS = {
    ".mkv", ".mp4", ".m4v", ".mov", ".avi", ".webm",
    ".wmv", ".flv", ".mpeg", ".mpg", ".ts", ".mts",
    ".m2ts", ".vob", ".ogv", ".3gp",
}


def require_program(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise RuntimeError(
            f"Cannot find {name}. Install FFmpeg and ensure "
            f"{name} is available on your PATH."
        )
    return path


def probe_media(
    ffprobe: str, source: Path
) -> tuple[bool, float | None]:
    """Inspect audio streams and duration in a single FFprobe call."""
    command = [
        ffprobe,
        "-v", "error",
        "-show_entries", "format=duration:stream=codec_type",
        "-of", "json",
        str(source),
    ]

    result = subprocess.run(
        command, capture_output=True, text=True, check=False
    )

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip() or "FFprobe could not read the file."
        )

    data = json.loads(result.stdout)
    has_audio = any(
        stream.get("codec_type") == "audio"
        for stream in data.get("streams", [])
    )

    try:
        duration = float(data.get("format", {}).get("duration", ""))
        if duration <= 0:
            duration = None
    except (ValueError, TypeError):
        duration = None

    return has_audio, duration


def format_time(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def show_progress(
    fraction: float,
    elapsed: float,
    filename: str,
    file_number: int,
    total_files: int,
) -> None:
    fraction = max(0.0, min(1.0, fraction))
    width = 24
    filled = int(width * fraction)
    bar = "#" * filled + "-" * (width - filled)

    percent = fraction * 100
    eta = elapsed * (1 - fraction) / fraction if fraction > 0 else 0

    label = Path(filename).name
    if len(label) > 32:
        label = label[:29] + "..."

    print(
        f"\r[{bar}] {percent:5.1f}% "
        f"| {file_number}/{total_files} "
        f"| elapsed {format_time(elapsed)} "
        f"| ETA {format_time(eta)} "
        f"| {label:<32}",
        end="",
        flush=True,
    )


def discover_inputs(
    paths: list[Path], recursive: bool
) -> list[Path]:
    found: set[Path] = set()

    for item in paths:
        item = item.expanduser().resolve()

        if not item.exists():
            print(f"SKIP  Not found: {item}", file=sys.stderr)
            continue

        if item.is_file():
            if item.name.startswith("._") or item.name.startswith("."):
                continue

            if item.suffix.lower() in VIDEO_EXTENSIONS:
                found.add(item)
            else:
                print(f"SKIP  Unsupported extension: {item}")
            continue

        if item.is_dir():
            iterator = item.rglob("*") if recursive else item.iterdir()

            for child in iterator:
                if not child.is_file():
                    continue

                if child.name.startswith("."):
                    continue

                if child.suffix.lower() in VIDEO_EXTENSIONS:
                    found.add(child.resolve())
        else:
            print(f"SKIP  Not a regular file: {item}", file=sys.stderr)

    return sorted(found)


def output_path(
    source: Path,
    output_dir: Path,
    input_root: Path | None = None,
) -> Path:
    """Preserve relative subdirectories when processing a folder."""
    if input_root is not None:
        return output_dir / source.relative_to(input_root)

    return output_dir / source.name


def publish_without_overwrite(
    temporary: Path, destination: Path
) -> None:
    """Publish a finished file without intentionally replacing an existing one.

    Reserve the destination exclusively first, then atomically replace
    our own placeholder. This avoids requiring hard-link support on
    external drives formatted with filesystems such as exFAT.
    """
    descriptor = os.open(
        destination,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY,
        0o666,
    )
    os.close(descriptor)

    try:
        os.replace(temporary, destination)
    except OSError:
        # Remove the empty reservation if publishing failed.
        try:
            if destination.stat().st_size == 0:
                destination.unlink()
        except OSError:
            pass
        raise


def convert(
    ffmpeg: str,
    ffprobe: str,
    source: Path,
    destination: Path,
    bitrate: str,
    dry_run: bool,
    file_number: int = 1,
    total_files: int = 1,
) -> bool:
    if destination.exists():
        print(f"SKIP  Output already exists: {destination}")
        return False

    if source == destination.resolve():
        print(f"SKIP  Output would overwrite input: {source}")
        return False

    try:
        has_audio, duration = probe_media(ffprobe, source)

        if not has_audio:
            print(f"SKIP  No audio stream: {source}")
            return False

    except (RuntimeError, json.JSONDecodeError) as exc:
        print(f"FAIL  Cannot inspect {source}: {exc}", file=sys.stderr)
        return False

    if dry_run:
        print(f"WOULD CONVERT  {source} -> {destination}")
        return True

    destination.parent.mkdir(parents=True, exist_ok=True)

    temporary = destination.with_name(
        f".{destination.stem}.aacify-{uuid.uuid4().hex}"
        f"{destination.suffix}"
    )

    command = [
        ffmpeg,
        "-hide_banner",
        "-nostdin",
        "-v", "error",
        "-n",
        "-i", str(source),
        "-map", "0",
        "-map_metadata", "0",
        "-map_chapters", "0",
        "-c", "copy",
        "-c:a", "aac",
        "-b:a", bitrate,
        "-progress", "pipe:1",
        "-nostats",
        str(temporary),
    ]

    process = None

    try:
        print(f"CONVERT  {source}")
        started = time.monotonic()
        errors: list[str] = []

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        assert process.stdout is not None

        for line in process.stdout:
            line = line.strip()

            if line.startswith("out_time_us=") and duration:
                try:
                    media_time = int(line.split("=", 1)[1]) / 1_000_000
                    show_progress(
                        min(1.0, max(0.0, media_time / duration)),
                        time.monotonic() - started,
                        str(source),
                        file_number,
                        total_files,
                    )
                except ValueError:
                    pass

            elif line == "progress=end" and duration:
                show_progress(
                    1.0,
                    time.monotonic() - started,
                    str(source),
                    file_number,
                    total_files,
                )

            elif line and not line.startswith(
                (
                    "frame=", "fps=", "bitrate=", "total_size=",
                    "out_time=", "out_time_ms=", "dup_frames=",
                    "drop_frames=", "speed=", "progress=",
                )
            ):
                errors.append(line)

        return_code = process.wait()
        process = None
        print()

        if return_code != 0:
            print(
                f"FAIL  FFmpeg exited with code {return_code}: {source}",
                file=sys.stderr,
            )
            for error in errors[-10:]:
                print(error, file=sys.stderr)
            return False

        if not temporary.is_file() or temporary.stat().st_size == 0:
            print(f"FAIL  Empty output: {source}", file=sys.stderr)
            return False

        # Reserve the destination without overwriting existing files.
        try:
            publish_without_overwrite(temporary, destination)
        except FileExistsError:
            print(f"SKIP  Output already exists: {destination}")
            return False

        print(f"DONE  {destination}")
        return True

    except KeyboardInterrupt:
        print("\nInterrupted. Cleaning up incomplete conversion...")
        return False

    except OSError as exc:
        print(f"FAIL  {source}: {exc}", file=sys.stderr)
        return False

    finally:
        # Stop FFmpeg before removing its temporary output.
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

        # Remove any partial temporary output on failure or interruption.
        try:
            temporary.unlink(missing_ok=True)
        except OSError as exc:
            print(
                f"WARNING: Could not remove temporary file "
                f"{temporary}: {exc}",
                file=sys.stderr,
            )

def main() -> int:
    parser = argparse.ArgumentParser(
        prog="aacify",
        description=(
            "Convert video audio streams to AAC while copying video "
            "and preserving the input container extension."
        ),
    )

    parser.add_argument(
        "paths",
        nargs="+",
        type=Path,
        help="Video files and/or directories",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="Output directory (default: automatically determined)",
    )
    parser.add_argument(
        "-b", "--bitrate",
        default=DEFAULT_BITRATE,
        help="AAC bitrate per audio stream (default: 192k)",
    )
    parser.add_argument(
    	"-r", "--recursive",
    	dest="recursive",
	    action="store_true",
	    default=True,
	    help="Search directories recursively (default)",
	)
    parser.add_argument(
		"--no-recursive",
		dest="recursive",
    	action="store_false",
    	help="Only search the specified directory's top level",
	)
	
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show planned conversions without writing files",
    )

    args = parser.parse_args()

    try:
        ffmpeg = require_program("ffmpeg")
        ffprobe = require_program("ffprobe")
    except RuntimeError as exc:
        parser.error(str(exc))

    requested = [p.expanduser().resolve() for p in args.paths]

    # Automatically select the output directory.
    input_root: Path | None = None

    if args.output is not None:
        output_dir = args.output.expanduser().resolve()

        if len(requested) == 1 and requested[0].is_dir():
            input_root = requested[0]

    elif len(requested) == 1 and requested[0].is_dir():
        # Folder input: sibling output folder.
        input_root = requested[0]
        output_dir = (
            input_root.parent / f"aacified - {input_root.name}"
        )

    elif len(requested) == 1:
        # Single file: sibling output folder named after the file.
        source_file = requested[0]
        output_dir = (
            source_file.parent / f"aacified - {source_file.stem}"
        )

    else:
        # Multiple inputs: group results beside the first input.
        first = requested[0]
        base_name = first.name if first.is_dir() else first.stem
        output_dir = first.parent / f"aacified - {base_name}"

    sources = discover_inputs(requested, args.recursive)

    if not sources:
        print("No supported video files found.", file=sys.stderr)
        return 1

    # Avoid recursively processing the output directory if a custom
    # output path happens to be inside a source directory.
    filtered_sources = []

    for source in sources:
        if input_root is not None and source.is_relative_to(output_dir):
            continue
        filtered_sources.append(source)

    sources = filtered_sources

    if not sources:
        print("No input files to process.", file=sys.stderr)
        return 1

    successes = 0
    failures = 0
    total_files = len(sources)

    for file_number, source in enumerate(sources, start=1):
        destination = output_path(source, output_dir, input_root)

        if destination.resolve() == source:
            print(f"SKIP  Output matches input: {source}", file=sys.stderr)
            failures += 1
            continue

        ok = convert(
            ffmpeg,
            ffprobe,
            source,
            destination,
            args.bitrate,
            args.dry_run,
            file_number,
            total_files,
        )

        if ok:
            successes += 1
        else:
            failures += 1

    print(
        f"\nSummary: {successes} successful, "
        f"{failures} skipped/failed."
    )

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())