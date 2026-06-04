"""Generate all STOOP brand icons from the Night & Brick + palette.

Three ascending bars — stoop steps + bar chart ascending.
Left: dark brick  ·  Centre: brick #D96444  ·  Right: amber #F0B845
Background: midnight navy #080C14 with rounded corners.

Outputs:
  assets/icon.ico              — main app icon (16/24/32/48/64/128/256)
  assets/icon-512.png          — master PNG (for reference / future use)
  ../../overlay/src-tauri/icons/icon.png        — Tauri master (512x512)
  ../../overlay/src-tauri/icons/icon.ico        — Tauri ICO
  ../../overlay/src-tauri/icons/128x128.png
  ../../overlay/src-tauri/icons/128x128@2x.png  (256x256)
  ../../overlay/src-tauri/icons/32x32.png

Regenerate:  uv run python assets/make_icon.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
OVERLAY_ICONS = HERE / "../../overlay/src-tauri/icons"

# ── Palette ────────────────────────────────────────────────────────────────
BG       = (8,   12,  20)   # #080C14  midnight navy
BAR_DIM  = (107, 61,  40)   # #6B3D28  dark brick (left/shortest bar)
BAR_MID  = (217, 100, 68)   # #D96444  brick+     (centre bar)
BAR_TALL = (240, 184, 69)   # #F0B845  amber+     (right/tallest bar)


def render(size: int) -> Image.Image:
    """Render the STOOP three-bars mark at *size* × *size* pixels."""
    S = size
    radius = max(2, round(S * 0.20))  # ~20% corner radius, min 2px

    # ── Background tile ────────────────────────────────────────────────────
    img  = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([0, 0, S - 1, S - 1], radius=radius, fill=(*BG, 255))

    # ── Three ascending bars ───────────────────────────────────────────────
    # Proportions are designed to look good from 16 px to 512 px.
    #
    #   padding:  14% of S on each side horizontally, 18% at bottom
    #   bar_w:    each bar is 18% of S wide
    #   gap:      4% of S between bars
    #   heights:  left=30%, centre=50%, right=70% of S
    #   top_r:    2% rounded tops on each bar

    pad_x   = round(S * 0.14)
    pad_bot = round(S * 0.18)
    bar_w   = round(S * 0.18)
    gap     = round(S * 0.04)
    top_r   = max(1, round(S * 0.025))

    total_w = bar_w * 3 + gap * 2
    left    = (S - total_w) // 2
    base_y  = S - pad_bot

    bars = [
        (BAR_DIM,  round(S * 0.30)),
        (BAR_MID,  round(S * 0.50)),
        (BAR_TALL, round(S * 0.70)),
    ]

    for i, (colour, h) in enumerate(bars):
        x0 = left + i * (bar_w + gap)
        x1 = x0 + bar_w - 1
        y0 = base_y - h
        y1 = base_y
        draw.rounded_rectangle([x0, y0, x1, y1], radius=top_r, fill=(*colour, 255))

    return img


def _save_png(img: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="PNG")
    print(f"  PNG  {path}  ({img.size[0]}×{img.size[1]})")


def _save_ico(sizes: list[int], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    images = [render(s) for s in sizes]
    images[0].save(
        path, format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=images[1:],
    )
    print(f"  ICO  {path}  (sizes {sizes})")


def main() -> None:
    print("STOOP icon generator — Night & Brick + palette")

    # ── App icon (installer + desktop shortcut) ────────────────────────────
    ico_sizes = [16, 24, 32, 48, 64, 128, 256]
    _save_ico(ico_sizes, HERE / "icon.ico")
    _save_png(render(512), HERE / "icon-512.png")

    # ── Overlay / Tauri icons ──────────────────────────────────────────────
    if OVERLAY_ICONS.is_dir():
        _save_ico(ico_sizes, OVERLAY_ICONS / "icon.ico")
        _save_png(render(512), OVERLAY_ICONS / "icon.png")
        _save_png(render(128), OVERLAY_ICONS / "128x128.png")
        _save_png(render(256), OVERLAY_ICONS / "128x128@2x.png")
        _save_png(render(32),  OVERLAY_ICONS / "32x32.png")
    else:
        print(f"  (overlay icons dir not found — skipping: {OVERLAY_ICONS})")

    print("Done.")


if __name__ == "__main__":
    main()
