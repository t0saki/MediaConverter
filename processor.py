import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from tqdm import tqdm
from config import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS
from image_processor import process_image
from video_processor import process_video

def process_media(source_dir: str, target_dir: str, quality: int, max_res: int, video_args: str, max_workers: int, delete_original: bool, skip_existing: bool, image_speed: int, video_speed: int, keep_apple_hdr: bool = False):
    """Finds and converts all media files in the source directory."""
    source_path = Path(source_dir)
    target_path = Path(target_dir)

    if not source_path.is_dir():
        logging.error(f"Source directory not found: {source_dir}")
        return

    files_to_process = [p for p in source_path.rglob('*') if p.is_file()]
    
    image_files = [f for f in files_to_process if f.suffix.lower() in IMAGE_EXTENSIONS]
    video_files = [f for f in files_to_process if f.suffix.lower() in VIDEO_EXTENSIONS]

    logging.info(f"Found {len(image_files)} images and {len(video_files)} videos to process.")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Create partial functions with fixed arguments for mapping
        image_task = partial(process_image, source_dir=source_path, target_dir=target_path, quality=quality, max_res=max_res, delete_original=delete_original, speed_preset=image_speed, keep_apple_hdr=keep_apple_hdr)
        video_task = partial(process_video, source_dir=source_path, target_dir=target_path, ffmpeg_args=video_args, max_res=max_res, delete_original=delete_original, speed_preset=video_speed)
        
        # Process images with a progress bar
        if image_files:
            list(tqdm(executor.map(image_task, image_files), total=len(image_files), desc="Converting Images"))
        
        # Process videos with a progress bar
        if video_files:
            list(tqdm(executor.map(video_task, video_files), total=len(video_files), desc="Converting Videos"))

    logging.info("All tasks completed.")