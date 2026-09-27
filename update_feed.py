"""Pull new pieces from Ethan Lou's Globe and Mail RSS feed into pieces.json.

The Globe's author feed only holds the latest piece or two, so this script
keeps a permanent record: every piece it ever sees is added to pieces.json,
and nothing already there is changed. Run by GitHub Actions on a schedule.

To hide or show a piece, edit its "show" value in pieces.json.
"""

import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path

FEED_URL = "https://www.theglobeandmail.com/arc/outboundfeeds/rss/author/ethanlou/?outputType=xml"
PIECES_FILE = Path(__file__).parent / "pieces.json"
NS = {"media": "http://search.yahoo.com/mrss/"}


def fetch_feed():
    req = urllib.request.Request(
        FEED_URL,
        headers={"User-Agent": "Mozilla/5.0 (compatible; ethanlou.com feed updater)"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def clean_title(title):
    # The Globe prefixes opinion headlines with "Opinion:" in some places.
    return re.sub(r"^\s*Opinion:\s*", "", title or "").strip()


def small_image(url):
    # Feed images are full-size (5,000+ px). Ask the Globe's resizer for 1,200 px.
    if not url:
        return ""
    base = re.sub(r"&(width|height|smart|quality)=[^&]*", "", url)
    return base + "&width=1200"


def make_blurb(description):
    text = (description or "").strip()
    if text and text[-1] not in ".?!”\"":
        text += "."
    return f"In the Globe and Mail: {text}" if text else ""


def parse_items(xml_bytes):
    root = ET.fromstring(xml_bytes)
    for item in root.iter("item"):
        url = (item.findtext("link") or "").strip()
        if not url:
            continue
        media = item.find("media:content", NS)
        date = ""
        if item.findtext("pubDate"):
            try:
                date = parsedate_to_datetime(item.findtext("pubDate")).date().isoformat()
            except (TypeError, ValueError):
                pass
        yield {
            "title": clean_title(item.findtext("title")),
            "url": url,
            "blurb": make_blurb(item.findtext("description")),
            "image": small_image(media.get("url") if media is not None else ""),
            "date": date,
        }


def normalise(url):
    return url.split("?")[0].rstrip("/").lower()


def main():
    data = json.loads(PIECES_FILE.read_text(encoding="utf-8"))
    pieces = data["pieces"]
    known = {normalise(p["url"]) for p in pieces}
    default_show = data.get("new_pieces_shown_by_default", True)

    new = []
    for item in parse_items(fetch_feed()):
        if normalise(item["url"]) in known:
            continue
        new.append({"show": default_show, **item})
        known.add(normalise(item["url"]))

    if not new:
        print("No new pieces.")
        return

    # Newest first, placed at the top so the rest of your hand-set order is kept.
    new.sort(key=lambda p: p["date"], reverse=True)
    data["pieces"] = new + pieces
    PIECES_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for p in new:
        print(f"Added: {p['title']}")


if __name__ == "__main__":
    main()
