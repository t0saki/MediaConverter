import logging
import json
import re
from math import sqrt, floor
from pathlib import Path
from utils import run_command
from metadata_handler import copy_metadata


def _get_video_info(filepath: Path) -> dict:
    """Gets video duration, width, height, and rotation using ffprobe."""
    cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json',
           '-show_format', '-show_streams', str(filepath)]
    result = run_command(cmd)
    if not result or not result.stdout:
        logging.warning(
            f"ffprobe command failed or returned no output for {filepath}")
        return {}

    try:
        data = json.loads(result.stdout)
        video_stream = next(
            (s for s in data['streams'] if s['codec_type'] == 'video'), None)
        if not video_stream:
            logging.warning(f"No video stream found in {filepath}")
            return {}

        # 新增：获取旋转角度，如果标签不存在则默认为0
        rotation = int(video_stream.get('tags', {}).get('rotate', '0'))

        return {
            'duration': float(data.get('format', {}).get('duration', 0)),
            'width': int(video_stream.get('width', 0)),
            'height': int(video_stream.get('height', 0)),
            'rotation': rotation  # 新增：返回旋转角度
        }
    except (json.JSONDecodeError, KeyError, StopIteration) as e:
        logging.error(f"Error parsing ffprobe output for {filepath}: {e}")
        return {}


def process_video(filepath: Path, source_dir: Path, target_dir: Path, ffmpeg_args: str, max_res: int, delete_original: bool, speed_preset: int):
    """Converts a single video file, correctly handling rotation."""
    relative_path = filepath.relative_to(source_dir)
    target_path = (target_dir / relative_path).with_suffix('.mp4')

    if target_path.exists() and target_path.stat().st_size > 0:
        logging.info(f"Skipping already converted file: {filepath.name}")
        return

    target_path.parent.mkdir(parents=True, exist_ok=True)

    source_info = _get_video_info(filepath)
    if not source_info:
        logging.error(f"Could not read video metadata for {filepath}")
        return

    scale_filter = []

    # 修改：根据旋转元数据调整宽高
    width = source_info['width']
    height = source_info['height']
    rotation = source_info.get('rotation', 0)

    # 如果视频旋转了90或270度，交换宽高以进行正确计算
    if abs(rotation) == 90:
        width, height = height, width

    resolution = width * height
    if max_res and resolution > max_res:
        scale_factor = sqrt(max_res / resolution)
        # 使用调整后的宽高进行缩放计算
        target_width = floor(width * scale_factor / 2) * 2
        target_height = floor(height * scale_factor / 2) * 2
        scale_filter = ['-vf', f'scale={target_width}:{target_height}']

    # 如果ffmpeg参数中包含 -metadata:s:v rotate，则将其移除，因为转换后不再需要
    ffmpeg_args_list = ffmpeg_args.split()
    try:
        rotate_index = ffmpeg_args_list.index('-metadata:s:v')
        # 移除 -metadata:s:v 和它的值
        ffmpeg_args_list.pop(rotate_index)
        ffmpeg_args_list.pop(rotate_index)
    except ValueError:
        pass  # 如果参数不存在，则什么也不做

    # 添加 -no-autorotate 确保ffmpeg不会自动旋转视频，因为我们已经处理了尺寸
    ffmpeg_args_updated = re.sub(
        r'-preset \d+', f'-preset {speed_preset}', " ".join(ffmpeg_args_list))

    cmd = [
        'ffmpeg', '-y', '-noautorotate', '-i', str(filepath),
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