#!/usr/bin/env python3
"""Generate a static Engineering Good site from the public WordPress API."""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import shutil
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "assets" / "site"
BASE_URL = "https://www.engineeringgood.org"
PAGES_API = f"{BASE_URL}/wp-json/wp/v2/pages?per_page=100&_embed=1"
POSTS_API = f"{BASE_URL}/wp-json/wp/v2/posts?per_page=100&_embed=1"
CATEGORIES_API = f"{BASE_URL}/wp-json/wp/v2/categories?per_page=100"
DEPLOY_BASE = "https://snyperf1.github.io/engineeringgood-homepage-refresh/"
ASSET_VERSION = "20260529-cardfix"

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Codex static-site recreation"})

NAV_ITEMS = [
    ("Home", "/"),
    ("About", "/about/"),
    ("Assistive Technology", "/assistive-technology/"),
    ("Digital Inclusion", "/digital-inclusion/"),
    ("Stories", "/stories/"),
    ("Events", "/events/"),
    ("Contribute", "/individual/"),
]

FOOTER_LINKS = [
    ("About", "/about/"),
    ("Contact", "/contact-faq/"),
    ("Careers", "/careers/"),
    ("Donate", "/donate/"),
    ("Terms", "/terms-of-service/"),
    ("Privacy", "/privacy-policy/"),
]

FALLBACK_HERO = "assets/hero-assistive.webp"
ALIASES = {
    "/contribute/": "/individual/",
    "/about-us/publications-and-media/": "/media/",
}


def fetch_json(url: str):
    response = SESSION.get(url, timeout=45)
    response.raise_for_status()
    return response.json()


def text_from_html(value: str) -> str:
    soup = BeautifulSoup(value or "", "html.parser")
    return " ".join(soup.get_text(" ", strip=True).split())


def truncate_text(value: str, limit: int = 210) -> str:
    value = " ".join((value or "").replace("[…]", "").replace("...", "").split())
    if len(value) <= limit:
        return value
    clipped = value[: limit + 1]
    sentence = max(clipped.rfind("."), clipped.rfind("!"), clipped.rfind("?"))
    if sentence > 80:
        return clipped[: sentence + 1]
    word = clipped.rfind(" ")
    return clipped[:word].rstrip(" ,;:") + "."


def summary_for(item: dict, limit: int = 210) -> str:
    content = item.get("content", {}).get("rendered", "")
    soup = BeautifulSoup(content or "", "html.parser")
    for paragraph in soup.find_all("p"):
        text = text_from_html(str(paragraph))
        if len(text) >= 45:
            return truncate_text(text, limit)
    excerpt = text_from_html(item.get("excerpt", {}).get("rendered", ""))
    if excerpt:
        return truncate_text(excerpt, limit)
    return truncate_text(text_from_html(content), limit)


def normalize_internal_path(url: str) -> str | None:
    if not url:
        return None
    parsed = urlparse(urljoin(BASE_URL, url))
    if parsed.scheme not in ("http", "https"):
        return None
    host = parsed.netloc.lower().replace("www.", "")
    if host != "engineeringgood.org":
        return None
    path = parsed.path or "/"
    return "/" + path.strip("/") + ("/" if path.strip("/") else "")


def route_from_path(path: str) -> str:
    clean = path.strip("/")
    if not clean:
        return "index.html"
    return f"{clean}/index.html"


def output_path_for_url(url: str) -> Path:
    path = normalize_internal_path(url) or "/"
    return ROOT / route_from_path(path)


def relative_root(output_file: Path) -> str:
    rel_dir = output_file.parent.relative_to(ROOT)
    if str(rel_dir) == ".":
        return ""
    return "../" * len(rel_dir.parts)


def relative_href(current_file: Path, target_route: str) -> str:
    start = current_file.parent
    target = ROOT / target_route
    href = os.path.relpath(target, start).replace(os.sep, "/")
    if href == "index.html":
        return "./"
    return href


def safe_filename(url: str) -> str:
    parsed = urlparse(url)
    name = unquote(Path(parsed.path).name) or "asset"
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-")
    if "." not in name:
        name += ".jpg"
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    return f"{digest}-{name}"


def full_asset_url(url: str) -> str:
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return urljoin(BASE_URL, url)
    return url


def is_downloadable_asset(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and parsed.netloc.endswith("engineeringgood.org")


def download_asset(url: str) -> str:
    url = full_asset_url(url.strip("\"' "))
    if not is_downloadable_asset(url):
        return url

    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    destination = ASSET_DIR / safe_filename(url)
    if not destination.exists():
        response = SESSION.get(url, timeout=60)
        response.raise_for_status()
        destination.write_bytes(response.content)
    return destination.relative_to(ROOT).as_posix()


def local_asset_href(current_file: Path, asset_path: str) -> str:
    if asset_path.startswith(("http://", "https://", "mailto:", "tel:", "#")):
        return asset_path
    return relative_href(current_file, asset_path)


def first_image_url(content: str) -> str | None:
    soup = BeautifulSoup(content or "", "html.parser")
    image = soup.find("img")
    if image and image.get("src"):
        return image["src"]
    match = re.search(r"background-image:\s*url\(([^)]+)\)", content or "")
    if match:
        return match.group(1)
    return None


def featured_image(item: dict) -> str | None:
    media = item.get("_embedded", {}).get("wp:featuredmedia", [])
    if media and media[0].get("source_url"):
        return media[0]["source_url"]
    return first_image_url(item.get("content", {}).get("rendered", ""))


def rewrite_link(href: str, current_file: Path, route_map: dict[str, str]) -> str:
    if not href:
        return href
    if href.startswith("mailto:"):
        return "mailto:" + href.replace("mailto:", "", 1).strip()
    if href.startswith(("#", "tel:", "javascript:")):
        return href
    if href.startswith("ahttp://") or href.startswith("ahttps://"):
        href = href[1:]
    if "@" in href and "://" not in href and not href.startswith("/"):
        return f"mailto:{href}"
    parsed = urlparse(href)
    if parsed.scheme and parsed.netloc:
        path = normalize_internal_path(href)
        if path and path in route_map:
            local = relative_href(current_file, route_map[path])
            return local + (f"#{parsed.fragment}" if parsed.fragment else "")
        return href
    if href.startswith("/"):
        path = "/" + href.strip("/") + "/"
        if path in route_map:
            return relative_href(current_file, route_map[path])
        return href.lstrip("/")
    return href


def compact_context(value: str, limit: int = 90) -> str:
    value = re.sub(r"\b(read|read more|watch|listen)\b", "", value or "", flags=re.I)
    value = re.sub(r"\s+", " ", value).strip(" -:|,")
    if not value:
        return "this item"
    if len(value) <= limit:
        return value
    clipped = value[: limit + 1]
    return clipped[: clipped.rfind(" ")].rstrip(" -:|,") + "."


def improve_link_labels(soup: BeautifulSoup) -> None:
    generic = {"read more", "read", "learn more", "click here", "here"}

    def context_for(link) -> str:
        heading = link.find(["h2", "h3", "h4", "h5", "h6"])
        if heading and heading.get_text(strip=True):
            return compact_context(heading.get_text(" ", strip=True))
        context_node = link.find_parent(["li", "p", "figcaption", "td"])
        context = text_from_html(str(context_node)) if context_node else ""
        if not context:
            previous_heading = link.find_previous(["h2", "h3", "h4", "h5", "h6"])
            context = previous_heading.get_text(" ", strip=True) if previous_heading else ""
        if not context:
            context = text_from_html(str(link))
        return compact_context(context)

    for link in soup.find_all("a"):
        label = text_from_html(str(link)).lower().strip("» ")
        context = context_for(link)
        if label in generic:
            link.clear()
            link.append(f"Read more about {context}")
            continue

        for text_node in list(link.find_all(string=True)):
            node_label = " ".join(text_node.strip().lower().strip("» ").split())
            if node_label in generic:
                text_node.replace_with(f"Explore {context}")


def normalize_headings(soup: BeautifulSoup) -> None:
    for heading in soup.find_all(["h1", "h4", "h5", "h6"]):
        if not heading.get_text(strip=True):
            heading.decompose()
            continue
        heading.name = "h2" if heading.name == "h1" else "h3"

    for heading in soup.find_all(["h2", "h3"]):
        if not heading.get_text(strip=True) and not heading.find("img"):
            heading.decompose()


def clean_content(raw_html: str, current_file: Path, route_map: dict[str, str]) -> str:
    soup = BeautifulSoup(raw_html or "", "html.parser")

    for tag in soup.find_all(["script", "style", "noscript", "svg"]):
        tag.decompose()

    for tag in soup.find_all(style=True):
        match = re.search(r"background-image:\s*url\(([^)]+)\)", tag.get("style", ""))
        if match:
            asset = download_asset(match.group(1))
            image = soup.new_tag("img")
            image["src"] = asset
            image["alt"] = tag.get("aria-label") or tag.get("title") or ""
            if not tag.get_text(strip=True) and not tag.find(["img", "p", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol"]):
                tag.replace_with(image)
            else:
                tag.insert(0, image)
        tag.attrs.pop("style", None)

    for image in soup.find_all("img"):
        src = image.get("src") or image.get("data-src")
        if src:
            asset = download_asset(src)
            image["src"] = local_asset_href(current_file, asset)
        image.attrs.pop("srcset", None)
        image.attrs.pop("sizes", None)
        image.attrs.pop("class", None)
        image.attrs.pop("decoding", None)
        image.attrs.pop("loading", None)
        image.attrs.pop("fetchpriority", None)
        if not image.get("alt"):
            image["alt"] = image.get("title", "")

    for link in soup.find_all("a"):
        if link.get("href"):
            link["href"] = rewrite_link(link["href"], current_file, route_map)
        if link.get("href", "").startswith(("http://", "https://")):
            link["target"] = "_blank"
            link["rel"] = "noopener"

    improve_link_labels(soup)
    normalize_headings(soup)

    allowed_attrs = {
        "a": {"href", "target", "rel"},
        "img": {"src", "alt", "title", "width", "height"},
        "iframe": {"src", "title", "allow", "allowfullscreen", "loading"},
        "table": set(),
        "thead": set(),
        "tbody": set(),
        "tr": set(),
        "th": set(),
        "td": set(),
        "blockquote": set(),
        "figure": set(),
        "figcaption": set(),
        "br": set(),
        "p": set(),
        "h1": set(),
        "h2": set(),
        "h3": set(),
        "h4": set(),
        "h5": set(),
        "h6": set(),
        "ul": set(),
        "ol": set(),
        "li": set(),
        "strong": set(),
        "b": set(),
        "em": set(),
        "i": set(),
    }

    for tag in soup.find_all(True):
        if tag.name in {"div", "section", "article", "span"}:
            tag.unwrap()
            continue
        if tag.name not in allowed_attrs:
            tag.unwrap()
            continue
        keep = allowed_attrs[tag.name]
        tag.attrs = {key: value for key, value in tag.attrs.items() if key in keep}

    for tag in list(soup.find_all(True)):
        if tag.name in {"br", "img", "iframe"}:
            continue
        if not tag.get_text(strip=True) and not tag.find(["img", "iframe"]):
            tag.decompose()

    return soup.decode_contents()


def nav_html(current_file: Path, route_map: dict[str, str]) -> str:
    links = []
    for label, path in NAV_ITEMS:
        links.append(f'<li><a href="{relative_href(current_file, route_map[path])}">{html.escape(label)}</a></li>')
    donate = relative_href(current_file, route_map["/donate/"])
    home = relative_href(current_file, route_map["/"])
    logo = local_asset_href(current_file, "assets/logo.webp")
    return f"""
    <header class="site-header">
      <a class="brand-mark" href="{home}" aria-label="Engineering Good home">
        <img src="{logo}" alt="Engineering Good logo" />
      </a>
      <button class="menu-toggle" type="button" aria-controls="site-navigation" aria-expanded="false">
        <span></span><span></span><span></span><span class="sr-only">Menu</span>
      </button>
      <nav class="site-nav" id="site-navigation" aria-label="Primary navigation">
        <ul>{''.join(links)}</ul>
      </nav>
      <a class="donate-link" href="{donate}">Donate</a>
    </header>
    """


def footer_html(current_file: Path, route_map: dict[str, str]) -> str:
    logo = local_asset_href(current_file, "assets/logo-white.webp")
    footer_links = " ".join(
        f'<a href="{relative_href(current_file, route_map[path])}">{html.escape(label)}</a>' for label, path in FOOTER_LINKS
    )
    return f"""
    <footer class="site-footer">
      <div class="footer-grid">
        <div>
          <img class="footer-logo" src="{logo}" alt="Engineering Good" />
          <p>Engineering Good is a Singapore registered Charity and Company Limited by Guarantee.</p>
          <p>UEN 201408320W</p>
        </div>
        <address>
          <strong>Contact Info</strong>
          <span>41, Jalan Pemimpin, #03-06A</span>
          <span>Kong Beng Industrial Building, Singapore 577186</span>
          <a href="mailto:contactus@engineeringgood.org">contactus@engineeringgood.org</a>
        </address>
        <div>
          <strong>Explore</strong>
          <div class="footer-link-list">{footer_links}</div>
        </div>
      </div>
      <div class="footer-bottom">
        <p>Copyright © 2024 Engineering Good</p>
        <div>
          <a href="https://www.facebook.com/engineeringgood.org/">Facebook</a>
          <a href="https://sg.linkedin.com/company/engineeringgood">LinkedIn</a>
          <a href="https://instagram.com/engineeringgood">Instagram</a>
        </div>
      </div>
    </footer>
    """


def page_template(
    *,
    item: dict,
    current_file: Path,
    route_map: dict[str, str],
    kind: str,
    content_html: str,
    extra_html: str = "",
) -> str:
    root = relative_root(current_file)
    title = text_from_html(item.get("title", {}).get("rendered", "Engineering Good"))
    excerpt = summary_for(item)
    hero_url = featured_image(item)
    hero_asset = download_asset(hero_url) if hero_url else FALLBACK_HERO
    hero_src = local_asset_href(current_file, hero_asset)
    css = f"{local_asset_href(current_file, 'styles.css')}?v={ASSET_VERSION}"
    js = f"{local_asset_href(current_file, 'script.js')}?v={ASSET_VERSION}"
    source = item.get("link", BASE_URL)
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{html.escape(title)} | Engineering Good</title>
    <meta name="description" content="{html.escape(excerpt)}" />
    <link rel="stylesheet" href="{css}" />
  </head>
  <body class="subpage">
    <a class="skip-link" href="#content">Skip to content</a>
    {nav_html(current_file, route_map)}
    <main id="content">
      <section class="page-hero">
        <img src="{hero_src}" alt="" />
        <div class="image-overlay"></div>
        <div class="page-hero-inner">
          <p class="eyebrow">{html.escape(kind)}</p>
          <h1>{html.escape(title)}</h1>
          <p>{html.escape(excerpt)}</p>
        </div>
      </section>
      <div class="content-shell">
        <nav class="breadcrumb" aria-label="Breadcrumb">
          <a href="{relative_href(current_file, route_map['/'])}">Home</a>
          <span>{html.escape(title)}</span>
        </nav>
        <article class="wp-content">
          {content_html}
        </article>
        {extra_html}
        <p class="source-note">Static recreation from <a href="{html.escape(source)}">engineeringgood.org</a>.</p>
      </div>
    </main>
    {footer_html(current_file, route_map)}
    <script src="{js}"></script>
  </body>
</html>
"""


def post_card(post: dict, current_file: Path, route_map: dict[str, str]) -> str:
    title = text_from_html(post.get("title", {}).get("rendered", "Story"))
    excerpt = text_from_html(post.get("excerpt", {}).get("rendered", ""))[:180]
    image = featured_image(post)
    src = local_asset_href(current_file, download_asset(image) if image else FALLBACK_HERO)
    href = relative_href(current_file, route_map[normalize_internal_path(post["link"])])
    date = post.get("date", "")[:10]
    return f"""
      <article class="story-card listing-card">
        <a href="{href}"><img src="{src}" alt="" /></a>
        <div>
          <p class="story-date">{html.escape(date)}</p>
          <h3><a href="{href}">{html.escape(title)}</a></h3>
          <p>{html.escape(excerpt)}</p>
        </div>
      </article>
    """


def listing_html(posts: list[dict], current_file: Path, route_map: dict[str, str], heading: str) -> str:
    cards = "\n".join(post_card(post, current_file, route_map) for post in posts)
    return f"""
      <section class="generated-listing" aria-labelledby="listing-title">
        <div class="section-grid compact">
          <div>
            <p class="section-kicker">Archive</p>
            <h2 id="listing-title">{html.escape(heading)}</h2>
          </div>
        </div>
        <div class="story-grid">{cards}</div>
      </section>
    """


def rewrite_homepage_links(route_map: dict[str, str]) -> None:
    index = ROOT / "index.html"
    soup = BeautifulSoup(index.read_text(encoding="utf-8"), "html.parser")
    for link in soup.find_all("a"):
        href = link.get("href")
        if href:
            link["href"] = rewrite_link(href, index, route_map)
    index.write_text(str(soup), encoding="utf-8")


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def make_sitemap(routes: list[str]) -> None:
    entries = []
    for route in sorted(set(routes)):
        if route == "index.html":
            loc = DEPLOY_BASE
        else:
            loc = urljoin(DEPLOY_BASE, route.replace("index.html", ""))
        entries.append(f"  <url><loc>{html.escape(loc)}</loc></url>")
    write_file(
        ROOT / "sitemap.xml",
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(entries)
        + "\n</urlset>\n",
    )


def main() -> None:
    pages = fetch_json(PAGES_API)
    posts = fetch_json(POSTS_API)
    categories = fetch_json(CATEGORIES_API)

    route_map: dict[str, str] = {"/": "index.html"}
    for item in pages + posts:
        path = normalize_internal_path(item["link"])
        if path:
            route_map[path] = route_from_path(path)
    for category in categories:
        path = normalize_internal_path(category["link"])
        if path:
            route_map[path] = route_from_path(path)
    for alias, destination in ALIASES.items():
        if destination in route_map:
            route_map[alias] = route_map[destination]

    for item in pages:
        path = normalize_internal_path(item["link"])
        if not path or path == "/":
            continue
        current_file = ROOT / route_map[path]
        content = clean_content(item.get("content", {}).get("rendered", ""), current_file, route_map)
        extra = ""
        if item.get("slug") == "stories":
            extra = listing_html(posts, current_file, route_map, "All stories")
        write_file(
            current_file,
            page_template(item=item, current_file=current_file, route_map=route_map, kind="Page", content_html=content, extra_html=extra),
        )

    for item in posts:
        path = normalize_internal_path(item["link"])
        if not path:
            continue
        current_file = ROOT / route_map[path]
        content = clean_content(item.get("content", {}).get("rendered", ""), current_file, route_map)
        write_file(
            current_file,
            page_template(item=item, current_file=current_file, route_map=route_map, kind="Story", content_html=content),
        )

    by_category = {category["id"]: category for category in categories}
    for category in categories:
        path = normalize_internal_path(category["link"])
        if not path:
            continue
        current_file = ROOT / route_map[path]
        category_posts = [post for post in posts if category["id"] in post.get("categories", [])]
        stub = {
            "title": {"rendered": category["name"]},
            "excerpt": {"rendered": category.get("description") or f"Engineering Good {category['name']} archive."},
            "content": {"rendered": ""},
            "link": category["link"],
        }
        content = listing_html(category_posts, current_file, route_map, category["name"])
        write_file(
            current_file,
            page_template(item=stub, current_file=current_file, route_map=route_map, kind="Archive", content_html=content),
        )

    rewrite_homepage_links(route_map)

    not_found = ROOT / "404.html"
    stub = {
        "title": {"rendered": "Page not found"},
        "excerpt": {"rendered": "The page you were looking for is not available in this static recreation."},
        "content": {"rendered": '<p>Use the navigation to continue exploring Engineering Good.</p>'},
        "link": DEPLOY_BASE,
    }
    write_file(
        not_found,
        page_template(
            item=stub,
            current_file=not_found,
            route_map=route_map,
            kind="404",
            content_html='<p>Use the navigation to continue exploring Engineering Good.</p>',
        ),
    )

    make_sitemap(list(route_map.values()) + ["404.html"])
    print(json.dumps({"pages": len(pages), "posts": len(posts), "categories": len(categories), "routes": len(route_map)}, indent=2))


if __name__ == "__main__":
    main()
