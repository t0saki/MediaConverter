# Supported file extensions, case-insensitive
IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.webp', '.heic', '.heif', '.gif', '.tiff', '.tif')
VIDEO_EXTENSIONS = ('.mp4', '.avi', '.mkv', '.mov', '.mpg', '.mpeg', '.m4v', '.webm', '.ts')

# Default FFmpeg arguments for video conversion
# Encodes video to AV1 and audio to Opus for a good balance of quality and file size.
DEFAULT_VIDEO_ARGS = (
    "-c:v libsvtav1 -preset 6 -crf 45 -pix_fmt yuv420p10le "
    "-c:a libopus -b:a 96k"
)

# Speed presets for different media types
DEFAULT_IMAGE_SPEED_PRESET = 4
DEFAULT_VIDEO_SPEED_PRESET = 6

# Default maximum resolution (4032 * 3024 = 12.2MP)
DEFAULT_MAX_RESOLUTION = 4032 * 3024

# Live Photo CRF offset - when processing .MOV files that are part of Live Photos (paired with .HEIC files)
# The CRF value will be increased by this offset to reduce quality and file size for Live Photo videos
LIVE_PHOTO_CRF_OFFSET = 15