import numpy as np
import cv2
import colour
import traceback
from imagecodecs import avif_encode

import hdrconv.io as hdr_io
import hdrconv.convert as hdr_convert
from hdrconv.identify import has_gain_map


def save_np_array_to_avif(
    np_array, output_path, quality=75, color_primaries=12, transfer_characteristics=16, speed_preset=1
):
    """
    Encode a PQ-encoded numpy array to AVIF and save to disk.

    Uses imagecodecs (libaom) for encoding with 10-bit depth.

    :param np_array: The input numpy array representing the image, range [0, 1].
    :param output_path: The path where the output image will be saved.
    :param quality: Image quality (0-100), higher means better quality but larger file size.
    :param color_primaries: Specifies the color primaries for the image.
                           - 1 for BT.709, 9 for BT.2020, 12 for P3-D65
    :param transfer_characteristics: Specifies the transfer characteristics for the image.
                                     - 1 for BT.709, 8 for Linear, 16 for PQ, 18 for HLG
    :param speed_preset: Encoding speed (0-10, lower is slower but better quality).
    """
    np_array = np.clip(np_array, 0, 1)
    np_array = (np_array * 1023.0).astype(np.uint16)

    avif_bytes: bytes = avif_encode(
        np_array,
        level=quality,
        speed=speed_preset,
        bitspersample=10,
        primaries=color_primaries,
        transfer=transfer_characteristics,
        numthreads=-1,
    )

    with open(output_path, "wb") as f:
        f.write(avif_bytes)


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
        speed_preset: Encoding speed (0-10, lower is slower but better quality).

    Returns:
        bool: True if conversion was successful, False otherwise.
    """
    try:
        # Read Apple HDR HEIC (base + gain map + headroom)
        heic_data = hdr_io.read_apple_heic(input_path)

        # Reconstruct linear HDR in Display P3 color space
        hdr = hdr_convert.apple_heic_to_hdr(heic_data)
        hdr_linear = hdr["data"]

        # Apply PQ transfer function (203 nits reference white)
        hdr_linear = np.clip(hdr_linear, 0.0, np.inf)
        hdr_pq = colour.eotf_inverse(
            hdr_linear * 203.0,
            function="ITU-R BT.2100 PQ"
        )
        hdr_pq = np.clip(hdr_pq, 0.0, 1.0).astype(np.float32)

        # Resize if needed (in PQ space, using LANCZOS4 for high quality)
        if target_width is not None and target_height is not None:
            hdr_pq = cv2.resize(
                hdr_pq,
                (target_width, target_height),
                interpolation=cv2.INTER_LANCZOS4
            )

        # Save as AVIF with HDR metadata
        save_np_array_to_avif(
            hdr_pq,
            output_path,
            quality=quality,
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
