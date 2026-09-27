"""Keep pieces.json in sync with everything Ethan Lou has published in The Globe and Mail.

Each run asks the Globe's own article search for every piece under Ethan's byline
(falling back to the RSS feed if that fails) and adds any piece not already in
pieces.json. Nothing already in pieces.json is ever changed or removed, so your
edits to titles, blurbs, images and order are safe.

Pieces newer than anything already in the file are new publications and get
"show" set by new_pieces_shown_by_default. Older ones (the back catalogue) come in
with "show": false, so they are there to switch on but never appear by surprise.

To hide or show a piece, edit its "show" value in pieces.json.
"""

import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path

SITE = "https://www.theglobeandmail.com"
SEARCH_QUERY = '(credits.by.name:"Ethan Lou" OR credits.by.slug:"ethan-lou") AND NOT slug:"secretcanada-repub-"'
FEED_URL = SITE + "/arc/outboundfeeds/rss/author/ethanlou/?outputType=xml"
PIECES_FILE = Path(__file__).parent / "pieces.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ethanlou.com feed updater)"}


def get(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def clean_title(title):
    return re.sub(r"^\s*Opinion:\s*", "", title or "").strip()


def make_blurb(description):
    text = (description or "").strip()
    if text and text[-1] not in ".?!”\"":
        text += "."
    return f"In the Globe and Mail: {text}" if text else ""


def from_search():
    """Every piece under the byline, via the Globe's article search."""
    items, start = [], 0
    while True:
        query = json.dumps({"contentQuery": SEARCH_QUERY, "from": start, "size": 100}, separators=(",", ":"))
        url = SITE + "/pf/api/v3/content/fetch/content-search?query=" + urllib.parse.quote(query) + "&_website=theglobeandmail"
        batch = json.loads(get(url)).get("content_elements", [])
        for el in batch:
            path = el.get("canonical_url") or ""
            if not path:
                continue
            promo = (el.get("promo_items") or {}).get("basic") or {}
            image = ((promo.get("resized_urls") or {}).get("w1200") or {}).get("r1xI", "")
            items.append({
                "title": clean_title((el.get("headlines") or {}).get("basic")),
                "url": path if path.startswith("http") else SITE + path,
                "blurb": make_blurb((el.get("subheadlines") or {}).get("basic")),
                "image": image,
                "date": (el.get("display_date") or el.get("publish_date") or "")[:10],
            })
        if len(batch) < 100:
            return items
        start += 100


def from_rss():
    """Fallback: the RSS feed, which only holds the latest piece or two."""
    ns = {"media": "http://search.yahoo.com/mrss/"}
    items = []
    for item in ET.fromstring(get(FEED_URL)).iter("item"):
        url = (item.findtext("link") or "").strip()
        if not url:
            continue
        media = item.find("media:content", ns)
        image = ""
        if media is not None and media.get("url"):
            image = re.sub(r"&(width|height|smart|quality)=[^&]*", "", media.get("url")) + "&width=1200"
        date = ""
        try:
            date = parsedate_to_datetime(item.findtext("pubDate")).date().isoformat()
        except (TypeError, ValueError):
            pass
        items.append({
            "title": clean_title(item.findtext("title")),
            "url": url,
            "blurb": make_blurb(item.findtext("description")),
            "image": image,
            "date": date,
        })
    return items


def normalise(url):
    return url.split("?")[0].rstrip("/").lower()


def main():
    data = json.loads(PIECES_FILE.read_text(encoding="utf-8"))
    pieces = data["pieces"]
    default_show = data.get("new_pieces_shown_by_default", True)
    known_urls = {normalise(p["url"]) for p in pieces}
    known_titles = {p["title"].lower() for p in pieces}
    newest_known = max((p.get("date", "") for p in pieces), default="")

    try:
        found = from_search()
        print(f"Article search returned {len(found)} pieces.")
    except Exception as err:  # search unavailable: fall back to the feed
        print(f"Article search failed ({err}); using the RSS feed instead.")
        found = from_rss()

    new = []
    for item in found:
        # Skip anything already listed, including the duplicate copies wire stories get.
        if normalise(item["url"]) in known_urls or item["title"].lower() in known_titles:
            continue
        is_new_publication = item["date"] > newest_known
        new.append({"show": default_show if is_new_publication else False, **item})
        known_urls.add(normalise(item["url"]))
        known_titles.add(item["title"].lower())

    if not new:
        print("No new pieces.")
        return

    recent = sorted((p for p in new if p["date"] > newest_known), key=lambda p: p["date"], reverse=True)
    older = sorted((p for p in new if p["date"] <= newest_known), key=lambda p: p["date"], reverse=True)
    # New publications go on top; the back catalogue goes below your existing list.
    data["pieces"] = recent + pieces + older
    PIECES_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Added {len(recent)} new and {len(older)} older pieces.")


if __name__ == "__main__":
    main()
