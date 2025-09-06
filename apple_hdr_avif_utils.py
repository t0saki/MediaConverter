import numpy as np
from PIL import Image
import pillow_heif
import cv2
import traceback
from hdr_conversion.utils import pq_eotf_inverse
from hdr_conversion.apple_heic.color_conversion import apply_gain_map
from hdr_conversion.apple_heic.get_images import read_base_and_gain_map
from hdr_conversion.apple_heic.headroom import get_headroom
from hdr_conversion.apple_heic.identify import has_gain_map


"""
Note: pillow_heif no longer supports AVIF after version 0.22.0 since pillow already supports AVIF natively.

Need to transfer the AVIF saving functionality to use pillow's native support for AVIF.
"""


# Save HDR image
def save_np_array_to_avif(
    np_array, output_path, color_primaries=12, transfer_characteristics=16, speed_preset=1
):
    """
    Convert a numpy array to a HEIF/AVIF image and save it to the specified output path.

    :param np_array: The input numpy array representing the image.
    :param output_path: The path where the output image will be saved.
    :param color_primaries: Specifies the color primaries for the image.
                           - 1 for BT.709, 9 for BT.2020, 12 for P3-D65
    :param transfer_characteristics: Specifies the transfer characteristics for the image.
                                     - 1 for BT.709, 8 for Linear, 16 for PQ, 18 for HLG
    """
    # Normalize the numpy array to the range [0, 1] and then scale it to [0, 65535]
    np_array = np.clip(np_array, 0, 1)
    np_array = np_array * 65535
    np_array = np_array.astype(np.uint16)

    # Create a HEIF image from the numpy array
    img = pillow_heif.from_bytes(
        mode="RGB;16",
        size=(np_array.shape[1], np_array.shape[0]),
        data=np_array.tobytes(),
    )

    # Define the save parameters
    kwargs = {
        "format": "AVIF",
        "color_primaries": color_primaries,
        "transfer_characteristics": transfer_characteristics,
        "enc_params": {"aom:cpu-used": speed_preset},
    }

    # Save the image to the specified output path
    img.save(output_path, **kwargs)


def convert_apple_hdr_to_avif(
    input_path: str,
    output_path: str,
    quality: int = 75,
    target_width: int | None = None,
    target_height: int | None = None,
    speed_preset: int = 1
):
    """
    Convert Apple HDR HEIC image to AVIF format with HDR support, with optional resizing.
    
    Args:
        input_path: Path to the input Apple HDR HEIC file.
        output_path: Path where the output AVIF file will be saved.
        quality: Image quality (0-100), higher means better quality but larger file size.
        target_width: The target width for the output image. If specified, requires target_height.
        target_height: The target height for the output image. If specified, requires target_width.
    
    Returns:
        bool: True if conversion was successful, False otherwise.
    """
    try:
        pillow_heif.options.QUALITY = quality
        # Read base image and gain map from Apple HDR HEIC
        base_image, gain_map = read_base_and_gain_map(input_path)
        headroom = get_headroom(input_path)

        if base_image is None or gain_map is None or headroom is None:
            print(
                f"Failed to retrieve necessary image data or metadata from {input_path}")
            return False

        # Apply gain map to reconstruct HDR image
        hdr_image_linear = apply_gain_map(base_image, gain_map, headroom)

        # Scale and convert to PQ space
        hdr_image_linear = hdr_image_linear * 203.0
        hdr_image_pq = pq_eotf_inverse(hdr_image_linear)

        if target_width is not None and target_height is not None:
            # print(
            #     f"Original dimensions: ({hdr_image_pq.shape[1]}, {hdr_image_pq.shape[0]})")
            # print(
            #     f"Resizing image to {target_width}x{target_height} using LANCZOS filter...")

            # Use cv2.resize directly on the float32 NumPy array.
            # cv2.INTER_LANCZOS4 is the equivalent high-quality resampling method.
            hdr_image_pq = cv2.resize(
                hdr_image_pq,
                (target_width, target_height),
                interpolation=cv2.INTER_LANCZOS4
            )

        # print(
        #     f"hdr pq np info: shape={hdr_image_pq.shape}, dtype={hdr_image_pq.dtype}, min={np.min(hdr_image_pq)}, max={np.max(hdr_image_pq)}")
        # Save as AVIF with HDR metadata
        save_np_array_to_avif(
            hdr_image_pq,
            output_path,
            color_primaries=12,  # P3-D65
            transfer_characteristics=16,  # PQ
            speed_preset=speed_preset
        )

        return True

    except Exception as e:
        print(f"Error converting {input_path} to AVIF: {traceback.format_exc()}")
        return False


if __name__ == "__main__":
    # Example usage
    input_file = "example.heic"

    # --- Example 1: Convert without resizing ---
    output_file_original = "example_original.avif"
    print(
        f"--- Converting {input_file} to {output_file_original} at original size ---")
    success_original = convert_apple_hdr_to_avif(
        input_file, output_file_original, quality=50)
    if success_original:
        print("Original size conversion completed successfully!\n")
    else:
        print("Original size conversion failed!\n")

    # --- Example 2: Convert with resizing to 1200x900 ---
    output_file_resized = "example_resized.avif"
    print(
        f"--- Converting {input_file} to {output_file_resized} with resizing ---")
    success_resized = convert_apple_hdr_to_avif(
        input_file,
        output_file_resized,
        quality=50,
        target_width=900,
        target_height=1200
    )
    if success_resized:
        print("Resized conversion completed successfully!")
    else:
        print("Resized conversion failed!")

    # Test has_gain_map function speed
    print(f"\n--- Testing has_gain_map on {input_file} ---")
    import time
    start_time = time.time()
    for _ in range(10):
        has_gain_map(input_file)
    end_time = time.time()
    print(f"has_gain_map average time: {(end_time - start_time) / 10:.4f} seconds")