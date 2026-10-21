#!/usr/bin/env python3
"""Download calendars and newsletters from the private pages listed in LOCAL_CONTEXT.

LOCAL_CONTEXT (a repository secret) may contain lines like:

  Page: https://example.school/school-life/events

For each page, this saves a text copy of the page plus any linked or embedded image or
PDF whose name mentions a calendar, newsletter or update, into .private/ (gitignored),
and writes .private/index.txt for Claude to read. It prints only counts, never URLs or
file names, because the Actions log is public.
"""

from __future__ import annotations

import html
import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / ".private"
KEYWORDS = re.compile(r"calendar|newsletter|update", re.I)
MAX_FILES = 8
MAX_BYTES = 15 * 1024 * 1024
USER_AGENT = "Mozilla/5.0 (compatible; LifeHub/1.0)"


class LinkFinder(HTMLParser):
    """Collects images and PDF links whose name or label mentions a keyword."""

    def __init__(self) -> None:
        super().__init__()
        self.found: list[tuple[str, str, str]] = []  # (kind, url, label)
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "img" and a.get("src"):
            label = a.get("alt") or ""
            if KEYWORDS.search(label) or KEYWORDS.search(a["src"]):
                self.found.append(("image", full_size(a["src"], a.get("width")), label))
        elif tag == "a" and a.get("href"):
            self._href, self._text = a["href"], []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            label = " ".join("".join(self._text).split())
            href = self._href
            if urlparse(href).path.lower().endswith(".pdf") and (KEYWORDS.search(label) or KEYWORDS.search(href)):
                self.found.append(("pdf", href, label))
            self._href = None


def full_size(src: str, width: str | None) -> str:
    """Ask image services for the original width instead of a thumbnail."""
    parts = urlparse(src)
    query = dict(parse_qsl(parts.query))
    if "width" in query:
        # Original width, capped so huge scans stay a sensible size to read.
        query["width"] = str(min(int(width), 2000)) if width and width.isdigit() else "1600"
        query["format"] = "jpg"
    return urlunparse(parts._replace(query=urlencode(query)))


def find_files(page_html: str, page_url: str) -> list[tuple[str, str, str]]:
    finder = LinkFinder()
    finder.feed(page_html)
    seen, files = set(), []
    for kind, url, label in finder.found:
        absolute = urljoin(page_url, html.unescape(url))
        if absolute not in seen:
            seen.add(absolute)
            files.append((kind, absolute, label))
    return files


def page_text(page_html: str) -> str:
    text = re.sub(r"<(script|style)\b.*?</\1>", " ", page_html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def fetch(url: str) -> bytes:
    with urlopen(Request(url, headers={"User-Agent": USER_AGENT}), timeout=30) as resp:
        data = resp.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("file too large")
    return data


def main() -> int:
    context = os.environ.get("LOCAL_CONTEXT", "").replace("\r", "")
    pages = re.findall(r"^\s*page:\s*(https?://\S+)", context, flags=re.I | re.M)
    if not pages:
        print("Private pages: none listed")
        return 0

    OUT.mkdir(exist_ok=True)
    index, saved, failed = [], 0, 0
    for p, page_url in enumerate(pages, 1):
        try:
            page_html = fetch(page_url).decode("utf-8", "replace")
        except Exception:
            failed += 1
            continue
        text_file = OUT / f"page{p}.txt"
        text_file.write_text(f"Source: {page_url}\n\n{page_text(page_html)}\n", encoding="utf-8")
        index.append(f"{text_file.relative_to(ROOT)}  (text of {page_url})")
        for kind, url, label in find_files(page_html, page_url):
            if saved >= MAX_FILES:
                break
            ext = ".pdf" if kind == "pdf" else ".jpg"
            target = OUT / f"page{p}-file{saved + 1}{ext}"
            try:
                target.write_bytes(fetch(url))
            except Exception:
                failed += 1
                continue
            saved += 1
            index.append(f"{target.relative_to(ROOT)}  ({kind}: {label or 'untitled'}; from {url})")

    (OUT / "index.txt").write_text("\n".join(index) + "\n", encoding="utf-8")
    print(f"Private pages: {len(pages)} listed, {saved} files saved, {failed} failed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
