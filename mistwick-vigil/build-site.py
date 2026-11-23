#!/usr/bin/env python3
"""Build all localized Mistwick Vigil pages from site-src JSON files."""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "site-src"
ASSETS = ROOT / "assets"
BASE_URL = "https://zouyongzhen.github.io/mistwick-vigil"
# Keep this order in sync with `app/src/main/assets/locales/catalog.js` in the
# MistwickVigil app. English remains the x-default website page below.
LOCALES = [
    "zh-Hans", "zh-Hant", "en", "es", "pt-BR", "fr", "de",
    "ru", "ja", "ko", "ar", "hi", "id",
]

# Old English URLs published before the localized page set was expanded.
# They stay as noindex redirects to the canonical English pages.
LEGACY_ALIASES = {
    "index-en.html": ("./", "Mistwick Vigil", "Continue to the Mistwick Vigil website"),
    "privacy-policy-en.html": ("privacy-policy.html", "Privacy policy · Mistwick Vigil", "Continue to the Mistwick Vigil privacy policy"),
    "service-policy-en.html": ("service-policy.html", "Terms of service · Mistwick Vigil", "Continue to the Mistwick Vigil terms of service"),
}
HOME_IMAGE_ASSETS = {
    "cover.webp", "watchkeepers.webp", "pathway.webp", "arena.webp", "endless-mist.webp",
}
# Only inline <strong>, <a href="..."> and plain <p> markup is allowed in
# translated strings; every other tag or stray "<" is rejected.
ALLOWED_HTML = re.compile(r'(?:[^<]|</?(?:strong|p)|<a(?: href="[#{{}\w./:@-]+")?>|</a>)*')
TAG_PATTERN = re.compile(r'<(/?)(strong|a|p)(?: href="([^"]*)")?>')
OG_LOCALES = {
    "en": "en_US", "zh-Hans": "zh_CN", "zh-Hant": "zh_TW", "es": "es_ES",
    "pt-BR": "pt_BR", "fr": "fr_FR", "de": "de_DE", "ru": "ru_RU",
    "ja": "ja_JP", "ko": "ko_KR", "ar": "ar_AR", "hi": "hi_IN", "id": "id_ID",
}
EXPECTED_META = {
    "en": ("en", "ltr", "English", ""),
    "zh-Hans": ("zh-CN", "ltr", "简体中文", "-zh"),
    "zh-Hant": ("zh-Hant", "ltr", "繁體中文", "-zh-hant"),
    "es": ("es", "ltr", "Español", "-es"),
    "pt-BR": ("pt-BR", "ltr", "Português (Brasil)", "-pt-br"),
    "fr": ("fr", "ltr", "Français", "-fr"),
    "de": ("de", "ltr", "Deutsch", "-de"),
    "ru": ("ru", "ltr", "Русский", "-ru"),
    "ja": ("ja", "ltr", "日本語", "-ja"),
    "ko": ("ko", "ltr", "한국어", "-ko"),
    "ar": ("ar", "rtl", "العربية", "-ar"),
    "hi": ("hi", "ltr", "हिन्दी", "-hi"),
    "id": ("id", "ltr", "Bahasa Indonesia", "-id"),
}


def esc(value: str) -> str:
    return html.escape(value, quote=True)


def page_path(locale: dict, kind: str) -> str:
    stem = {"home": "index", "privacy": "privacy-policy", "service": "service-policy"}[kind]
    if locale["code"] == "en" and kind == "home":
        return "./"
    return f"{stem}{locale['suffix']}.html"


def page_url(locale: dict, kind: str) -> str:
    path = page_path(locale, kind)
    return f"{BASE_URL}/" if path == "./" else f"{BASE_URL}/{path}"


def shape(value):
    if isinstance(value, dict):
        return {key: shape(item) for key, item in value.items()}
    if isinstance(value, list):
        return [shape(item) for item in value]
    return type(value).__name__


def walk_strings(value, path=""):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from walk_strings(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from walk_strings(item, f"{path}[{index}]")
    elif isinstance(value, str):
        yield path, value


def html_signature(value: str) -> list[tuple[str, str, str]]:
    """Ordered (closing, tag, href) tuples; translations must match English."""
    return [(match.group(1), match.group(2), match.group(3) or "") for match in TAG_PATTERN.finditer(value)]


def validate(locales: dict[str, dict]) -> None:
    missing = set(LOCALES) - set(locales)
    extra = set(locales) - set(LOCALES)
    if missing or extra:
        raise ValueError(f"Locale mismatch; missing={sorted(missing)}, extra={sorted(extra)}")

    reference = locales["en"]
    reference_shape = shape(reference)
    for code in LOCALES:
        locale = locales[code]
        expected = EXPECTED_META[code]
        actual = (locale["htmlLang"], locale["dir"], locale["name"], locale["suffix"])
        if locale["code"] != code or actual != expected:
            raise ValueError(f"Invalid metadata for {code}: {actual}")
        if shape(locale) != reference_shape:
            raise ValueError(f"JSON structure differs from English: {code}")
        if len(locale["privacy"]["sections"]) != 11 or len(locale["service"]["sections"]) != 13:
            raise ValueError(f"Incomplete legal sections: {code}")
        for kind in ("privacy", "service"):
            reference_ids = [section["id"] for section in reference[kind]["sections"]]
            ids = [section["id"] for section in locale[kind]["sections"]]
            if ids != reference_ids:
                raise ValueError(f"Section IDs differ in {code}/{kind}")

    reference_text = "\n".join(value for _, value in walk_strings(reference))
    reference_tokens = {token: reference_text.count(token) for token in ("{{home}}", "{{privacy}}", "{{service}}")}
    reference_html = {path: value for path, value in walk_strings(reference) if path.endswith(".html")}
    for code, locale in locales.items():
        text = "\n".join(value for _, value in walk_strings(locale))
        for token, count in reference_tokens.items():
            if text.count(token) != count:
                raise ValueError(f"Link token mismatch in {code}: {token}")
        for path, value in walk_strings(locale):
            if not path.endswith(".html"):
                continue
            if not ALLOWED_HTML.fullmatch(value):
                raise ValueError(f"Unexpected or malformed HTML at {code}{path}")
            if html_signature(value) != html_signature(reference_html[path]):
                raise ValueError(f"HTML tags/links differ from English at {code}{path}")
        for kind in ("privacy", "service"):
            for index, section in enumerate(locale[kind]["sections"]):
                for position, block in enumerate(section["blocks"]):
                    expected_type = reference[kind]["sections"][index]["blocks"][position]["type"]
                    if block["type"] != expected_type:
                        raise ValueError(f"Block type differs in {code}/{kind} section {index} block {position}")


def validate_assets() -> None:
    missing = sorted(name for name in HOME_IMAGE_ASSETS if not (ASSETS / name).is_file())
    if missing:
        raise ValueError(f"Missing website image assets: {missing}")


def links_for(locales: dict[str, dict], current: dict, kind: str) -> str:
    items = []
    for code in LOCALES:
        locale = locales[code]
        current_attr = ' aria-current="page"' if code == current["code"] else ""
        items.append(
            f'<a href="{page_path(locale, kind)}" lang="{esc(locale["htmlLang"])}" '
            f'hreflang="{esc(locale["htmlLang"])}" dir="{locale["dir"]}"{current_attr}>{esc(locale["name"])}</a>'
        )
    return "\n".join(items)


def head(locales: dict[str, dict], locale: dict, kind: str) -> str:
    content = locale[kind]
    canonical = page_url(locale, kind)
    alternates = "\n".join(
        f'  <link rel="alternate" hreflang="{esc(item["htmlLang"])}" href="{page_url(item, kind)}">'
        for item in locales.values()
    )
    og_alternates = "\n".join(
        f'  <meta property="og:locale:alternate" content="{OG_LOCALES[code]}">'
        for code in LOCALES if code != locale["code"]
    )
    og_title = content.get("ogTitle", content["title"])
    og_description = content.get("ogDescription", content["description"])
    keywords = f'  <meta name="keywords" content="{esc(content["keywords"])}">\n' if kind == "home" else ""
    return f'''<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="theme-color" content="#0a1413">
  <meta name="color-scheme" content="dark">
  <meta name="description" content="{esc(content['description'])}">
{keywords}  <meta name="author" content="Mistwick Vigil">
  <meta name="robots" content="index,follow,max-image-preview:large">
  <link rel="canonical" href="{canonical}">
{alternates}
  <link rel="alternate" hreflang="x-default" href="{page_url(locales['en'], kind)}">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="Mistwick Vigil">
  <meta property="og:locale" content="{OG_LOCALES[locale['code']]}">
{og_alternates}
  <meta property="og:title" content="{esc(og_title)}">
  <meta property="og:description" content="{esc(og_description)}">
  <meta property="og:url" content="{canonical}">
  <meta property="og:image" content="{BASE_URL}/assets/cover.webp">
  <meta property="og:image:width" content="960">
  <meta property="og:image:height" content="1440">
  <meta property="og:image:alt" content="{esc(content.get('ogAlt', locale['home']['hero']['imageAlt']))}">
  <meta name="twitter:card" content="summary_large_image">
  <title>{esc(content['title'])}</title>
  <link rel="icon" type="image/png" href="assets/lantern.png">
  <link rel="stylesheet" href="site.css">
</head>'''


def header(locales: dict[str, dict], locale: dict, kind: str) -> str:
    common = locale["common"]
    home = page_path(locale, "home")
    home_prefix = "./" if kind == "home" else home
    other_label = common["terms"] if kind == "privacy" else common["privacy"]
    other_path = page_path(locale, "service" if kind == "privacy" else "privacy")
    if kind == "home":
        other_label = common["legal"]
        other_path = page_path(locale, "privacy")
    return f'''<a class="skip-link" href="#main-content">{esc(common['skip'])}</a>
<header class="topbar">
  <div class="topbar-inner wrap">
    <a class="brand" href="{home}" aria-label="{esc(common['homeAria'])}">
      <img class="brand-mark" src="assets/lantern.png" alt="" width="36" height="36">
      <span class="brand-copy"><strong>Mistwick Vigil</strong><small>{esc(common['tagline'])}</small></span>
    </a>
    <nav class="nav" aria-label="{esc(common['mainNav'])}">
      <a class="nav-section" href="{home_prefix}#features">{esc(common['features'])}</a>
      <a class="nav-section" href="{home_prefix}#watch">{esc(common['watch'])}</a>
      <a class="nav-section nav-world" href="{home_prefix}#world">{esc(common['world'])}</a>
      <a class="nav-section nav-support" href="{home_prefix}#support">{esc(common['support'])}</a>
      <a class="nav-pill" href="{other_path}">{esc(other_label)}</a>
      <details class="language-menu">
        <summary aria-label="{esc(common['language'])}"><span aria-hidden="true">文A</span><span class="language-current">{esc(locale['name'])}</span></summary>
        <div class="language-list" role="group" aria-label="{esc(common['language'])}">
{links_for(locales, locale, kind)}
        </div>
      </details>
    </nav>
  </div>
</header>'''


def footer(locale: dict, kind: str) -> str:
    common = locale["common"]
    first = common["backHome"] if kind != "home" else common["privacy"]
    first_path = page_path(locale, "home") if kind != "home" else page_path(locale, "privacy")
    brand_name = "雾灯行" if locale["code"].startswith("zh-") else "Mistwick Vigil"
    copyright = common.get("copyright", f"© 2026 {brand_name}")
    return f'''<footer>
  <div class="footer-inner wrap">
    <span>{esc(copyright)}</span>
    <nav class="footer-links" aria-label="{esc(common['footerNav'])}">
      <a href="{first_path}">{esc(first)}</a>
      <a href="{page_path(locale, 'service')}">{esc(common['terms'])}</a>
      <a href="mailto:yongzhen_zou@163.com">{esc(common['supportEmail'])}</a>
    </nav>
  </div>
</footer>'''


def interpolate(value: str, locale: dict) -> str:
    return (value.replace("{{home}}", page_path(locale, "home"))
            .replace("{{privacy}}", page_path(locale, "privacy"))
            .replace("{{service}}", page_path(locale, "service")))


def home_page(locales: dict[str, dict], locale: dict) -> str:
    page = locale["home"]
    hero = page["hero"]
    features = page["features"]
    watch = page["watch"]
    world = page["world"]
    support = page["support"]
    closing = page["closing"]
    facts = "\n".join(
        f'          <div class="hero-fact"><strong>{esc(item["value"])}</strong><span>{esc(item["label"])}</span></div>'
        for item in hero["facts"]
    )
    cards = "\n".join(
        f'''        <article class="feature-card">
          <div class="feature-symbol" aria-hidden="true">{esc(item['symbol'])}</div>
          <h3>{esc(item['title'])}</h3>
          <p>{interpolate(item['html'], locale)}</p>
        </article>''' for item in features["cards"]
    )
    steps = "\n".join(
        f'''          <article class="step"><div class="step-number">{index:02}</div><div><h3>{esc(item['title'])}</h3><p>{esc(item['text'])}</p></div></article>'''
        for index, item in enumerate(watch["steps"], 1)
    )
    images = ["pathway.webp", "arena.webp", "endless-mist.webp"]
    world_cards = "\n".join(
        f'''        <article class="roster-card">
          <img src="assets/{images[index]}" alt="{esc(item['imageAlt'])}" width="960" height="640" loading="lazy" decoding="async" sizes="(max-width: 560px) 100vw, (max-width: 820px) 50vw, 33vw">
          <div class="roster-label"><small>{esc(item['label'])}</small><h3>{esc(item['title'])}</h3><p>{esc(item['text'])}</p></div>
        </article>''' for index, item in enumerate(world["cards"])
    )
    support_items = "\n".join(
        f'          <div class="support-item"><span>{esc(item["label"])}</span><div>{interpolate(item["html"], locale)}</div></div>'
        for item in support["items"]
    )
    structured = {
        "@context": "https://schema.org", "@type": "VideoGame", "name": "Mistwick Vigil",
        "alternateName": "雾灯行", "description": page["structuredDescription"],
        "applicationCategory": "Game", "operatingSystem": "Android", "genre": ["Action", "Survival"],
        "image": f"{BASE_URL}/assets/cover.webp", "url": page_url(locale, "home"),
        "inLanguage": [locale["htmlLang"]],
        "author": {"@type": "Person", "email": "yongzhen_zou@163.com"},
    }
    return f'''<!doctype html>
<html lang="{esc(locale['htmlLang'])}" dir="{locale['dir']}">
{head(locales, locale, 'home')}
  <script type="application/ld+json">{json.dumps(structured, ensure_ascii=False, separators=(',', ':'))}</script>
<body>
  {header(locales, locale, 'home')}
  <main id="main-content">
    <section class="hero" aria-labelledby="hero-title">
      <div class="hero-inner">
        <div class="hero-copy">
          <p class="kicker">{esc(hero['kicker'])}</p>
          <h1 id="hero-title">{esc(hero['title'])}<span>{esc(hero['subtitle'])}</span></h1>
          <p class="hero-lede">{esc(hero['lede'])}</p>
          <p class="hero-note">{esc(hero['note'])}</p>
          <div class="cta-row">
            <a class="btn btn-primary" href="#features">{esc(hero['primary'])}</a>
            <a class="btn btn-ghost" href="{page_path(locale, 'privacy')}">{esc(hero['secondary'])}</a>
          </div>
          <div class="hero-facts" aria-label="{esc(hero['factsLabel'])}">
{facts}
          </div>
          <a class="scroll-hint" href="#features">{esc(hero['scroll'])}</a>
        </div>
        <figure class="hero-art">
          <img src="assets/cover.webp" alt="{esc(hero['imageAlt'])}" width="960" height="1440" fetchpriority="high" decoding="async" sizes="(max-width: 820px) min(100vw - 32px, 420px), 420px">
        </figure>
      </div>
    </section>

    <section class="section" id="features" aria-labelledby="features-title">
      <div class="wrap">
        <div class="section-head">
          <p class="section-kicker">{esc(features['kicker'])}</p>
          <h2 id="features-title">{esc(features['title'])}</h2>
          <p class="section-lede">{esc(features['lede'])}</p>
        </div>
        <div class="feature-grid">
{cards}
        </div>
      </div>
    </section>

    <section class="section ritual" id="watch" aria-labelledby="watch-title">
      <div class="wrap ritual-inner">
        <div class="ritual-copy">
          <p class="section-kicker">{esc(watch['kicker'])}</p>
          <h2 id="watch-title">{esc(watch['title'])}</h2>
          <p class="section-lede">{esc(watch['lede'])}</p>
          <figure class="ritual-art"><img src="assets/watchkeepers.webp" alt="{esc(watch.get('imageAlt', watch['title']))}" width="960" height="640" loading="lazy" decoding="async" sizes="(max-width: 820px) min(100vw - 32px, 420px), 420px"></figure>
        </div>
        <div class="steps" aria-label="{esc(watch['stepsLabel'])}">
{steps}
        </div>
      </div>
    </section>

    <section class="section roster" id="world" aria-labelledby="world-title">
      <div class="wrap">
        <div class="section-head">
          <p class="section-kicker">{esc(world['kicker'])}</p>
          <h2 id="world-title">{esc(world['title'])}</h2>
          <p class="section-lede">{esc(world['lede'])}</p>
        </div>
        <div class="roster-grid">
{world_cards}
        </div>
      </div>
    </section>

    <section class="section support" id="support" aria-labelledby="support-title">
      <div class="wrap support-grid">
        <div>
          <p class="section-kicker">{esc(support['kicker'])}</p>
          <h2 id="support-title">{esc(support['title'])}</h2>
          <p class="section-lede">{esc(support['lede'])}</p>
        </div>
        <div class="support-card">
{support_items}
        </div>
      </div>
    </section>

    <section class="closing" aria-labelledby="closing-title">
      <div class="wrap">
        <img class="lantern" src="assets/lantern.png" alt="" width="94" height="94" loading="lazy">
        <h2 id="closing-title">{esc(closing['title'])}</h2>
        <p>{esc(closing['text'])}</p>
        <div class="cta-row">
          <a class="btn btn-primary" href="{page_path(locale, 'service')}">{esc(closing['primary'])}</a>
          <a class="btn btn-ghost" href="mailto:yongzhen_zou@163.com">{esc(closing['secondary'])}</a>
        </div>
      </div>
    </section>
  </main>
  {footer(locale, 'home')}
</body>
</html>
'''


def legal_page(locales: dict[str, dict], locale: dict, kind: str) -> str:
    page = locale[kind]
    toc = "".join(f'<a href="#{section["id"]}">{esc(section["toc"])}</a>' for section in page["sections"])
    sections = []
    for section in page["sections"]:
        blocks = []
        for block in section["blocks"]:
            if block["type"] == "p":
                blocks.append(f'          <p>{interpolate(block["html"], locale)}</p>')
            elif block["type"] == "callout":
                blocks.append(f'          <div class="legal-callout">{interpolate(block["html"], locale)}</div>')
            elif block["type"] == "list":
                items = "".join(f'<li>{esc(item)}</li>' for item in block["items"])
                blocks.append(f'          <ul>{items}</ul>')
            else:
                raise ValueError(f"Unknown block type: {block['type']}")
        sections.append(f'''        <section id="{section['id']}">
          <h2>{esc(section['title'])}</h2>
{chr(10).join(blocks)}
        </section>''')
    meta = "".join(f'<span>{esc(item)}</span>' for item in page["meta"])
    return f'''<!doctype html>
<html lang="{esc(locale['htmlLang'])}" dir="{locale['dir']}">
{head(locales, locale, kind)}
<body>
  {header(locales, locale, kind)}
  <main id="main-content" class="legal-shell"><div class="wrap">
    <header class="legal-hero">
      <p class="section-kicker">{esc(page['kicker'])}</p>
      <h1>{esc(page['heading'])}</h1>
      <p class="subtitle">{esc(page['subtitle'])}</p>
      <div class="legal-meta">{meta}</div>
    </header>
    <div class="legal-layout">
      <aside class="toc" aria-label="{esc(page['tocTitle'])}"><strong>{esc(page['tocTitle'])}</strong>{toc}</aside>
      <article class="legal-content">
{chr(10).join(sections)}
      </article>
    </div>
  </div></main>
  {footer(locale, kind)}
</body>
</html>
'''


def build_sitemap(locales: dict[str, dict]) -> str:
    entries = [
        "  <url><loc>https://zouyongzhen.github.io/</loc></url>",
        "  <url><loc>https://zouyongzhen.github.io/saylove/</loc></url>",
        "  <url><loc>https://zouyongzhen.github.io/saylove/privacy-policy.html</loc></url>",
        "  <url><loc>https://zouyongzhen.github.io/saylove/service-policy.html</loc></url>",
    ]
    for kind in ("home", "privacy", "service"):
        alternate_links = "".join(
            f'\n    <xhtml:link rel="alternate" hreflang="{esc(locale["htmlLang"])}" href="{page_url(locale, kind)}"/>'
            for locale in locales.values()
        )
        alternate_links += f'\n    <xhtml:link rel="alternate" hreflang="x-default" href="{page_url(locales["en"], kind)}"/>'
        for locale in locales.values():
            entries.append(
                f'  <url>\n    <loc>{page_url(locale, kind)}</loc>{alternate_links}\n'
                '    <lastmod>2026-11-23</lastmod>\n  </url>'
            )
    return '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"\n        xmlns:xhtml="http://www.w3.org/1999/xhtml">\n' + "\n".join(entries) + "\n</urlset>\n"


def redirect_page(target: str, title: str, link_text: str) -> str:
    canonical = f"{BASE_URL}/" if target == "./" else f"{BASE_URL}/{target}"
    return f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex,follow">
  <meta http-equiv="refresh" content="0; url={target}">
  <link rel="canonical" href="{canonical}">
  <title>{esc(title)}</title>
</head>
<body><p><a href="{target}">{esc(link_text)}</a></p></body>
</html>
'''


def main() -> int:
    locales = {}
    for code in LOCALES:
        path = SOURCE / f"{code}.json"
        if not path.exists():
            print(f"Missing localization: {path}", file=sys.stderr)
            return 1
        with path.open(encoding="utf-8") as source:
            locales[code] = json.load(source)
    validate(locales)
    validate_assets()
    for locale in locales.values():
        for kind in ("home", "privacy", "service"):
            path = ROOT / ("index.html" if kind == "home" and locale["code"] == "en" else page_path(locale, kind))
            content = home_page(locales, locale) if kind == "home" else legal_page(locales, locale, kind)
            path.write_text(content, encoding="utf-8")
    # Keep links that were published before the localized page set was
    # expanded working. These aliases are noindex redirects, not copies.
    for alias, (target, title, link_text) in LEGACY_ALIASES.items():
        (ROOT / alias).write_text(redirect_page(target, title, link_text), encoding="utf-8")
    (ROOT.parent / "sitemap.xml").write_text(build_sitemap(locales), encoding="utf-8")
    print(f"Built {len(locales) * 3} localized pages and sitemap.xml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
