#!/usr/bin/env python3
"""Inspect newly resolved Gate-1 source files and schemas for taxonomy v31.

Sources:
- Relevanta kompetenser v31 (.json.zst)
- taxonomy keyword concepts with relations (the published search-concept view)
- taxonomy substitutability relations between occupations
- Närliggande yrken v31 directory contents

This is a schema probe, not yet the final coverage adapter.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Any

import zstandard as zstd

USER_AGENT = "semantic-taxonomy-search-gate1-probe/0.1"

URLS = {
    "relevant_skills": "https://data.arbetsformedlingen.se/yrke/relevanta-kompetenser/v1/relevanta-kompetenser-t31.json.zst",
    "search_concepts": "https://data.jobtechdev.se/taxonomy/version/31/query/keyword-concepts-with-relations/keyword-concepts-with-relations.json",
    "substitutability": "https://data.jobtechdev.se/taxonomy/version/31/query/substitutability-relations-between-occupations/substitutability-relations-between-occupations.json",
    "nearby_index": "https://data.arbetsformedlingen.se/yrke/narliggande-yrken/v1/t31/index.html",
}


class Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href is not None:
            self.links.append((self._href, re.sub(r"\s+", " ", " ".join(self._text)).strip()))
            self._href = None
            self._text = []


def fetch(url: str, timeout: int = 180) -> tuple[bytes, str, str]:
    req = urllib.request.Request(url, headers={"Accept": "*/*", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read(), response.headers.get("content-type", ""), response.geturl()


def shape(value: Any, depth: int = 0) -> Any:
    if depth >= 4:
        if isinstance(value, dict):
            return f"object[{len(value)}]"
        if isinstance(value, list):
            return f"list[{len(value)}]"
        return type(value).__name__
    if isinstance(value, dict):
        return {str(k): shape(v, depth + 1) for k, v in list(value.items())[:30]}
    if isinstance(value, list):
        return [] if not value else [shape(value[0], depth + 1), f"count={len(value)}"]
    return type(value).__name__


def inspect_json(name: str, url: str, compressed: bool = False) -> None:
    try:
        body, content_type, final = fetch(url)
    except Exception as exc:
        print(name, "FETCH_ERROR", repr(exc))
        return
    wire_sha = hashlib.sha256(body).hexdigest()
    raw = zstd.ZstdDecompressor().decompress(body) if compressed else body
    try:
        value = json.loads(raw)
    except Exception as exc:
        print(name, "PARSE_ERROR", repr(exc), "wire_bytes", len(body), "wire_sha256", wire_sha)
        return
    meta = {
        "url": url,
        "final_url": final,
        "content_type": content_type,
        "wire_bytes": len(body),
        "wire_sha256": wire_sha,
        "json_bytes": len(raw),
        "json_sha256": hashlib.sha256(raw).hexdigest(),
        "shape": shape(value),
    }
    print(name, "JSON", json.dumps(meta, ensure_ascii=False)[:50000])
    if isinstance(value, dict):
        print(name, "TOP_KEYS", json.dumps(list(value.keys())[:50], ensure_ascii=False))
        data = value.get("data")
        if isinstance(data, list):
            print(name, "DATA_COUNT", len(data), "SAMPLE", json.dumps(data[:2], ensure_ascii=False)[:20000])
        elif isinstance(data, dict):
            print(name, "DATA_COUNT", len(data), "SAMPLE", json.dumps(list(data.items())[:2], ensure_ascii=False)[:20000])


def inspect_nearby_index() -> None:
    url = URLS["nearby_index"]
    body, content_type, final = fetch(url)
    print("nearby_index", "PAGE", json.dumps({
        "url": url,
        "final_url": final,
        "content_type": content_type,
        "bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
    }, ensure_ascii=False))
    text = body.decode("utf-8", errors="replace")
    parser = Links()
    parser.feed(text)
    links = []
    files = []
    for href, label in parser.links:
        absolute = urllib.parse.urljoin(final, href)
        if absolute.startswith("https://data.arbetsformedlingen.se/yrke/narliggande-yrken/v1/t31/"):
            links.append({"url": absolute, "text": label})
            if not absolute.endswith("index.html") and not absolute.endswith("/"):
                files.append(absolute)
    print("nearby_index", "LINKS", json.dumps(links, ensure_ascii=False)[:50000])
    print("nearby_index", "FILES", json.dumps(files, ensure_ascii=False)[:50000])

    # Inspect a bounded set of obvious JSON/ZST resources. Do not download an
    # unbounded shard collection in this schema probe.
    for i, file_url in enumerate(files[:20]):
        low = file_url.lower()
        if low.endswith(".json.zst"):
            inspect_json(f"nearby_file_{i}", file_url, compressed=True)
        elif low.endswith(".json"):
            inspect_json(f"nearby_file_{i}", file_url, compressed=False)


def main() -> int:
    inspect_json("relevant_skills", URLS["relevant_skills"], compressed=True)
    inspect_json("search_concepts", URLS["search_concepts"])
    inspect_json("substitutability", URLS["substitutability"])
    inspect_nearby_index()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
