# media_converter/config.py

# Supported file extensions, case-insensitive
IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.webp', '.heic', '.heif', '.gif', '.tiff', '.tif')
VIDEO_EXTENSIONS = ('.mp4', '.avi', '.mkv', '.mov', '.mpg', '.mpeg', '.m4v', '.webm', '.ts')

# Default FFmpeg arguments for video conversion
# Encodes video to AV1 and audio to Opus for a good balance of quality and file size.
DEFAULT_VIDEO_ARGS = (
    "-c:v libsvtav1 -preset 6 -crf 35 -pix_fmt yuv420p10le "
    "-c:a libopus -b:a 96k"
)