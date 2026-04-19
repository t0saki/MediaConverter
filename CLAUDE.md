# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MediaConverter is a Python CLI tool that batch-converts images and videos to modern formats (AVIF/WebP for images, AV1+Opus MP4 for videos) with full metadata preservation. It has special support for Apple HDR HEIC files, reconstructing HDR from gain maps and encoding to PQ AVIF.

## Commands

```bash
# Run the converter
uv run python main.py <source_dir> <target_dir> [options]

# Example with common options
uv run python main.py /path/to/source /path/to/target \
  --quality 75 --max-image-resolution 4032*3024 --max-video-resolution 1920*1080 \
  --max-framerate 60 --max-workers 4 --keep-apple-hdr

# Install/sync dependencies
uv sync
```

No test suite exists. No linter is configured.

## Architecture

### Processing Pipeline

```
main.py  →  processor.py  →  image_processor.py  (parallel via ThreadPoolExecutor)
         (CLI + argparse)  →  video_processor.py  (sequential, to avoid resource contention)
                           →  metadata_handler.py (called after each conversion)
```

### Image Conversion

Two paths depending on whether the source is an Apple HDR HEIC with a gain map:

1. **Apple HDR path** (`--keep-apple-hdr`): `apple_hdr_avif_utils.py` uses the `hdr-conversion` PyPI package (`hdrconv`) to extract base image + gain map, reconstruct linear HDR via gain map application, convert to PQ color space via `colour-science`, and save as 10-bit AVIF via `imagecodecs` (libaom). Color metadata: P3-D65 primaries (12), PQ transfer (16).

2. **Standard path**: ImageMagick (`magick`) converts to AVIF with 10-bit depth. Falls back to WebP if AVIF encoding fails.

### Video Conversion

Uses `ffprobe` for metadata extraction, then `ffmpeg` with SVT-AV1 (`libsvtav1`) + Opus audio. Handles rotation metadata, frame rate limiting (applied when source fps > max+3), and Live Photo detection (paired .MOV+.HEIC files get CRF increased by `LIVE_PHOTO_CRF_OFFSET`).

### Metadata Handling

`metadata_handler.py` copies EXIF tags via `exiftool` and backfills creation dates using a priority chain: EXIF tags → filename parsing (regex for date patterns) → file mtime. Sets both EXIF dates and filesystem timestamps on output.

### HDR Dependencies

- **`hdr-conversion`** (PyPI >=0.1.4): [Jackchou00/hdr-conversion](https://github.com/Jackchou00/hdr-conversion) — Apple HDR gain map extraction, HEIC reading via `pillow_heif`, AVIF I/O via `imagecodecs`.
- **`imagecodecs`**: Provides `avif_encode()` with libaom for 10-bit PQ AVIF encoding. Replaces the old `pillow_heif` AVIF encoding path.
- **`colour-science`**: PQ transfer function (`colour.eotf_inverse` with `"ITU-R BT.2100 PQ"`).

## System Dependencies

The tool requires these external programs in PATH (checked at startup by `utils.check_dependencies()`):

- `ffmpeg` / `ffprobe` — video encoding and metadata extraction
- `exiftool` — EXIF metadata reading and writing
- `magick` (ImageMagick) — image dimension detection and format conversion

## Environment

- Python >=3.13, managed via `uv`
- Resolution args use `width*height` format (e.g., `4032*3024`)
- Defaults in `config.py`: image speed 4, video speed/preset 6, CRF 45, Opus 96k
