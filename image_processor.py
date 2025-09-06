# media_converter/image_processor.py

import logging
from math import sqrt, floor
from pathlib import Path
from utils import run_command
from metadata_handler import copy_metadata

def process_image(filepath: Path, source_dir: Path, target_dir: Path, quality: int, max_res: int, delete_original: bool):
    """Converts a single image to AVIF with a fallback to WebP."""
    relative_path = filepath.relative_to(source_dir)
    target_path_avif = (target_dir / relative_path).with_suffix('.avif')
    target_path_webp = (target_dir / relative_path).with_suffix('.webp')

    # Skip if target file already exists
    if target_path_avif.exists() or target_path_webp.exists():
        logging.info(f"Skipping already converted file: {filepath.name}")
        return

    target_path_avif.parent.mkdir(parents=True, exist_ok=True)

    # Get dimensions using ffprobe (universal for images/videos)
    cmd_probe = ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of', 'csv=s=x:p=0', str(filepath)]
    probe_result = run_command(cmd_probe)
    if not probe_result or not probe_result.stdout:
        logging.error(f"Could not get dimensions for {filepath}")
        return
    
    width, height = map(int, probe_result.stdout.strip().split('x'))
    resolution = width * height

    # Calculate resize filter if necessary
    resize_filter = []
    if resolution > max_res:
        scale_factor = sqrt(max_res / resolution)
        target_width = floor(width * scale_factor / 2) * 2
        target_height = floor(height * scale_factor / 2) * 2
        resize_filter = ['-resize', f'{target_width}x{target_height}']

    # Build conversion command (use ImageMagick for broad compatibility)
    cmd = [
        'magick', str(filepath),
        *resize_filter,
        '-quality', str(quality),
        '-define', 'heic:speed=4', # Speed preset for AVIF/HEIC
        '-depth', '10',           # 10-bit for better color
        str(target_path_avif)
    ]

    # Execute conversion
    if run_command(cmd):
        logging.info(f"Successfully converted {filepath.name} to AVIF")
        copy_metadata(filepath, target_path_avif)
        if delete_original:
            filepath.unlink()
    else:
        # Fallback to WebP if AVIF conversion fails
        logging.warning(f"AVIF conversion failed for {filepath.name}. Falling back to WebP.")
        cmd[-1] = str(target_path_webp) # Change output path
        if run_command(cmd):
            logging.info(f"Successfully converted {filepath.name} to WebP")
            copy_metadata(filepath, target_path_webp)
            if delete_original:
                filepath.unlink()
        else:
            logging.error(f"WebP fallback also failed for {filepath.name}")