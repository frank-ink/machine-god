#!/usr/bin/env python3
"""Renders the generated machine_god_art.rs as dots (exact braille geometry) to a PNG for visual review."""
import re, sys
from PIL import Image, ImageDraw
src = open(sys.argv[1]).read()
def arr(name):
    blk = re.search(name + r": \[\[&str; \d+\]; \d+\] = \[\n(.*?)\n\];", src, re.S).group(1)
    return [re.findall(r'"([^"]*)"', l) for l in blk.splitlines()]
C = {'.': (0, 0, 0), 'g': (110, 110, 110), 'w': (210, 210, 210), 'r': (150, 30, 35), 'R': (255, 45, 45)}
DOT = ((0, 0, 0x01), (0, 1, 0x02), (0, 2, 0x04), (1, 0, 0x08), (1, 1, 0x10), (1, 2, 0x20), (0, 3, 0x40), (1, 3, 0x80))
CW, CH = 8, 16  # terminal cell ~1:2
out = Image.new('RGB', (3 * (40 * CW + 12), 20 * CH + 12 * CH + 24), (0, 0, 0)); d = ImageDraw.Draw(out)
y0 = 0
for nm in ("LARGE", "SMALL"):
    A, M = arr(nm + "_ART"), arr(nm + "_MASK")
    for fi in range(len(A)):
        for y, (l, m) in enumerate(zip(A[fi], M[fi])):
            for x, (ch, c) in enumerate(zip(l, m)):
                b = ord(ch) - 0x2800
                for dx, dy, bit in DOT:
                    if b > 0 and b & bit:
                        cx, cy = fi * (40 * CW + 12) + x * CW + dx * 4 + 2, y0 + y * CH + dy * 4 + 2
                        d.ellipse((cx - 1.4, cy - 1.4, cx + 1.4, cy + 1.4), fill=C[c])
    y0 += len(A[0][0]) and len(A[0]) * CH + 12
out.save(sys.argv[2])
