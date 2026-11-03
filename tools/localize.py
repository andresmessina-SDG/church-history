#!/usr/bin/env python3
"""Serve the site's fonts and images from the site itself: python3 tools/localize.py [site-dir]

Pages written as artifacts can only load fonts from Google Fonts and images
from other sites, so the pages this repository receives make every reader's
browser contact those sites. This script brings them home:

- Fonts. Each Google Fonts stylesheet link is replaced by fonts/fonts.css,
  and the font files it names are downloaded into fonts/, with each family's
  licence in fonts/licences/. The preconnect hints to Google go too.
- Images. Each <img> or <source> that loads a picture from another site is
  pointed at a copy in images/, and images/SOURCES.md records where each copy
  came from.

It also removes the artifact viewer's own meta tags, which mean nothing on the
published site. Links to other sites are left alone: they load nothing until
a reader follows them.

Run it after every update that brings in new HTML. It is safe to run again:
files already downloaded are kept, and a page with nothing to change is not
touched.
"""
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.error
import urllib.request
import time
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
FONTS = ROOT / "fonts"
CSS_OUT = FONTS / "fonts.css"
IMAGES = ROOT / "images"
SOURCES = IMAGES / "SOURCES.md"
SKIP_DIRS = {".git", "tools", "node_modules", "fonts", "images"}
# A current desktop Chrome, so Google answers with woff2 files and unicode ranges.
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
# Wikimedia asks automated clients to name themselves.
IMG_UA = "site-localize/1.0 (static site build; https://github.com/andresmessina-SDG)"
IMG_TAG = re.compile(r"<(?:img|source)\b[^>]*>", re.I)
IMG_ATTR = re.compile(r'\b(src|srcset|poster)="([^"]*https?://[^"]*)"', re.I)
TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif", "image/svg+xml": ".svg", "image/avif": ".avif"}

LINK = re.compile(r'<link\b[^>]*\bhref="(https://fonts\.googleapis\.com/css2?\?[^"]+)"[^>]*>\s*', re.I)
VIEWER_META = re.compile(r'<meta\b[^>]*\bname="claude:[^"]*"[^>]*>\s*', re.I)
PRECONNECT = re.compile(r'<link\b[^>]*\brel="(?:preconnect|dns-prefetch)"[^>]*\bhref="https://fonts\.(?:googleapis|gstatic)\.com/?"[^>]*>\s*', re.I)
FACE = re.compile(r"(?:/\*\s*([\w-]+)\s*\*/\s*)?@font-face\s*\{(.*?)\}", re.S)


def get(url: str, ua: str = UA, want_type: bool = False):
    """Fetch a URL, waiting and retrying when the server asks us to slow down."""
    for attempt in range(8):
        req = urllib.request.Request(url, headers={"User-Agent": ua})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
                return (data, r.headers.get_content_type()) if want_type else data
        except urllib.error.HTTPError as e:
            if e.code not in (429, 503) or attempt == 7:
                raise
            wait = e.headers.get("Retry-After", "")
            time.sleep(max(float(wait) if wait.replace(".", "", 1).isdigit() else 0, 2 ** attempt))


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def pages():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if name.endswith(".html"):
                yield Path(dirpath) / name


def fonts() -> int:
    found = {}
    for page in pages():
        text = page.read_text(encoding="utf-8")
        urls = [html.unescape(u) for u in LINK.findall(text)]
        if urls or PRECONNECT.search(text) or VIEWER_META.search(text):
            found[page] = (text, urls)
    if not found:
        print("No page asks Google for fonts. Nothing to do.")
        return 0
    if not any(urls for _, urls in found.values()):
        for page, (text, _) in found.items():
            page.write_text(VIEWER_META.sub("", PRECONNECT.sub("", text)), encoding="utf-8")
        print(f"Tidied {len(found)} pages; no page asks Google for fonts.")
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
    header = ("/* Written by tools/localize.py. The site serves its own fonts, so a reader's\n"
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

        new = VIEWER_META.sub("", PRECONNECT.sub("", text))
        new = LINK.sub(swap, new)
        if new != text:
            page.write_text(new, encoding="utf-8")
            changed += 1
    print(f"{len(faces)} font files ({fetched} new) for {len(families)} families; {changed} pages now load fonts/fonts.css.")
    return 0


def fetch_url(url: str) -> str:
    """Where to download an image from. Commons' Special:FilePath redirects through
    several hosts; its thumb.php serves the same scaled image directly."""
    parts = urllib.parse.urlsplit(url)
    m = re.match(r"/wiki/Special:FilePath/(.+)", parts.path)
    width = urllib.parse.parse_qs(parts.query).get("width", [""])[0]
    if parts.netloc == "commons.wikimedia.org" and m and width.isdigit():
        name = urllib.parse.unquote(m.group(1))
        # A file renamed on Commons redirects from its old name; ask for the current one.
        api = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(
            {"action": "query", "titles": "File:" + name, "redirects": 1, "format": "json", "formatversion": 2})
        info = json.loads(get(api, IMG_UA))
        for r in info.get("query", {}).get("redirects", []):
            name = r["to"].split(":", 1)[1]
        return "https://commons.wikimedia.org/w/thumb.php?" + urllib.parse.urlencode({"f": name, "w": width})
    return url


def image_name(url: str, ctype: str) -> str:
    parts = urllib.parse.urlsplit(url)
    stem = Path(urllib.parse.unquote(parts.path)).stem or "image"
    width = urllib.parse.parse_qs(parts.query).get("width", [""])[0]
    name = slug(stem)[:90] + (f"-{width}" if width.isdigit() else "")
    return name + TYPES.get(ctype, Path(parts.path).suffix.lower() or ".img")


def images() -> int:
    known = {}  # remote URL -> local file name, from earlier runs
    if SOURCES.exists():
        for m in re.finditer(r"^\| `([^`]+)` \| <([^>]+)> \|$", SOURCES.read_text(encoding="utf-8"), re.M):
            if (IMAGES / m.group(1)).exists():
                known[m.group(2)] = m.group(1)
    changed = fetched = 0
    for page in pages():
        text = page.read_text(encoding="utf-8")
        rel = os.path.relpath(IMAGES, page.parent).replace(os.sep, "/")

        def local(url: str) -> str:
            nonlocal fetched
            url = html.unescape(url)
            if url not in known:
                if fetched:
                    time.sleep(1.5)  # be gentle with image hosts such as Wikimedia
                data, ctype = get(fetch_url(url), IMG_UA, want_type=True)
                if not ctype.startswith("image/"):
                    raise SystemExit(f"{url} answered with {ctype}, not an image")
                name = image_name(url, ctype)
                base, ext = os.path.splitext(name)
                n = 2
                while name in known.values():
                    name, n = f"{base}-{n}{ext}", n + 1
                IMAGES.mkdir(exist_ok=True)
                (IMAGES / name).write_bytes(data)
                known[url] = name
                fetched += 1
            return f"{rel}/{known[url]}"

        def fix_attr(m):
            attr, value = m.group(1), m.group(2)
            if attr.lower() == "srcset":
                items = []
                for item in value.split(","):
                    bits = item.strip().split(None, 1)
                    if bits and re.match(r"https?://", bits[0]):
                        bits[0] = local(bits[0])
                    items.append(" ".join(bits))
                return f'{attr}="{", ".join(items)}"'
            return f'{attr}="{local(value)}"' if re.match(r"https?://", value) else m.group(0)

        new = IMG_TAG.sub(lambda t: IMG_ATTR.sub(fix_attr, t.group(0)), text)
        if new != text:
            page.write_text(new, encoding="utf-8")
            changed += 1
    if known:
        rows = "\n".join(f"| `{name}` | <{url}> |" for url, name in sorted(known.items(), key=lambda kv: kv[1]))
        SOURCES.write_text("# Where these images came from\n\n"
                           "Written by tools/localize.py. Each file is a copy of the image the page\n"
                           "used to load from the address beside it; the licence and credit are on\n"
                           "that address's page.\n\n| File | Source |\n|---|---|\n" + rows + "\n", encoding="utf-8")
        print(f"{len(known)} images ({fetched} new); {changed} pages now load them from images/.")
    else:
        print("No page loads an image from another site.")
    return 0


def main() -> int:
    status = fonts() or images()
    leftover = []
    for p in pages():
        text = p.read_text(encoding="utf-8")
        if re.search(r"fonts\.(googleapis|gstatic)\.com", text) or any(IMG_ATTR.search(t) for t in IMG_TAG.findall(text)):
            leftover.append(str(p.relative_to(ROOT)))
    if leftover:
        print("still loads something from another site, check by hand: " + ", ".join(leftover[:10]), file=sys.stderr)
        return 1
    return status


if __name__ == "__main__":
    sys.exit(main())
