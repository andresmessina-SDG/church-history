#!/usr/bin/env node
/* Build the readable pages: node tools/build-pages.js
   The river (index.html) draws everything in the browser, so a search engine, a link preview or a reader without JavaScript finds no text there.
   This writes a plain page for every era (/<era>/) and every chapter (/<era>/<n>/) from the same data the river reads, each with its own title,
   description, canonical address and preview card, and links back into the river at the same place (#<era>-<n>). It also rewrites sitemap.xml.
   The eras, their slugs and the typesetting rules are read from index.html itself, so the pages cannot drift from the river. Run it after the data
   or index.html change, and commit what it writes. */
'use strict';
const fs = require('fs'), path = require('path'), vm = require('vm');
const ROOT = path.resolve(__dirname, '..');
const BASE = 'https://andresmessina-sdg.github.io/church-history/';
const read = f => fs.readFileSync(path.join(ROOT, f), 'utf8');
const html = read('index.html');

// ---- what the river knows ----
const grab = (start, end) => { const a = html.indexOf(start); if (a < 0) throw new Error('not found: ' + start); const b = html.indexOf(end, a); return html.slice(a, b); };
const ctx = { window: {} }; vm.createContext(ctx);
vm.runInContext(grab('const ERAS = [', '\nconst TW') + '\nthis.ERAS=ERAS;', ctx);
vm.runInContext(grab('const ROMAN=', '\n') + '\nthis.ROMAN=ROMAN;', ctx);
vm.runInContext(grab('const typo=', '\n') + '\nthis.typo=typo;', ctx);
vm.runInContext(grab('const SLUG=', '\n') + '\nthis.SLUG=SLUG;', ctx);
// the late Middle Ages are one body of chapters shared by two eras; the river says which chapters, openings, readings and people belong to each
vm.runInContext('const LM_PART=(...a)=>a;\n' + grab('const LM_V=', '\n') + '\n' + grab('const LM_VI=', '\n') + '\nthis.LM_V=LM_V; this.LM_VI=LM_VI;', ctx);
const { ERAS, ROMAN, typo, SLUG, LM_V, LM_VI } = ctx;
for (const f of ['apostolic', 'antenicene', 'chapters', 'earlymedieval', 'latemedieval', 'reformation', 'orthodoxy', 'nineteenth', 'global'])
  vm.runInContext(read(f + '.js'), ctx);
const W = ctx.window;
const lm = ([chs, ops, rds, names]) => ({
  chapters: W.LATEMED_CHAPTERS.filter(c => chs.includes(c.n)).map((c, j) => Object.assign({}, c, { n: j + 1 })),
  extra: { opening: W.LATEMED_EXTRA.opening.filter(q => ops.includes(q.id)), readings: W.LATEMED_EXTRA.readings.filter(q => rds.includes(q.id)), people: W.LATEMED_EXTRA.people.filter(p => names.includes(p.name)) } });
const DATA = [
  { chapters: W.APOSTOLIC_CHAPTERS, extra: W.APOSTOLIC_EXTRA }, { chapters: W.ANTENICENE_CHAPTERS, extra: W.ANTENICENE_EXTRA },
  { chapters: W.NICENE_CHAPTERS, extra: W.NICENE_EXTRA }, { chapters: W.EARLYMED_CHAPTERS, extra: W.EARLYMED_EXTRA },
  lm(LM_V), lm(LM_VI),
  { chapters: W.REFORM_CHAPTERS, extra: W.REFORM_EXTRA }, { chapters: W.ORTHO_CHAPTERS, extra: W.ORTHO_EXTRA },
  { chapters: W.NINE_CHAPTERS, extra: W.NINE_EXTRA }, { chapters: W.GLOBAL_CHAPTERS, extra: W.GLOBAL_EXTRA }];
if (ERAS.length !== DATA.length || SLUG.length !== DATA.length) throw new Error('eras, slugs and data do not line up');

// ---- typesetting ----
const SITE = 'A History of the Christian Church';
const attr = s => String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
const plain = s => String(s).replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim();
const clip = (s, n) => { s = plain(s); if (s.length <= n) return s; const c = s.slice(0, n); return c.slice(0, c.lastIndexOf(' ')) + '…'; };
const years = e => `AD ${e.a}–${e.b === 2026 ? 'today' : e.b}`;
const river = (i, key) => '../'.repeat(key ? 2 : 1) + '#' + SLUG[i] + (key ? '-' + key : '');
const cite = q => {
  const parts = [`${q.author}, <i>${q.work}</i>${q.ref ? ' ' + q.ref : ''}.`];
  if (q.tr) parts.push(`Tr. ${q.tr}${q.year ? ', ' + q.year : ''}.`); else if (q.year && !/Schaff/.test(q.author)) parts.push(`${q.year}.`);
  if (q.url) parts.push(`<a href="${attr(q.url)}" rel="noopener">Read the whole</a>`);
  return `<p class="src">${parts.join(' ')}</p>`; };
const scripCite = b => (b.work === 'King James Version' ? b.ref : b.work + ' ' + b.ref) + (b.work === 'King James Version' || /King James/.test(b.tr || '') ? ' · KJV' : '');
function block(b) {
  const t = typo(b.text || '');
  switch (b.k) {
    case 'scrip': return `<blockquote class="scrip"><p>“${t}”</p><footer>${scripCite(b)}</footer></blockquote>`;
    case 'head': return `<h3>${b.text}</h3>`;
    case 'ed': return `<p class="ed">${b.text}</p><p class="src">The editor.</p>`;
    case 'chart': return '';
    case 'schaff': return `<p>${t}</p>${cite(b)}`;
    case 'reformed': return `<figure class="w ref"><figcaption>A Reformed reading · ${b.author}</figcaption><blockquote><p>${t}</p></blockquote>${cite(b)}</figure>`;
    default: return `<figure class="w"><figcaption>${b.author}</figcaption><blockquote><p>${t}</p></blockquote>${cite(b)}</figure>`;
  } }

const CSS = `:root{--paper:#ECE8DC;--ink:#2B2620;--muted:#6B6355;--water:#2F4E9E;--accent:#A8321F;--gloss:#386E54;--rule:rgba(43,38,32,.18)}
*{box-sizing:border-box}html{background:var(--paper)}body{margin:0;background:var(--paper);color:var(--ink);font:17px/1.65 Spectral,Georgia,serif}
a{color:var(--water)}main{max-width:44rem;margin:0 auto;padding:28px 16px 64px}
nav.crumbs{font:15px/1.4 'IM Fell English SC','IM Fell English',Georgia,serif;letter-spacing:.03em;color:var(--muted);margin-bottom:22px}nav.crumbs a{color:var(--accent);text-decoration:none}
.kick{font:16px 'IM Fell English SC','IM Fell English',Georgia,serif;letter-spacing:.04em;color:var(--accent);margin:0}
h1,h2,h3{font-family:'IM Fell English',Georgia,serif;font-weight:400;line-height:1.15;text-wrap:balance}h1{font-size:clamp(2rem,6vw,2.8rem);margin:.15em 0 .5em}h2{font-size:1.6rem;margin:2em 0 .5em}h3{font-size:1.3rem;margin:1.8em 0 .4em}
blockquote{margin:0}.scrip{border-top:1px solid #B08226;border-bottom:1px solid #B08226;padding:12px 0;margin:1.4em 0;font:1.3rem/1.35 'IM Fell English',Georgia,serif}.scrip p{margin:0}.scrip footer{font:15px 'IM Fell English SC',Georgia,serif;color:var(--accent);margin-top:.4em}
.w{margin:1.4em 0}.w figcaption{font:15px 'IM Fell English SC',Georgia,serif;letter-spacing:.03em;color:var(--accent)}.w blockquote p{margin:.2em 0}.ref{border-left:2px solid var(--gloss);padding-left:14px}
.src{font-size:.82rem;line-height:1.45;color:var(--gloss);font-style:italic;margin:-.4em 0 1.2em}.ed{font-style:italic;color:var(--muted)}
.go{display:inline-block;margin:6px 0 0;font:16px 'IM Fell English',Georgia,serif;font-style:italic;color:var(--accent)}
ol.chs{padding-left:1.4em}ol.chs li{margin:.3em 0}ol.chs .y,.dt{color:var(--muted);font-size:.9rem}ul.plain{padding-left:1.1em}
nav.pager{display:flex;justify-content:space-between;gap:16px;border-top:1px solid var(--rule);margin-top:3em;padding-top:14px;font:16px 'IM Fell English',Georgia,serif}
footer.site{border-top:1px solid var(--rule);margin-top:3em;padding-top:12px;font-size:.85rem;color:var(--muted)}`;
const FONTS = 'https://fonts.googleapis.com/css2?family=IM+Fell+English:ital@0;1&family=IM+Fell+English+SC&family=Spectral:ital,wght@0,400;1,400&display=swap';

function page({ rel, title, desc, body, crumbs, ld }) {
  const url = BASE + rel;
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${attr(title)}</title>
<meta name="description" content="${attr(desc)}">
<link rel="canonical" href="${url}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="${SITE}">
<meta property="og:title" content="${attr(title)}">
<meta property="og:description" content="${attr(desc)}">
<meta property="og:url" content="${url}">
<meta property="og:image" content="${BASE}og.jpg">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#ECE8DC">
<link rel="icon" href="${'../'.repeat(rel.split('/').length - 1)}apple-touch-icon.png">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="${FONTS}">
<style>${CSS}</style>
<script type="application/ld+json">${JSON.stringify(ld).replace(/</g, '\\u003c')}</script>
</head>
<body>
<main>
<nav class="crumbs" aria-label="Breadcrumb">${crumbs}</nav>
${body}
<footer class="site"><p>From <a href="${'../'.repeat(rel.split('/').length - 1)}">${SITE}</a>, drawn as one river from Pentecost to today and told in the words of its own witnesses. <a href="${'../'.repeat(rel.split('/').length - 1)}credits.html">Sources, credits and method</a>.</p></footer>
</main>
</body>
</html>
`; }
const crumbList = items => ({ '@type': 'BreadcrumbList', itemListElement: items.map(([name, rel], i) => ({ '@type': 'ListItem', position: i + 1, name, item: BASE + rel })) });

// ---- write ----
const written = [];
const out = (rel, text) => { const f = path.join(ROOT, rel, 'index.html'); fs.mkdirSync(path.dirname(f), { recursive: true }); fs.writeFileSync(f, text); written.push(rel); };
ERAS.forEach((e, i) => {
  const { chapters, extra } = DATA[i], slug = SLUG[i], erel = slug + '/';
  const etitle = `${e.name}, ${years(e)} · ${SITE}`;
  const body = `<p class="kick">Era ${e.n} · ${years(e)}</p>
<h1>${e.name}</h1>
<blockquote class="scrip"><p>“${e.q}”</p><footer>${e.c}</footer></blockquote>
<p>${e.sum}</p>
<p><i>${e.two}</i></p>
<a class="go" href="${river(i)}">See this era on the river</a>
${(extra.opening || []).length ? `<h2>Opening</h2>\n${extra.opening.map(q => `<p>${typo(q.text)}</p>${cite(q)}`).join('\n')}` : ''}
<h2>The chapters of this era</h2>
<ol class="chs">${chapters.map(c => `<li><a href="${c.n}/">${c.title}</a> <span class="y">${c.yrs}</span></li>`).join('')}</ol>
${(extra.readings || []).length ? `<h2>Readings</h2>\n${extra.readings.map(q => `<figure class="w ref"><figcaption>${q.author}</figcaption><blockquote><p>${typo(q.text)}</p></blockquote>${cite(q)}</figure>`).join('\n')}` : ''}
${(extra.people || []).length ? `<h2>People</h2>\n<ul class="plain">${extra.people.map(p => `<li><b>${p.name}</b> <span class="dt">${p.dates || ''}</span>${p.role ? ` — ${p.role}` : ''}</li>`).join('')}</ul>` : ''}
<h2>On the river</h2>
<ul class="plain">${e.ev.map(v => `<li>${v[0]} · ${v[1]}</li>`).join('')}</ul>
<nav class="pager">${i ? `<a href="../${SLUG[i - 1]}/">← ${ERAS[i - 1].name}</a>` : '<span></span>'}${i < ERAS.length - 1 ? `<a href="../${SLUG[i + 1]}/">${ERAS[i + 1].name} →</a>` : '<span></span>'}</nav>`;
  out(erel, page({ rel: erel, title: etitle, desc: clip(e.sum, 158), body,
    crumbs: `<a href="../">${SITE}</a> · Era ${e.n}`,
    ld: { '@context': 'https://schema.org', '@graph': [
      { '@type': 'CollectionPage', name: e.name, description: plain(e.sum), url: BASE + erel, isPartOf: { '@type': 'WebSite', name: SITE, url: BASE }, inLanguage: 'en' },
      crumbList([[SITE, ''], [e.name, erel]])] } }));

  chapters.forEach((c, j) => {
    const crel = `${slug}/${c.n}/`;
    const lead = c.blocks.find(b => b.k === 'schaff' || b.k === 'w') || c.blocks[0];
    const prev = chapters[j - 1], next = chapters[j + 1];
    const body = `<p class="kick">${e.name} · Chapter ${ROMAN(c.n).toUpperCase()} · ${c.yrs}</p>
<h1>${c.title}</h1>
<a class="go" href="${river(i, c.n)}">Read it on the river</a>
${c.blocks.map(block).join('\n')}
${c.read && c.read.length ? `<h2>Read on</h2>\n<ul class="plain">${c.read.map(x => `<li>${x.url ? `<a href="${attr(x.url)}" rel="noopener">${x.label}</a>` : x.label}</li>`).join('')}</ul>` : ''}
<nav class="pager">${prev ? `<a href="../${prev.n}/">← ${prev.title}</a>` : `<a href="../">← ${e.name}</a>`}${next ? `<a href="../${next.n}/">${next.title} →</a>` : (i < ERAS.length - 1 ? `<a href="../../${SLUG[i + 1]}/">${ERAS[i + 1].name} →</a>` : '<span></span>')}</nav>`;
    out(crel, page({ rel: crel, title: `${c.title} (${c.yrs}) · ${e.name} · ${SITE}`, desc: clip(typo(lead.text || ''), 158), body,
      crumbs: `<a href="../../">${SITE}</a> · <a href="../">${e.name}</a> · Chapter ${ROMAN(c.n).toUpperCase()}`,
      ld: { '@context': 'https://schema.org', '@graph': [
        { '@type': 'Article', headline: c.title, about: `${e.name}, ${c.yrs}`, description: clip(typo(lead.text || ''), 158), url: BASE + crel, inLanguage: 'en', image: BASE + 'og.jpg',
          isPartOf: { '@type': 'CollectionPage', name: e.name, url: BASE + erel } },
        crumbList([[SITE, ''], [e.name, erel], [c.title, crel]])] } }));
  });
});

// ---- the sitemap ----
const today = new Date().toISOString().slice(0, 10);
const urls = ['', 'credits.html', ...written];
fs.writeFileSync(path.join(ROOT, 'sitemap.xml'), `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${urls.map(u => `  <url><loc>${BASE}${u}</loc><lastmod>${today}</lastmod></url>`).join('\n')}
</urlset>
`);
console.log(`wrote ${written.length} pages (${ERAS.length} eras, ${written.length - ERAS.length} chapters) and sitemap.xml with ${urls.length} addresses`);
// The pages above name Google Fonts, as the river does; serve those fonts from the site instead.
require('child_process').execFileSync('python3', [path.join(__dirname, 'localize-fonts.py'), ROOT], { stdio: 'inherit' });
