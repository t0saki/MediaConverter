import argparse

import utils
import processor
import config

def main():
    parser = argparse.ArgumentParser(
        description="A comprehensive tool to convert and compress images and videos.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("source_dir", type=str, help="Source directory containing media files.")
    parser.add_argument("target_dir", type=str, help="Target directory for converted files.")
    
    # Conversion settings
    parser.add_argument("-q", "--quality", type=int, default=75, help="Image quality for AVIF/WebP (0-100). Lower is smaller.")
    parser.add_argument("-r", "--max-resolution", type=int, default=config.DEFAULT_MAX_RESOLUTION, help="Max resolution in pixels (width * height). Files above this will be resized.")
    parser.add_argument("--video-args", type=str, default=config.DEFAULT_VIDEO_ARGS, help="FFmpeg arguments for video conversion.")
    parser.add_argument("--image-speed", type=int, default=config.DEFAULT_IMAGE_SPEED_PRESET, help="Speed preset for image conversion (0-10, lower is slower but better quality).")
    parser.add_argument("--video-speed", type=int, default=config.DEFAULT_VIDEO_SPEED_PRESET, help="Speed preset for video conversion (0-13, lower is slower but better quality).")

    # Concurrency and file handling
    parser.add_argument("-w", "--max-workers", type=int, default=4, help="Maximum number of parallel threads.")
    parser.add_argument("--delete-original", action="store_true", help="Delete original files after successful conversion.")
    parser.add_argument("--skip-existing", action="store_true", default=True, help="Skip files that already exist in the target directory.")
    parser.add_argument("--keep-apple-hdr", action="store_true", help="Preserve Apple HDR metadata when converting HEIC files with gain maps.")
    
    parser.add_argument("--log-file", type=str, default="conversion.log", help="Path to the log file.")

    args = parser.parse_args()

    # Setup
    utils.setup_logging(args.log_file)
    utils.check_dependencies()

    # Start processing
    try:
        processor.process_media(
            source_dir=args.source_dir,
            target_dir=args.target_dir,
            quality=args.quality,
            max_res=args.max_resolution,
            video_args=args.video_args,
            max_workers=args.max_workers,
            delete_original=args.delete_original,
            skip_existing=args.skip_existing,
            image_speed=args.image_speed,
            video_speed=args.video_speed,
            keep_apple_hdr=args.keep_apple_hdr
        )
    except KeyboardInterrupt:
        utils.logging.info("\nProcess interrupted by user. Exiting.")
        exit(0)

if __name__ == "__main__":
    main()