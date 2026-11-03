#!/usr/bin/env python3
"""Serve the site's web fonts from the site itself: python3 tools/localize-fonts.py [site-dir]

Pages written in a claude.ai artifact can only load fonts from Google Fonts, so
the pages this repository receives ask Google for them, and every reader's
browser then contacts Google. This script finds each Google Fonts stylesheet
link in the site's HTML, downloads the CSS and the font files it names into
fonts/, writes fonts/fonts.css pointing at those files, and rewrites each page
to load that instead. It also removes the preconnect hints to Google.

Run it after every update that brings in new HTML. It is safe to run again:
pages that already use fonts/fonts.css are left alone, and font files already
downloaded are kept. A page with nothing to change is not touched.

The fonts are under the SIL Open Font License; their licences are saved in
fonts/licences/.
"""
import html
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
FONTS = ROOT / "fonts"
CSS_OUT = FONTS / "fonts.css"
SKIP_DIRS = {".git", "tools", "node_modules", "fonts"}
# A current desktop Chrome, so Google answers with woff2 files and unicode ranges.
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

LINK = re.compile(r'<link\b[^>]*\bhref="(https://fonts\.googleapis\.com/css2?\?[^"]+)"[^>]*>\s*', re.I)
PRECONNECT = re.compile(r'<link\b[^>]*\brel="(?:preconnect|dns-prefetch)"[^>]*\bhref="https://fonts\.(?:googleapis|gstatic)\.com/?"[^>]*>\s*', re.I)
FACE = re.compile(r"(?:/\*\s*([\w-]+)\s*\*/\s*)?@font-face\s*\{(.*?)\}", re.S)


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def pages():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if name.endswith(".html"):
                yield Path(dirpath) / name


def main() -> int:
    found = {}
    for page in pages():
        text = page.read_text(encoding="utf-8")
        urls = [html.unescape(u) for u in LINK.findall(text)]
        if urls or PRECONNECT.search(text):
            found[page] = (text, urls)
    if not found:
        print("No page asks Google for fonts. Nothing to do.")
        return 0

    # Gather every face the pages ask for, keyed by the file Google serves.
    faces, families = {}, set()
    prior = CSS_OUT.read_text(encoding="utf-8") if CSS_OUT.exists() else ""
    for url in sorted({u for _, urls in found.values() for u in urls}):
        css = get(url).decode("utf-8")
        for subset, body in FACE.findall(css):
            src = re.search(r"url\((https://fonts\.gstatic\.com/[^)]+)\)", body).group(1)
            family = re.search(r"font-family:\s*'([^']+)'", body).group(1)
            style = re.search(r"font-style:\s*(\w+)", body).group(1)
            weight = re.search(r"font-weight:\s*([^;]+);", body).group(1).strip()
            stretch = re.search(r"font-stretch:\s*([^;]+);", body)
            rng = re.search(r"unicode-range:\s*([^;]+);", body)
            families.add(family)
            name = "-".join(filter(None, [slug(family), style, slug(weight), slug(stretch.group(1)) if stretch else "", subset or "all"])) + ".woff2"
            faces[src] = dict(family=family, style=style, weight=weight, stretch=stretch.group(1).strip() if stretch else None,
                              range=rng.group(1).strip() if rng else None, file=name, subset=subset)

    FONTS.mkdir(exist_ok=True)
    fetched = 0
    for src, f in faces.items():
        dest = FONTS / f["file"]
        if not dest.exists():
            dest.write_bytes(get(src))
            fetched += 1

    # Faces from earlier runs stay, so pages built before this run keep their fonts.
    blocks = {}
    for f in faces.values():
        lines = [f'  font-family: "{f["family"]}";', f'  font-style: {f["style"]};', f'  font-weight: {f["weight"]};']
        if f["stretch"]:
            lines.append(f'  font-stretch: {f["stretch"]};')
        lines += ["  font-display: swap;", f'  src: url("{f["file"]}") format("woff2");']
        if f["range"]:
            lines.append(f'  unicode-range: {f["range"]};')
        blocks[f["file"]] = (f"/* {f['family']}, {f['subset'] or 'all'} */\n@font-face {{\n" + "\n".join(lines) + "\n}\n")
    for m in re.finditer(r"/\* [^*]+ \*/\n@font-face \{.*?src: url\(\"([^\"]+)\"\).*?\n\}\n", prior, re.S):
        if m.group(1) not in blocks and (FONTS / m.group(1)).exists():
            blocks[m.group(1)] = m.group(0)
    header = ("/* Written by tools/localize-fonts.py. The site serves its own fonts, so a reader's\n"
              "   browser asks no other site for them. SIL Open Font License: see licences/. */\n\n")
    CSS_OUT.write_text(header + "\n".join(blocks[k] for k in sorted(blocks)), encoding="utf-8")

    # Each family's licence, from the Google Fonts repository.
    lic_dir = FONTS / "licences"
    lic_dir.mkdir(exist_ok=True)
    for family in sorted(families):
        dest = lic_dir / f"{slug(family)}.txt"
        if dest.exists():
            continue
        key = re.sub(r"[^a-z0-9]", "", family.lower())
        for folder, file in (("ofl", "OFL.txt"), ("apache", "LICENSE.txt"), ("ufl", "UFL.txt")):
            try:
                dest.write_bytes(get(f"https://raw.githubusercontent.com/google/fonts/main/{folder}/{key}/{file}"))
                break
            except Exception:
                continue
        else:
            print(f"warning: no licence found for {family}; add it to {lic_dir.relative_to(ROOT)} by hand", file=sys.stderr)

    changed = 0
    for page, (text, urls) in found.items():
        href = os.path.relpath(CSS_OUT, page.parent).replace(os.sep, "/")
        if page.name == "404.html":
            # GitHub Pages serves the 404 page at whatever address was missed, at any depth,
            # so it needs a path from the root of the host, taken from its own canonical address.
            canon = re.search(r'<link\b[^>]*rel="canonical"[^>]*href="([^"]+)"', text) or re.search(r'property="og:url"[^>]*content="([^"]+)"', text)
            if canon:
                base = urllib.parse.urlparse(canon.group(1)).path.rsplit("/", 1)[0] + "/"
                rel_dir = page.parent.relative_to(ROOT).as_posix()
                base = base[: len(base) - len(rel_dir) - 1] if rel_dir != "." and base.endswith(rel_dir + "/") else base
                href = base + CSS_OUT.relative_to(ROOT).as_posix()
            else:
                print(f"warning: {page.relative_to(ROOT)} has no canonical address; its font link is relative", file=sys.stderr)
        tag = f'<link rel="stylesheet" href="{href}">\n'
        first = [True]

        def swap(m):
            if first[0]:
                first[0] = False
                return tag
            return ""

        new = PRECONNECT.sub("", text)
        new = LINK.sub(swap, new)
        if new != text:
            page.write_text(new, encoding="utf-8")
            changed += 1
    leftover = [str(p.relative_to(ROOT)) for p in pages() if re.search(r"fonts\.(googleapis|gstatic)\.com", p.read_text(encoding="utf-8"))]
    print(f"{len(faces)} font files ({fetched} new) for {len(families)} families; {changed} pages now load fonts/fonts.css.")
    if leftover:
        print("still mentions Google Fonts, check by hand: " + ", ".join(leftover[:10]), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
