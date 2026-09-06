#!/usr/bin/env python3
"""Generate a standard multi-size BMP-based icon.ico for Tauri's Windows resource
file, using only the Python standard library (no Pillow needed).

Draws a simple blue circle on a transparent background. Sizes: 16/32/48/256.
Traditional ICO layout (BITMAPINFOHEADER + BGRA XOR + AND mask) is what MinGW
windres expects, so it compiles cleanly.
"""
import struct

OUT = "D:/codex/pet/src-tauri/icons/icon.ico"


def blue_circle(x, y, s):
    cx = cy = (s - 1) / 2.0
    r = s * 0.42
    dx, dy = x - cx, y - cy
    if dx * dx + dy * dy <= r * r:
        # radial-ish blue, lighter toward top-left
        t = (dx + dy) / (2 * r)  # -1..1
        g = int(156 + 40 * max(0.0, -t))
        b = int(255 - 20 * max(0.0, t))
        return (40, min(220, g), min(255, b), 255)
    return (0, 0, 0, 0)


def build_rgba(size):
    rows = []
    for y in range(size):
        row = [blue_circle(x, y, size) for x in range(size)]
        rows.append(row)
    return rows


def dib(size, rows):
    # BITMAPINFOHEADER
    info = struct.pack(
        "<IiiHHIIiiII",
        40,            # biSize
        size,          # biWidth
        size * 2,      # biHeight (XOR + AND)
        1,             # biPlanes
        32,            # biBitCount
        0,             # biCompression (BI_RGB)
        0,             # biSizeImage
        0, 0, 0, 0,    # x/y ppm, clrused, clrimportant
    )
    pixel = b""
    for y in reversed(range(size)):          # bottom-up
        for x in range(size):
            r, g, b, a = rows[y][x]
            pixel += bytes((b, g, r, a))     # BGRA
    row_bytes = ((size + 31) // 32) * 4
    andmask = b"\x00" * (row_bytes * size)   # all-zero => fully opaque
    return info + pixel + andmask


def main():
    sizes = [16, 32, 48, 256]
    entries = []
    for s in sizes:
        entries.append((s, dib(s, build_rgba(s))))
    icondir = struct.pack("<HHH", 0, 1, len(entries))
    offset = 6 + 16 * len(entries)
    data = b""
    direntries = b""
    for s, d in entries:
        w = 0 if s >= 256 else s
        h = 0 if s >= 256 else s
        direntries += struct.pack(
            "<BBBBHHII", w, h, 0, 0, 1, 32, len(d), offset + len(data)
        )
        data += d
    ico = icondir + direntries + data
    with open(OUT, "wb") as f:
        f.write(ico)
    print("wrote", OUT, "bytes=", len(ico), "entries=", len(entries))


if __name__ == "__main__":
    main()
