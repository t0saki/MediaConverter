import logging
import shutil
import subprocess
from pathlib import Path

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

def run_command(cmd: list[str]):
    """Runs an external command and logs errors."""
    try:
        process = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        return process
    except subprocess.CalledProcessError as e:
        logging.error(f"Command failed: {' '.join(cmd)}")
        logging.error(f"Stderr: {e.stderr.strip()}")
        return None