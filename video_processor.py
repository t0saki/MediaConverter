import logging
import json
import re
from math import sqrt, floor
from pathlib import Path
from utils import run_command
from metadata_handler import copy_metadata

def _get_video_info(filepath: Path) -> dict:
    """Gets video duration, width, and height using ffprobe."""
    cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', str(filepath)]
    result = run_command(cmd)
    if not result or not result.stdout:
        return {}
    
    try:
        data = json.loads(result.stdout)
        video_stream = next((s for s in data['streams'] if s['codec_type'] == 'video'), None)
        if not video_stream: return {}
        
        return {
            'duration': float(data.get('format', {}).get('duration', 0)),
            'width': int(video_stream.get('width', 0)),
            'height': int(video_stream.get('height', 0))
        }
    except (json.JSONDecodeError, KeyError):
        return {}

def process_video(filepath: Path, source_dir: Path, target_dir: Path, ffmpeg_args: str, max_res: int, delete_original: bool, speed_preset: int):
    """Converts a single video file."""
    relative_path = filepath.relative_to(source_dir)
    target_path = (target_dir / relative_path).with_suffix('.mp4')

    if target_path.exists():
        logging.info(f"Skipping already converted file: {filepath.name}")
        return

    target_path.parent.mkdir(parents=True, exist_ok=True)
    
    source_info = _get_video_info(filepath)
    if not source_info:
        logging.error(f"Could not read video metadata for {filepath}")
        return

    scale_filter = []
    resolution = source_info['width'] * source_info['height']
    if max_res and resolution > max_res:
        scale_factor = sqrt(max_res / resolution)
        target_width = floor(source_info['width'] * scale_factor / 2) * 2
        target_height = floor(source_info['height'] * scale_factor / 2) * 2
        scale_filter = ['-vf', f'scale={target_width}:{target_height}']

    # Replace preset value in ffmpeg args with the provided speed preset
    ffmpeg_args_updated = re.sub(r'-preset \d+', f'-preset {speed_preset}', ffmpeg_args)
    
    cmd = [
        'ffmpeg', '-y', '-i', str(filepath),
        *ffmpeg_args_updated.split(),
        *scale_filter,
        str(target_path)
    ]

    if run_command(cmd):
        target_info = _get_video_info(target_path)
        # Verify duration to catch partial conversions
        duration_diff = abs(source_info['duration'] - target_info.get('duration', 0))
        if source_info['duration'] > 0 and duration_diff > 2:
            logging.error(f"Duration mismatch for {target_path.name}. Deleting corrupt file.")
            target_path.unlink()
            return
            
        logging.info(f"Successfully converted {filepath.name} to MP4")
        copy_metadata(filepath, target_path)
        if delete_original:
            filepath.unlink()
    else:
        logging.error(f"Failed to convert {filepath.name}")
        if target_path.exists(): # Clean up failed attempt
            target_path.unlink()