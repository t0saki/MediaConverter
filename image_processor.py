import logging
from math import sqrt, floor
from pathlib import Path
from utils import run_command
from metadata_handler import copy_metadata

try:
    from apple_hdr_avif_utils import convert_apple_hdr_to_avif, has_gain_map
except ImportError:
    logging.warning("apple_hdr_avif_utils import error. Apple HDR conversion will be disabled. Please ensure all dependencies of hdr_conversion are installed.")
    def convert_apple_hdr_to_avif(*args, **kwargs):
        return False
    def has_gain_map(*args, **kwargs):
        return False

def process_image(filepath: Path, source_dir: Path, target_dir: Path, quality: int, max_res: int, delete_original: bool, speed_preset: int, keep_apple_hdr: bool = False):
    """Converts a single image to AVIF with a fallback to WebP."""
    relative_path = filepath.relative_to(source_dir)
    target_path_avif = (target_dir / relative_path).with_suffix('.avif')
    target_path_webp = (target_dir / relative_path).with_suffix('.webp')

    # Skip if target file already exists and has non-zero size
    if (target_path_avif.exists() and target_path_avif.stat().st_size > 0) or \
       (target_path_webp.exists() and target_path_webp.stat().st_size > 0):
        logging.info(f"Skipping already converted file: {filepath.name}")
        return

    target_path_avif.parent.mkdir(parents=True, exist_ok=True)

    # Get dimensions using ImageMagick's identify
    cmd_identify = ['magick', 'identify', '-format', '%wx%h', str(filepath)]
    identify_result = run_command(cmd_identify)
    if not identify_result or not identify_result.stdout:
        logging.error(
            f"Could not get dimensions for {filepath} using identify")
        return

    # The output format '%wx%h' is identical to the old ffprobe command,
    # so the parsing logic remains the same.
    width, height = map(int, identify_result.stdout.strip().split('x'))
    resolution = width * height

    # Calculate resize filter if necessary
    resize_filter = []
    if resolution > max_res:
        scale_factor = sqrt(max_res / resolution)
        target_width = floor(width * scale_factor / 2) * 2
        target_height = floor(height * scale_factor / 2) * 2
        resize_filter = ['-resize', f'{target_width}x{target_height}']
    else:
        target_width, target_height = None, None

    success = False

    # Try Apple HDR conversion if enabled and file has gain map
    if keep_apple_hdr and filepath.suffix.lower() in ['.heic', '.heif']:
        try:
            logging.debug(f"Checking for Apple HDR gain map in {filepath.name}")
            if has_gain_map(str(filepath)):
                logging.debug(f"Apple HDR gain map found in {filepath.name}, attempting HDR conversion")
                
                # Attempt Apple HDR to AVIF conversion
                success = convert_apple_hdr_to_avif(
                    input_path=str(filepath),
                    output_path=str(target_path_avif),
                    quality=quality,
                    target_width=target_width,
                    target_height=target_height,
                    speed_preset=speed_preset
                )
        except Exception as e:
            logging.warning(f"Error during Apple HDR conversion for {filepath.name}: {e}")
            success = False

    if not success:
        # Build conversion command (use ImageMagick for broad compatibility)
        cmd = [
            'magick', str(filepath),
            *resize_filter,
            '-quality', str(quality),
            '-define', f'heic:speed={speed_preset}', # Speed preset for AVIF/HEIC
            '-depth', '10',           # 10-bit for better color
            str(target_path_avif)
        ]

        # Execute conversion
        success = run_command(cmd)

    if success:
        logging.debug(f"Successfully converted {filepath.name} to AVIF")
        copy_metadata(filepath, target_path_avif)
        if delete_original:
            filepath.unlink()
    else:
        # Fallback to WebP if AVIF conversion fails
        logging.warning(f"AVIF conversion failed for {filepath.name}. Falling back to WebP.")
        cmd[-1] = str(target_path_webp) # Change output path
        if run_command(cmd):
            logging.debug(f"Successfully converted {filepath.name} to WebP")
            copy_metadata(filepath, target_path_webp)
            if delete_original:
                filepath.unlink()
        else:
            logging.error(f"WebP fallback also failed for {filepath.name}")