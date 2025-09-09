import logging
import shutil
import subprocess
from pathlib import Path
import traceback

def setup_logging(log_file='conversion.log'):
    """Configures logging to both file and console."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )

def check_dependencies():
    """Checks if required command-line tools are installed."""
    dependencies = ['ffmpeg', 'ffprobe', 'exiftool', 'magick']
    missing = []
    for dep in dependencies:
        if not shutil.which(dep):
            missing.append(dep)
    if missing:
        logging.error(f"Missing required dependencies: {', '.join(missing)}")
        logging.error("Please install them and ensure they are in your system's PATH.")
        exit(1)
    logging.info("All required dependencies found.")

def run_command(cmd: list[str], verbose: bool = True):
    """Runs an external command and logs errors."""
    try:
        process = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',
            check=True
        )
        return process
    except subprocess.CalledProcessError as e:
        if verbose:
            logging.error(f"Command failed: {' '.join(cmd)}")
            logging.error(f"Stderr: {e.stderr.strip().encode('utf-8', errors='replace').decode('utf-8')}")
            logging.error(f"Stack: {traceback.format_exc()}")
        return None
    
    
# If the source file is a .MOV and there is a .HEIC file in the same directory, it is considered a video attached to a live photo, and CRF + 10
def is_live_photo_mov(file: Path) -> bool:
    return file.suffix.lower() == '.mov' and (file.with_suffix('.heic')).exists()
