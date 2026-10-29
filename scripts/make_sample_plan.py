"""Generate a synthetic floor-plan image used to demo the plan-import feature.

Draws an architect-style plan (dark walls on white) with three rooms, door
gaps, and window ticks. Output: frontend/public/sample-plan.png (served by
the app after a frontend build and used in tests/E2E).

Run:  .venv/Scripts/python scripts/make_sample_plan.py   (from backend/ or repo root)
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

W, H = 1200, 800
WALL = (30, 30, 30)
BG = (250, 250, 250)
THICK = 10


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    out = root / "frontend" / "public" / "sample-plan.png"
    out.parent.mkdir(parents=True, exist_ok=True)

    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # Outer envelope with two door openings (bottom and right). The outline
    # extends inward from the bounds, so the gaps must erase the border band
    # itself, not the margin outside it.
    d.rectangle([20, 20, W - 20, H - 20], outline=WALL, width=THICK)
    d.rectangle([W // 2 - 60, H - 20 - THICK, W // 2 + 60, H - 20 + 2], fill=BG)
    d.rectangle([W - 20 - THICK, H // 2 - 50, W - 20 + 2, H // 2 + 50], fill=BG)

    # Vertical interior wall with a doorway gap.
    x = W // 3
    d.rectangle([x, 20, x + THICK, H // 2 - 70], fill=WALL)
    d.rectangle([x, H // 2 - 10, x + THICK, H - 20], fill=WALL)

    # Horizontal interior wall with a doorway gap.
    y = H // 2
    d.rectangle([20, y, x - 120, y + THICK], fill=WALL)
    d.rectangle([x + 40, y, W - 20, y + THICK], fill=WALL)

    # A shaft/closer block (stair-like) in the top-right room.
    d.rectangle([W - 320, 60, W - 160, 220], outline=WALL, width=THICK)
    d.rectangle([W - 320, 60, W - 160, 60 + THICK], fill=WALL)

    # Window ticks on the top wall (thin double lines).
    for wx in range(160, W - 200, 240):
        d.rectangle([wx, 14, wx + 90, 26], outline=WALL, width=3)

    # Small annotation text (noise the import must tolerate; user cleans it).
    try:
        from PIL import ImageFont

        font = ImageFont.load_default(28)
    except Exception:  # pragma: no cover
        font = None
    d.text((60, 60), "ROOM 101", fill=WALL, font=font)
    d.text((W - 480, H - 120), "ROOM 102", fill=WALL, font=font)

    img.save(out, "PNG")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
