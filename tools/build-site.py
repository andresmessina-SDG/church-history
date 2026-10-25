#!/usr/bin/env python3
"""Build the deployable site: python3 tools/build-site.py <pilot-dir> <out-dir>

<pilot-dir> holds the artifact's files. Its index.html is a page fragment that
begins with a wrapper line (ending in <body>) followed by <title>...; this
swaps the wrapper for a full head and copies every other file beside it.
"""
import re, shutil, sys
from pathlib import Path

BASE = "https://andresmessina-sdg.github.io/church-history/"
OG_ALT = "A river of blue water winding across aged paper, the Christian church from Pentecost to today."

src, out = Path(sys.argv[1]), Path(sys.argv[2])
lines = (src / "index.html").read_text(encoding="utf-8").split("\n")
assert lines[0].startswith("<!doctype html>"), "wrapper line not found"
frag = "\n".join(lines[1:])

title = re.search(r"<title>(.*?)</title>", frag).group(1)
desc = re.search(r'<meta name="description" content="(.*?)">', frag).group(1)
split = frag.index("</style>") + len("</style>")
head, body = frag[:split], frag[split:]
head = head.replace("<script>document.documentElement.lang='en'</script>\n", "")
body = body.replace("</body></html>", "").rstrip() + "\n"

extra = f'''<link rel="canonical" href="{BASE}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{title}">
<meta property="og:url" content="{BASE}">
<meta property="og:image" content="{BASE}og.jpg">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="{OG_ALT}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title}">
<meta name="twitter:description" content="{desc}">
<meta name="twitter:image" content="{BASE}og.jpg">
<meta name="twitter:image:alt" content="{OG_ALT}">
<link rel="apple-touch-icon" href="{BASE}apple-touch-icon.png">
<script type="application/ld+json">{{"@context":"https://schema.org","@type":"WebSite","name":"{title}","url":"{BASE}","description":"{desc}","inLanguage":"en"}}</script>
'''
head = head.replace("<link rel=\"preconnect\" href=\"https://fonts.googleapis.com\">", extra + "<link rel=\"preconnect\" href=\"https://fonts.googleapis.com\">", 1)
noscript = '<noscript><p><a href="credits.html">Sources, credits and method</a></p></noscript>\n'

page = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n'
        + head + "\n</head>\n<body>\n" + noscript + body + "</body>\n</html>\n")
out.mkdir(parents=True, exist_ok=True)
(out / "index.html").write_text(page, encoding="utf-8")

for f in src.rglob("*"):
    if f.is_file() and f.relative_to(src) != Path("index.html"):
        dest = out / f.relative_to(src)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dest)
