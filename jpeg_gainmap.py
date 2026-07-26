"""Gain-map JPEG (ISO 21496-1 / Google "Ultra HDR") -> 10-bit PQ AVIF.

Why this exists
---------------
An HDR photo out of Lightroom is an SDR base image plus a *gain map*: a second picture whose
pixels say how much to brighten each part of the base to recover the HDR rendition. Neither
ImageMagick nor Pillow decodes that second image, so before this module a gain-map JPEG came out
of the converter as plain SDR — with the source's `hdrgm:` / `crs:HDR*` XMP copied along, leaving
an SDR AVIF that claimed to be HDR.

`apple_hdr_avif_utils` already solves the same problem for Apple HEIC. This module is the JPEG
front-end for that same back-end: decode base + gain map to linear light, then hand the array to
`save_np_array_to_avif` as PQ. AVIF *can* carry a gain map natively (an ISO 21496-1 `tmap` item),
but Chrome still hides that behind `chrome://flags/#avif-gainmap-hdr-images`, so a single PQ
stream is what actually reaches a viewer's screen today. The trade-off is that PQ has no clean
SDR fallback — an SDR display gets the browser's tone map, not the graded base.

Ported from raw-sorter's `src/raw_sorter/hdr.py` (v0.3.0), which validated the composition against
libultrahdr's own decode (mean |delta| 0.00066). Kept to the JPEG paths only; the AVIF/JXL
readers there need ffmpeg/djxl and have no caller here.

Internal representation: `float32 HxWx3`, **linear light, SDR diffuse white = 1.0**, in the
primaries named by a CICP code.
"""
from __future__ import annotations

import io
import logging
import re
import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

# --- CICP colour primaries (ITU-T H.273) ------------------------------------------------------
CICP_BT709 = 1      # also sRGB
CICP_BT2020 = 9
CICP_P3_D65 = 12    # SMPTE EG 432-1 "Display P3"

# D50-adapted ICC colorants (rXYZ/gXYZ/bXYZ) for the profiles that turn up on real HDR JPEGs.
# The PCS is always D50, so these values are fixed regardless of ICC version — matching them is
# simpler and more robust than un-adapting through the `chad` tag, and the three spaces are far
# enough apart that a loose tolerance still discriminates them. A profile that matches none of
# them (Adobe RGB, say, which CICP cannot express) sends the file down the SDR path instead,
# where the ICC is carried through verbatim and the colours stay right.
_ICC_COLORANTS = {
    CICP_BT709: ((0.43607, 0.22249, 0.01392), (0.38515, 0.71687, 0.09708), (0.14307, 0.06061, 0.71410)),
    CICP_P3_D65: ((0.51512, 0.24120, -0.00105), (0.29198, 0.69225, 0.04189), (0.15710, 0.06657, 0.78407)),
    CICP_BT2020: ((0.67347, 0.27923, -0.00193), (0.16562, 0.67573, 0.02995), (0.12501, 0.04504, 0.79685)),
}
_ICC_TOLERANCE = 0.02

_ISO_URN = b"urn:iso:std:iso:ts:21496:-1\x00"

# Every APP segment of a JPEG lives well inside the first MiB (EXIF and XMP are capped at 64 KB
# each). Probing reads this much, not the whole file — it runs on every photo in the tree.
_JPEG_SCAN = 1 << 20


def srgb_to_linear(x: np.ndarray) -> np.ndarray:
    """sRGB / Display-P3 EOTF (the piecewise curve, not the 2.2 approximation)."""
    return np.where(x <= 0.04045, x / 12.92, np.power((x + 0.055) / 1.055, 2.4)).astype(np.float32)


# ==============================================================================================
# ISO 21496-1 gain map metadata
# ==============================================================================================
@dataclass(frozen=True)
class GainMapMeta:
    """The ISO 21496-1 parameters, per channel, with the log2 fields already in log2 space."""
    base_headroom: float                      # log2 headroom of the base rendition
    alt_headroom: float                       # log2 headroom of the alternate rendition
    gain_min: tuple[float, float, float]      # log2
    gain_max: tuple[float, float, float]      # log2
    gamma: tuple[float, float, float]
    base_offset: tuple[float, float, float]
    alt_offset: tuple[float, float, float]
    use_base_colour_space: bool = True

    @property
    def base_is_hdr(self) -> bool:
        """True when the *base* is the HDR rendition and the gain map recovers an SDR one."""
        return self.base_headroom > self.alt_headroom


def _triple(values: list[float]) -> tuple[float, float, float]:
    return (values[0], values[1 % len(values)], values[2 % len(values)])


def parse_iso21496(payload: bytes) -> GainMapMeta:
    """Parse the ISO 21496-1 binary metadata blob from a JPEG APP2 segment.

    Layout: minimum_version(u16) writer_version(u16) flags(u8),
            base_hdr_headroom(i32/u32) alternate_hdr_headroom(i32/u32),
            then per channel (1 or 3): gain_min, gain_max, gamma, base_offset, alt_offset
            — each a signed numerator + unsigned denominator pair.
    """
    if len(payload) < 21:
        raise ValueError(f"ISO 21496-1 payload too short: {len(payload)} bytes")
    _min_ver, _writer_ver = struct.unpack(">HH", payload[0:4])
    flags = payload[4]
    multichannel = bool(flags & 0x80)
    use_base_cs = bool(flags & 0x40)
    bn, bd, an, ad = struct.unpack(">iIiI", payload[5:21])
    channels = 3 if multichannel else 1
    need = 21 + 40 * channels
    if len(payload) < need:
        raise ValueError(f"ISO 21496-1 payload truncated: {len(payload)} < {need}")

    def frac(n: int, d: int) -> float:
        return float(n) / float(d) if d else 0.0

    gmin: list[float] = []
    gmax: list[float] = []
    gam: list[float] = []
    boff: list[float] = []
    aoff: list[float] = []
    off = 21
    for _ in range(channels):
        v = struct.unpack(">iIiIIIiIiI", payload[off:off + 40])
        off += 40
        gmin.append(frac(v[0], v[1]))
        gmax.append(frac(v[2], v[3]))
        gam.append(frac(v[4], v[5]) or 1.0)
        boff.append(frac(v[6], v[7]))
        aoff.append(frac(v[8], v[9]))
    return GainMapMeta(
        base_headroom=frac(bn, bd), alt_headroom=frac(an, ad),
        gain_min=_triple(gmin), gain_max=_triple(gmax), gamma=_triple(gam),
        base_offset=_triple(boff), alt_offset=_triple(aoff),
        use_base_colour_space=use_base_cs,
    )


_XMP_ATTR = r'{0}\s*=\s*"([^"]*)"'
_XMP_ELEM = r"<{0}[^>]*>(.*?)</{0}>"


def _xmp_values(xmp: str, name: str) -> list[float] | None:
    """Read an `hdrgm:` property that may be a single value or an rdf:Seq of three."""
    m = re.search(_XMP_ATTR.format(re.escape(f"hdrgm:{name}")), xmp)
    if m:
        return [float(m.group(1))]
    m = re.search(_XMP_ELEM.format(re.escape(f"hdrgm:{name}")), xmp, re.S)
    if not m:
        return None
    items = re.findall(r"<rdf:li[^>]*>([^<]*)</rdf:li>", m.group(1))
    if items:
        return [float(v.strip()) for v in items]
    text = m.group(1).strip()
    return [float(text)] if text else None


def parse_hdrgm_xmp(xmp: str) -> GainMapMeta:
    """Fallback metadata route: Adobe's `hdrgm:` XMP on the gain map image.

    Unlike the ISO binary form, `GainMapMin/Max` here are *linear* content-boost multipliers, so
    they get log2'd; the defaults come from the hdr-gain-map 1.0 spec.
    """
    def get(name: str, default: float) -> list[float]:
        return _xmp_values(xmp, name) or [default]

    gmin = [float(np.log2(max(v, 1e-6))) for v in get("GainMapMin", 1.0)]
    gmax = [float(np.log2(max(v, 1e-6))) for v in get("GainMapMax", 2.0)]
    gamma = [v or 1.0 for v in get("Gamma", 1.0)]
    boff = get("OffsetSDR", 1.0 / 64.0)
    aoff = get("OffsetHDR", 1.0 / 64.0)
    cap_min = get("HDRCapacityMin", 0.0)[0]
    cap_max = get("HDRCapacityMax", max(gmax))[0]
    flag = re.search(_XMP_ATTR.format(re.escape("hdrgm:BaseRenditionIsHDR")), xmp) \
        or re.search(_XMP_ELEM.format(re.escape("hdrgm:BaseRenditionIsHDR")), xmp, re.S)
    is_hdr = bool(flag) and flag.group(1).strip().lower() == "true"
    return GainMapMeta(
        base_headroom=cap_max if is_hdr else cap_min,
        alt_headroom=cap_min if is_hdr else cap_max,
        gain_min=_triple(gmin), gain_max=_triple(gmax), gamma=_triple(gamma),
        base_offset=_triple(boff), alt_offset=_triple(aoff),
    )


def apply_gain_map(base_lin: np.ndarray, gain: np.ndarray, meta: GainMapMeta,
                   max_headroom: float = 0.0) -> np.ndarray:
    """Composite a gain map onto a linear base, per ISO 21496-1.

        rec      = gain ** (1/gamma)
        logBoost = gain_min + (gain_max - gain_min) * rec
        out      = (base + base_offset) * 2**(logBoost * weight) - alt_offset

    `weight` is 1 for the full alternate rendition; `max_headroom` (log2, 0 = unlimited) scales it
    down the way a display with less headroom would, which is the spec-sanctioned way to cap peak
    brightness rather than clipping the boost.
    """
    span = meta.alt_headroom - meta.base_headroom
    weight = 1.0
    if max_headroom > 0 and span > 0:
        weight = float(np.clip((max_headroom - meta.base_headroom) / span, 0.0, 1.0))

    h, w = base_lin.shape[:2]
    out = np.empty_like(base_lin)
    for c in range(3):
        g = gain[..., c if gain.shape[2] == 3 else 0].astype(np.float32)
        rec = np.power(g, np.float32(1.0 / meta.gamma[c]))
        log_boost = meta.gain_min[c] + (meta.gain_max[c] - meta.gain_min[c]) * rec
        np.exp2(log_boost * np.float32(weight), out=log_boost)
        out[..., c] = (base_lin[..., c] + np.float32(meta.base_offset[c])) * log_boost \
            - np.float32(meta.alt_offset[c])
    np.clip(out, 0.0, None, out=out)
    logging.debug("gain map applied: %dx%d weight=%.3f headroom base=%.3f alt=%.3f peak=%.2f",
                  w, h, weight, meta.base_headroom, meta.alt_headroom, float(out.max()))
    return out


# ==============================================================================================
# JPEG container walking
# ==============================================================================================
def _jpeg_segments(data: bytes, start: int = 0):
    """Yield (marker, payload_offset, payload) for JPEG marker segments, stopping at SOS.

    `payload_offset` is an absolute offset into `data`, which MPF needs to resolve its own
    TIFF-relative pointers.
    """
    off = start + 2
    n = len(data)
    while off + 4 <= n:
        if data[off] != 0xFF:
            return
        marker = data[off + 1]
        if marker == 0xD8 or marker == 0x01 or 0xD0 <= marker <= 0xD7:
            off += 2
            continue
        if marker == 0xDA or marker == 0xD9:
            return
        length = struct.unpack(">H", data[off + 2:off + 4])[0]
        if length < 2 or off + 2 + length > n:
            return
        yield marker, off + 4, data[off + 4:off + 2 + length]
        off += 2 + length


def _mpf_images(data: bytes) -> list[tuple[int, int, int]]:
    """Parse the MPF (Multi-Picture Format) index -> [(attribute, offset, size), ...].

    Offsets are absolute file offsets; the first entry is the primary image, whose stored offset
    is 0 by definition. Every other offset is relative to the MPF TIFF header.
    """
    for marker, seg_off, payload in _jpeg_segments(data):
        if marker != 0xE2 or not payload.startswith(b"MPF\x00"):
            continue
        tiff = seg_off + 4
        bo = ">" if data[tiff:tiff + 2] == b"MM" else "<"
        try:
            ifd = struct.unpack(bo + "I", data[tiff + 4:tiff + 8])[0]
            p = tiff + ifd
            count = struct.unpack(bo + "H", data[p:p + 2])[0]
            p += 2
            entries: dict[int, bytes] = {}
            for _ in range(count):
                tag, _typ, _cnt = struct.unpack(bo + "HHI", data[p:p + 8])
                entries[tag] = data[p + 8:p + 12]
                p += 12
            if 0xB002 not in entries or 0xB001 not in entries:
                return []
            table = tiff + struct.unpack(bo + "I", entries[0xB002])[0]
            num = struct.unpack(bo + "I", entries[0xB001])[0]
            out: list[tuple[int, int, int]] = []
            for i in range(min(num, 16)):
                attr, size, off, _d1, _d2 = struct.unpack(
                    bo + "IIIHH", data[table + 16 * i:table + 16 * i + 16])
                out.append((attr, 0 if i == 0 else tiff + off, size))
            return out
        except (struct.error, IndexError):
            return []
    return []


def _gain_map_signal(sub: bytes) -> str | None:
    """Look for a gain map marker in one MPF sub-image's header."""
    for marker, _seg_off, payload in _jpeg_segments(sub):
        if marker == 0xE2 and payload.startswith(_ISO_URN):
            return "iso21496"
        if marker == 0xE1 and b"ns.adobe.com/hdr-gain-map/" in payload:
            return "hdrgm-xmp"
    return None


def has_jpeg_gain_map(path: str | Path) -> bool:
    """A gain-map JPEG is MPF with >= 2 images *and* an explicit gain map signal.

    The `and` matters: plenty of ordinary camera JPEGs (Panasonic, Sony, ...) carry a second MPF
    image that is only a preview thumbnail. Keying off MPF alone flags every one of them.

    Header reads only — this runs on every photo in the tree.
    """
    try:
        with Path(path).open("rb") as fh:
            if fh.read(2) != b"\xff\xd8":
                return False
            fh.seek(0)
            images = _mpf_images(fh.read(_JPEG_SCAN))
            for _attr, off, size in images[1:]:
                if off <= 0:
                    continue
                fh.seek(off)
                if _gain_map_signal(fh.read(min(size, _JPEG_SCAN))):
                    return True
    except Exception:  # detection must never break the encode
        logging.debug("gain map probe failed for %s", path, exc_info=True)
    return False


# ==============================================================================================
# ICC -> primaries
# ==============================================================================================
def icc_primaries(icc: bytes | None) -> int | None:
    """CICP primaries code from an ICC profile's D50-adapted colorant tags, or None if unknown."""
    if not icc or len(icc) < 132:
        return None
    try:
        count = struct.unpack(">I", icc[128:132])[0]
        tags: dict[bytes, bytes] = {}
        for i in range(min(count, 200)):
            sig, off, size = struct.unpack(">4sII", icc[132 + 12 * i:144 + 12 * i])
            if off + size <= len(icc):
                tags[sig] = icc[off:off + size]
        got = []
        for sig in (b"rXYZ", b"gXYZ", b"bXYZ"):
            t = tags.get(sig)
            if not t or t[:4] != b"XYZ " or len(t) < 20:
                return None
            got.append(tuple(v / 65536.0 for v in struct.unpack(">3i", t[8:20])))
    except (struct.error, IndexError):
        return None
    for code, ref in _ICC_COLORANTS.items():
        if all(abs(a - b) <= _ICC_TOLERANCE for gc, rc in zip(got, ref) for a, b in zip(gc, rc)):
            return code
    return None


# ==============================================================================================
# Decode
# ==============================================================================================
def _resize_uint8(arr: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    """Bilinear upsample of a gain map to the base's size (ISO 21496-1 assumes linear filtering)."""
    chans = [
        np.asarray(Image.fromarray(np.ascontiguousarray(arr[..., c])).resize(size, Image.BILINEAR),
                   dtype=np.uint8)
        for c in range(arr.shape[2])
    ]
    return np.stack(chans, axis=-1)


def load_jpeg_gainmap(path: str | Path, max_headroom: float = 0.0) -> tuple[np.ndarray, int]:
    """Decode a gain-map JPEG to (linear float32 HxWx3 with SDR white = 1.0, CICP primaries)."""
    data = Path(path).read_bytes()
    images = _mpf_images(data)
    if len(images) < 2:
        raise RuntimeError("MPF index vanished between probe and decode")

    with Image.open(io.BytesIO(data)) as im:
        base_rgb = im.convert("RGB")
        icc = im.info.get("icc_profile")
    # No profile means sRGB (the JPEG default, and what Ultra HDR uses). A profile we cannot map
    # to a CICP code — Adobe RGB, a printer profile — must not be silently relabelled sRGB, so
    # give up and let the SDR path carry the ICC through unchanged.
    primaries = CICP_BT709 if not icc else icc_primaries(icc)
    if primaries is None:
        raise RuntimeError("gain-map JPEG with an ICC profile CICP cannot express")
    base = np.asarray(base_rgb, dtype=np.uint8)
    del base_rgb

    # The gain map lives in a later MPF image; its APP2/XMP carries the parameters.
    meta = None
    gain_img = None
    for _attr, off, size in images[1:]:
        if off <= 0 or off + size > len(data):
            continue
        segments = list(_jpeg_segments(data, off))
        found = None
        for marker, _seg_off, payload in segments:
            if marker == 0xE2 and payload.startswith(_ISO_URN):
                found = parse_iso21496(payload[len(_ISO_URN):])
                break
        if found is None:
            for marker, _seg_off, payload in segments:
                if marker == 0xE1 and payload.startswith(b"http://ns.adobe.com/xap/1.0/\x00"):
                    text = payload[29:].decode("utf-8", "replace")
                    if "hdr-gain-map" in text:
                        found = parse_hdrgm_xmp(text)
                    break
        if found is None:
            continue
        meta = found
        with Image.open(io.BytesIO(data[off:off + size])) as gm:
            gain_img = np.asarray(gm.convert("L" if gm.mode in ("L", "1") else "RGB"),
                                  dtype=np.uint8)
        break
    if meta is None or gain_img is None:
        raise RuntimeError("no ISO 21496-1 / hdrgm metadata on the gain map image")
    if meta.base_is_hdr:
        raise RuntimeError("BaseRenditionIsHDR on a JPEG base — not a valid SDR base")

    if gain_img.ndim == 2:
        gain_img = gain_img[..., None]
    if gain_img.shape[:2] != base.shape[:2]:
        gain_img = _resize_uint8(gain_img, (base.shape[1], base.shape[0]))

    base_lin = srgb_to_linear(base.astype(np.float32) / 255.0)
    del base
    gain = gain_img.astype(np.float32) / 255.0
    del gain_img
    linear = apply_gain_map(base_lin, gain, meta, max_headroom)
    del base_lin, gain
    return linear, primaries


# ==============================================================================================
# Encode
# ==============================================================================================
def convert_jpeg_gainmap_to_avif(
    input_path: str,
    output_path: str,
    quality: int = 75,
    target_width: int | None = None,
    target_height: int | None = None,
    speed_preset: int = 1,
    max_headroom: float = 0.0,
) -> bool:
    """Convert a gain-map JPEG to a 10-bit PQ AVIF, with optional resizing.

    Mirrors `convert_apple_hdr_to_avif` — same PQ reference white and the same encoder — so the
    two HDR sources land on identical output signalling.

    Returns True on success, False on any failure (the caller then falls back to the SDR path).
    """
    import traceback

    import cv2
    import colour

    from apple_hdr_avif_utils import save_np_array_to_avif

    try:
        hdr_linear, primaries = load_jpeg_gainmap(input_path, max_headroom=max_headroom)

        # Apply PQ transfer function (203 nits reference white, BT.2408)
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

        save_np_array_to_avif(
            hdr_pq,
            output_path,
            quality=quality,
            color_primaries=primaries,
            transfer_characteristics=16,  # PQ
            speed_preset=speed_preset
        )
        return True

    except Exception:
        print(f"Error converting gain-map JPEG {input_path} to AVIF: {traceback.format_exc()}")
        return False


# ==============================================================================================
# XMP hygiene
# ==============================================================================================
def strip_stale_hdr_tags(target_path: str | Path) -> None:
    """Remove gain-map XMP that no longer describes the converted file.

    The source JPEG's primary image carries `hdrgm:Version` / `crs:HDREditMode` / `crs:HDRMaxValue`,
    and `copy_metadata`'s `-TagsFromFile -all:all` brings them across wholesale. That leaves an SDR
    AVIF claiming to have a gain map, and a PQ AVIF claiming a gain map it has already baked in.
    Either way a viewer can be misled, so both paths drop them.
    """
    from utils import run_command

    run_command([
        'exiftool', '-charset', 'filename=utf8',
        '-XMP-hdrgm:all=', '-XMP-crs:HDREditMode=', '-XMP-crs:HDRMaxValue=',
        '-overwrite_original', str(target_path)
    ], verbose=False)
