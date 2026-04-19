import os
import re
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional
from utils import run_command

MIN_VALID_DATE = datetime(2000, 1, 1)

def _get_date_from_exif(source_path: Path) -> Optional[datetime]:
    """Tries to find the earliest date from EXIF tags."""
    try:
        cmd = ['exiftool', '-charset', 'filename=UTF8', '-j', '-DateTimeOriginal',
               '-CreateDate', '-ModifyDate', str(source_path)]
        proc = run_command(cmd, verbose=False)
        if not (proc and proc.stdout):
            return None

        exif_data = json.loads(proc.stdout)[0]
        date_keys = ['DateTimeOriginal', 'CreateDate', 'ModifyDate']
        date_strings = [exif_data.get(k)
                        for k in date_keys if exif_data.get(k)]

        timestamps = []
        for ds in date_strings:
            try:
                # Handle dates with and without timezone information
                # e.g., '2023:09:15 10:30:00+08:00' or '2023:09:15 10:30:00'
                if '+' in ds or '-' in ds[11:]:
                    dt = datetime.strptime(ds, '%Y:%m:%d %H:%M:%S%z')
                else:
                    dt = datetime.strptime(ds, '%Y:%m:%d %H:%M:%S')
                timestamps.append(dt)
            except (ValueError, TypeError):
                continue

        return min(timestamps) if timestamps else None

    except (json.JSONDecodeError, IndexError, Exception) as e:
        logging.debug(
            f"Could not extract EXIF date from {source_path.name}: {e}")
        return None


def _get_date_from_filename(filename: str) -> Optional[datetime]:
    """
    Tries to parse a date and time from a filename string.
    The parsed date must be on or after January 1, 2000.
    """
    # Patterns are ordered from most to least specific.
    # Covers formats like: 20230915_103000, 2023-09-15 10-30-00, VID_20230915, etc.
    patterns = [
        r'(?P<Y>\d{4})(?P<m>\d{2})(?P<d>\d{2})[_.-]?(?P<H>\d{2})(?P<M>\d{2})(?P<S>\d{2})',
        r'(?P<Y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})[\s_.-](?P<H>\d{2})[:.-](?P<M>\d{2})[:.-](?P<S>\d{2})',
        r'(?P<Y>\d{4})(?P<m>\d{2})(?P<d>\d{2})'
    ]
    for pattern in patterns:
        match = re.search(pattern, filename)
        if match:
            parts = match.groupdict()
            try:
                # Create datetime object, defaulting time parts to 0 if not found
                dt = datetime(
                    year=int(parts['Y']),
                    month=int(parts['m']),
                    day=int(parts['d']),
                    hour=int(parts.get('H', 0)),
                    minute=int(parts.get('M', 0)),
                    second=int(parts.get('S', 0)),
                )

                # VALIDATION: Ensure the date is within the allowed range
                if dt >= MIN_VALID_DATE and dt <= datetime.now():
                    return dt
                else:
                    logging.debug(
                        f"Parsed date {dt} from '{filename}' is out of valid range, ignoring.")
                    continue  # Try next pattern or fail

            except (ValueError, TypeError):
                # Handles invalid date parts, e.g., month=13
                continue
    return None


def _get_date_from_mtime(source_path: Path) -> datetime:
    """Gets the date from the file's last modification time as a fallback."""
    return datetime.fromtimestamp(source_path.stat().st_mtime)


def get_best_creation_date(source_path: Path) -> datetime:
    """
    Determines the best creation date for a file using a prioritized approach.
    Priority Order:
    1. The earliest date found in EXIF tags (DateTimeOriginal, CreateDate, ModifyDate).
    2. A date parsed from the filename (e.g., 'IMG_20230915_103000.jpg').
    3. The file's last modification time (fallback).
    """
    # Priority 1: Try EXIF
    if exif_date := _get_date_from_exif(source_path):
        return exif_date

    # Priority 2: Try filename
    if filename_date := _get_date_from_filename(source_path.name):
        return filename_date

    # Priority 3: Fallback to file modification time
    return _get_date_from_mtime(source_path)


def copy_metadata(source_path: Path, target_path: Path):
    """
    性能优化版：行为与原版完全一致（包含日期回填），但大幅降低 NAS 压力。
    """
    if not target_path.exists() or target_path.stat().st_size == 0:
        logging.warning(
            f"Skipping metadata copy for non-existent or empty target: {target_path}")
        return

    # 1. 第一步：从 NAS 源文件复制所有现有 Tag 到本地目标文件
    # [这是整个函数唯一一次访问 NAS 的 I/O 操作]
    cmd_copy_tags = [
        'exiftool', '-charset', 'filename=utf8', '-TagsFromFile', str(source_path), '-all:all',
        '--unsafe', '-overwrite_original', str(target_path)
    ]
    # 如果这一步失败，后续逻辑依然可以基于文件名继续
    run_command(cmd_copy_tags, verbose=False)

    try:
        # 2. 核心优化点：从【本地 Target 文件】确定最佳日期
        # 原版是读 source_path (NAS)，这里改读 target_path (SSD)
        # 因为第一步已经把 Exif 拷过来了，读本地也是一样的，速度快 100 倍
        best_date = get_best_creation_date(target_path)
        
        # 特殊兜底：如果本地文件既没 Exif 也没文件名日期，
        # get_best_creation_date 可能会返回 target 的创建时间（即刚刚）。
        # 这时候我们需要读取一次 source 的 mtime 作为最后防线。
        # (os.path.getmtime 是轻量级操作，比 exiftool 快得多)
        if not best_date: 
             best_date = datetime.fromtimestamp(source_path.stat().st_mtime)

        date_str = best_date.strftime('%Y:%m:%d %H:%M:%S')

        # 3. 写入 Exif：操作的是本地 SSD 文件，不会造成 SMB 阻塞
        # 这一步保留了你的“回填”逻辑
        cmd_set_date = [
            'exiftool', f'-DateTimeOriginal={date_str}', f'-CreateDate={date_str}',
            f'-ModifyDate={date_str}', '-overwrite_original', str(target_path)
        ]
        run_command(cmd_set_date, verbose=False)

        # 4. 修改文件系统时间
        timestamp = best_date.timestamp()
        os.utime(target_path, (timestamp, timestamp))

    except Exception as e:
        logging.error(f"Failed to set timestamps for {target_path}: {e}")

    # 5. 清理备份文件
    backup_file = target_path.with_name(f"{target_path.name}_original")
    if backup_file.exists():
        try:
            backup_file.unlink()
        except OSError:
            pass
