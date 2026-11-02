#!/usr/bin/env python3
"""Make the light copies of the plates: python3 tools/build-plates.py

The plates are tipped into the era pages at most about 420px wide (840px on a sharp screen), but the originals run to 1600px and 735 KB.
This writes WebP copies 400 and 800 pixels wide (never wider than the original) into plates/w400/ and plates/w800/, which the river offers
through <picture>, keeping the original JPEG for any browser without WebP. Run it after adding or changing a plate.
"""
from pathlib import Path
from PIL import Image

root = Path(__file__).resolve().parent.parent / "plates"
before = after = 0
for src in sorted(root.glob("*.jpg")):
    im = Image.open(src).convert("RGB")
    before += src.stat().st_size
    for w in (400, 800):
        out = root / f"w{w}" / (src.stem + ".webp")
        out.parent.mkdir(exist_ok=True)
        cw = min(w, im.width)
        im.resize((cw, round(im.height * cw / im.width)), Image.LANCZOS).save(out, "WEBP", quality=72, method=6)
        if w == 800: after += out.stat().st_size
print(f"{len(list(root.glob('*.jpg')))} plates: originals {before/1e6:.1f} MB, 800px WebP {after/1e6:.1f} MB")
