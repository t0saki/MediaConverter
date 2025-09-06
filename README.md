# Media Converter

A comprehensive Python tool for converting and compressing images and videos to modern formats with metadata preservation.

## Features

- **Image Conversion**: Convert images to AVIF format with WebP fallback
- **Video Conversion**: Convert videos to AV1/Opus format (MP4 container)
- **Metadata Preservation**: Copy EXIF data and file timestamps
- **Smart Resizing**: Automatically resize media that exceeds maximum resolution
- **Parallel Processing**: Multi-threaded conversion for faster processing
- **Error Handling**: Robust error handling with fallback mechanisms

## Supported Formats

### Input Formats
- **Images**: PNG, JPG, JPEG, WebP, HEIC, HEIF, GIF, TIFF
- **Videos**: MP4, AVI, MKV, MOV, MPG, MPEG, M4V, WebM, TS

### Output Formats
- **Images**: AVIF (primary), WebP (fallback)
- **Videos**: MP4 with AV1 video and Opus audio

## Installation

### Prerequisites

1. **Install system dependencies**:
   
   **Windows (Chocolatey)**:
   ```bash
   choco install ffmpeg exiftool imagemagick.app
   ```
   
   **macOS (Homebrew)**:
   ```bash
   brew install ffmpeg exiftool imagemagick
   ```
   
   **Debian/Ubuntu**:
   ```bash
   sudo apt update && sudo apt install ffmpeg exiftool imagemagick
   ```

2. **Install Python dependencies**:
   ```bash
   pip install tqdm
   ```

## Usage

### Basic Usage
```bash
python main.py "/path/to/source" "/path/to/target"
```

### Advanced Options
```bash
python main.py "D:\MyPictures" "D:\ConvertedMedia" \
  --quality 60 \
  --max-resolution 1920*1080 \
  --max-workers 8 \
  --delete-original \
  --log-file conversion.log
```

### Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `source_dir` | Source directory containing media files | Required |
| `target_dir` | Target directory for converted files | Required |
| `-q, --quality` | Image quality (0-100, lower = smaller) | 75 |
| `-r, --max-resolution` | Max pixels (width*height) before resizing | 4032*3024 |
| `--video-args` | Custom FFmpeg arguments for video | AV1/Opus preset |
| `--image-speed` | Speed preset for image conversion (0-10, lower is slower but better quality) | 6 |
| `--video-speed` | Speed preset for video conversion (0-13, lower is slower but better quality) | 4 |
| `-w, --max-workers` | Number of parallel threads | 4 |
| `--delete-original` | Delete original files after conversion | False |
| `--skip-existing` | Skip files that already exist in target | True |
| `--keep-apple-hdr` | Convert Apple HDR gain maps to PQ format when converting HEIC files | False |
| `--log-file` | Path to log file | conversion.log |

## Project Structure

```
media_converter/
├── main.py              # Main entry point
├── config.py            # Configuration constants
├── utils.py             # Utility functions
├── metadata_handler.py  # Metadata handling
├── image_processor.py   # Image conversion logic
├── video_processor.py   # Video conversion logic
├── processor.py         # Main orchestrator
└── README.md           # This file
```

## Examples

### Convert photos with high quality
```bash
python main.py "~/Photos" "~/PhotosConverted" --quality 85
```

### Convert and resize large videos
```bash
python main.py "~/Videos" "~/VideosConverted" --max-resolution 1280*720
```

### Batch convert with maximum parallelism
```bash
python main.py "/mnt/photos" "/mnt/converted" --max-workers 16 --delete-original
```

## Notes

- The tool preserves directory structure from source to target
- Files are skipped if they already exist in the target directory
- Metadata (EXIF, timestamps) is copied to converted files
- Conversion progress is shown with progress bars
- Detailed logs are written to the specified log file
- Apple HDR support requires the `--keep-apple-hdr` flag

## Acknowledgments

- Apple HDR conversion functionality based on [hdr-conversion](https://github.com/Jackchou00/hdr-conversion) by Jackchou

## License

MIT License