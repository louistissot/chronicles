"""
Generate the DnD WhisperX app icon (.icns) for macOS.
Draws a D20 die on a dark background.
"""
import math
import os
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ICONSET = Path("DnDWhisperX.iconset")


def draw_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    pad = size * 0.06
    r_outer = (size - pad * 2) / 2
    cx, cy = size / 2, size / 2

    # Background circle with dark gradient feel (solid dark)
    bg_r = r_outer + pad * 0.6
    d.ellipse(
        [cx - bg_r, cy - bg_r, cx + bg_r, cy + bg_r],
        fill=(22, 22, 35, 255),
    )

    # ── D20 shape: pentagon top + trapezoid middle + triangle bottom ────────
    # We draw a rough d20 using 7 key points:
    #   top vertex, upper-left, upper-right, lower-left, lower-right, bottom-left, bottom-right + bottom vertex
    # Simplified: a regular pentagon rotated so one edge is at the top.

    def pentagon_points(cx, cy, r, angle_offset=math.pi / 2):
        pts = []
        for i in range(5):
            a = angle_offset + 2 * math.pi * i / 5
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        return pts

    r = r_outer * 0.82
    pent = pentagon_points(cx, cy, r, angle_offset=-math.pi / 2)  # top vertex at top

    # Outline (gold / amber)
    outline_color = (210, 160, 55, 255)
    face_color = (35, 35, 55, 255)
    lw = max(1, int(size * 0.022))

    # Draw the pentagon as the die face
    d.polygon(pent, fill=face_color, outline=outline_color)

    # Interior lines to suggest a d20 (divide into faces)
    # Line from top to bottom-left and bottom-right midpoints
    top = pent[0]
    upper_right = pent[1]
    lower_right = pent[2]
    lower_left = pent[3]
    upper_left = pent[4]

    center_face = (cx, cy + r * 0.08)

    line_color = (210, 160, 55, 200)
    thick = max(1, int(size * 0.016))

    def line(p1, p2, color=line_color, width=thick):
        d.line([p1, p2], fill=color, width=width)

    # Connect each vertex to the center to create 5 triangular faces
    for p in pent:
        line(p, center_face)

    # Draw the pentagon outline again on top to keep it crisp
    d.polygon(pent, outline=outline_color)
    # Redraw outline thicker
    for i in range(5):
        line(pent[i], pent[(i + 1) % 5], color=outline_color, width=lw)

    # ── "20" text ────────────────────────────────────────────────────────────
    font_size = max(10, int(r * 0.62))
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Impact.ttf", font_size)
    except Exception:
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
        except Exception:
            font = ImageFont.load_default()

    text = "20"
    bbox = d.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = cx - tw / 2 - bbox[0]
    ty = cy - th / 2 - bbox[1] + r * 0.04

    # Shadow
    shadow_offset = max(1, int(size * 0.012))
    d.text(
        (tx + shadow_offset, ty + shadow_offset),
        text, fill=(0, 0, 0, 160), font=font,
    )
    # Main text
    d.text((tx, ty), text, fill=(245, 215, 100, 255), font=font)

    # Small "D" label above "20"
    small_size = max(6, int(r * 0.22))
    try:
        small_font = ImageFont.truetype(
            "/System/Library/Fonts/Supplemental/Impact.ttf", small_size
        )
    except Exception:
        small_font = font

    d_text = "D"
    db = d.textbbox((0, 0), d_text, font=small_font)
    dw = db[2] - db[0]
    dh = db[3] - db[1]
    d.text(
        (cx - dw / 2 - db[0], ty - dh - small_size * 0.2 - db[1]),
        d_text, fill=(210, 160, 55, 230), font=small_font,
    )

    return img


def build_iconset():
    ICONSET.mkdir(exist_ok=True)
    sizes = [16, 32, 64, 128, 256, 512, 1024]
    retina_names = {
        16: ("icon_16x16.png", "icon_16x16@2x.png"),
        32: ("icon_32x32.png", "icon_32x32@2x.png"),
        64: (None, "icon_32x32@2x.png"),
        128: ("icon_128x128.png", "icon_128x128@2x.png"),
        256: ("icon_256x256.png", "icon_256x256@2x.png"),
        512: ("icon_512x512.png", "icon_512x512@2x.png"),
        1024: (None, "icon_512x512@2x.png"),
    }

    written = set()
    for size in sizes:
        img = draw_icon(size)
        names = retina_names.get(size, (f"icon_{size}x{size}.png", None))
        for name in names:
            if name and name not in written:
                img.save(ICONSET / name, "PNG")
                written.add(name)
                print(f"  {name}")

    # Convert to .icns
    os.system(f"iconutil -c icns {ICONSET}")
    icns_path = Path("DnDWhisperX.icns")
    if icns_path.exists():
        print(f"\nIcon created: {icns_path}")
    else:
        print("iconutil failed — check output above")

    shutil.rmtree(ICONSET, ignore_errors=True)


if __name__ == "__main__":
    print("Building icon...")
    build_iconset()
