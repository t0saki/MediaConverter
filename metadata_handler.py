# media_converter/metadata_handler.py

import os
import logging
from pathlib import Path
from datetime import datetime
from utils import run_command

def copy_metadata(source_path: Path, target_path: Path):
    """Copies metadata and file timestamps from source to target."""
    if not target_path.exists() or target_path.stat().st_size == 0:
        logging.warning(f"Skipping metadata copy for non-existent target: {target_path}")
        return

    # 1. Copy all tags from the source file
    cmd_copy_tags = [
        'exiftool', '-TagsFromFile', str(source_path), '-all:all', '-overwrite_original', str(target_path)
    ]
    run_command(cmd_copy_tags)

    # 2. Determine the best "creation date"
    try:
        mtime = datetime.fromtimestamp(source_path.stat().st_mtime)
        # Use exiftool to find the earliest date
        proc = run_command(['exiftool', '-j', '-DateTimeOriginal', '-CreateDate', '-ModifyDate', str(source_path)])
        if proc and proc.stdout:
            import json
            try:
                exif_data = json.loads(proc.stdout)[0]
                date_keys = ['DateTimeOriginal', 'CreateDate', 'ModifyDate']
                date_strings = [exif_data.get(k) for k in date_keys if exif_data.get(k)]
                
                # Parse dates, handling potential timezone info
                timestamps = []
                for ds in date_strings:
                    try:
                        # Format example: '2023:09:15 10:30:00+08:00' or '2023:09:15 10:30:00'
                        if '+' in ds or '-' in ds[11:]:
                             timestamps.append(datetime.strptime(ds, '%Y:%m:%d %H:%M:%S%z'))
                        else:
                             timestamps.append(datetime.strptime(ds, '%Y:%m:%d %H:%M:%S'))
                    except ValueError:
                        continue
                if timestamps:
                    mtime = min(timestamps)

            except (json.JSONDecodeError, IndexError):
                pass # Fallback to file modification time

        # 3. Write DateTimeOriginal if it's missing
        date_str = mtime.strftime('%Y:%m:%d %H:%M:%S')
        run_command(['exiftool', f'-DateTimeOriginal="{date_str}"', '-overwrite_original', str(target_path)])
        
        # 4. Set file modification and access times
        os.utime(target_path, (source_path.stat().st_atime, source_path.stat().st_mtime))
        
    except Exception as e:
        logging.error(f"Failed to copy timestamps for {source_path}: {e}")

    # 5. Clean up backup file created by exiftool
    backup_file = target_path.with_name(f"{target_path.name}_original")
    if backup_file.exists():
        backup_file.unlink()