"""Generate the TallyCraft icon: tally marks (|||| with a slash) beside an
outlined crate, on a plywood-colored rounded tile.

Writes assets/tallycraft.ico (multi-size) and assets/tallycraft.png.
Run:  python tools/make_icon.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

S = 1024  # master canvas; downsampled for each icon size
BG = (222, 184, 135, 255)      # plywood / burlywood
BG_EDGE = (160, 110, 60, 255)
INK = (52, 38, 28, 255)        # dark walnut
ACCENT = (178, 34, 34, 255)    # tally slash

OUT = Path(__file__).resolve().parents[1] / "assets"


def draw_master() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = 40
    d.rounded_rectangle([pad, pad, S - pad, S - pad], radius=180, fill=BG, outline=BG_EDGE, width=28)

    stroke = 70
    # Tally marks: four verticals, left half
    top, bottom = 250, 770
    xs = [150, 250, 350, 450]
    for x in xs:
        d.line([(x, top), (x, bottom)], fill=INK, width=stroke)
    # Diagonal slash through them
    d.line([(95, 700), (515, 320)], fill=ACCENT, width=stroke)

    # Crate: outlined box with a lid line and a diagonal brace, right half
    x0, y0, x1, y1 = 560, 330, 900, 770
    w = 60
    d.rectangle([x0, y0, x1, y1], outline=INK, width=w)
    lid_y = y0 + 115
    d.line([(x0, lid_y), (x1, lid_y)], fill=INK, width=w - 10)
    d.line([(x0 + w // 2, y1 - w // 2), (x1 - w // 2, lid_y + w // 2)], fill=INK, width=w - 16)
    return img


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    master = draw_master()
    master.resize((256, 256), Image.LANCZOS).save(OUT / "tallycraft.png")
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    master.save(OUT / "tallycraft.ico", sizes=sizes)
    print(f"Wrote {OUT / 'tallycraft.ico'} and {OUT / 'tallycraft.png'}")


if __name__ == "__main__":
    main()
