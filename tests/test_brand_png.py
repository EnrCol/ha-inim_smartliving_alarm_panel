"""Validate custom local brand PNGs, including CRC and completeness (no Pillow dependency)."""
from pathlib import Path
import struct
import zlib
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "inim_smartliving_alarm" / "brand"
SIGNATURE = b"\x89PNG\r\n\x1a\n"

def check_png(data: bytes) -> tuple[int, int]:
    if not data.startswith(SIGNATURE):
        raise ValueError("invalid signature")
    offset = len(SIGNATURE)
    dimensions = None
    found_idat = False
    found_iend = False
    while offset < len(data):
        if offset + 12 > len(data):
            raise ValueError("truncated PNG chunk")
        length = struct.unpack_from(">I", data, offset)[0]
        kind = data[offset + 4:offset + 8]
        end = offset + 8 + length
        if end + 4 > len(data):
            raise ValueError("truncated PNG payload")
        stored = struct.unpack_from(">I", data, end)[0]
        actual = zlib.crc32(data[offset + 4:end]) & 0xFFFFFFFF
        if stored != actual:
            raise ValueError(f"bad CRC on {kind!r}")
        if offset == len(SIGNATURE):
            if kind != b"IHDR" or length != 13:
                raise ValueError("missing first IHDR")
            dimensions = struct.unpack_from(">II", data, offset + 8)
        if kind == b"IDAT":
            found_idat = True
        offset = end + 4
        if kind == b"IEND":
            found_iend = length == 0 and offset == len(data)
            break
    if not (found_iend and found_idat and dimensions == (256, 256)):
        raise ValueError("invalid complete 256x256 PNG")
    return dimensions

class BrandTests(unittest.TestCase):
    def test_icon_and_logo(self):
        for filename in ("icon.png", "logo.png"):
            with self.subTest(filename=filename):
                self.assertEqual(check_png((ROOT / filename).read_bytes()), (256, 256))

    def test_corruption_detected(self):
        image = bytearray((ROOT / "icon.png").read_bytes())
        image[50] ^= 1
        with self.assertRaises(ValueError):
            check_png(image)
