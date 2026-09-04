#!/usr/bin/env python3
"""Probe AF public file areas and print concrete JSON filenames/schemas.

Research-only discovery tool. It never infers a missing file as zero coverage.
Once a distribution and schema are verified, write a dedicated adapter and
record the exact source URL/hash in the coverage registry.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Any

USER_AGENT = "semantic-taxonomy-search-file-area-probe/0.2"
TARGET_VERSION = 31

ROOTS = {
    "yrkesvaljaren": "https://data.arbetsformedlingen.se/yrke/yrkesvaljaren/",
    "relevant-skills": "https://data.arbetsformedlingen.se/yrke/relevanta-kompetenser/",
    "skill-selector": "https://data.arbetsformedlingen.se/kompetens/kompetensvaljaren/",
    "nearby-occupations": "https://data.arbetsformedlingen.se/yrke/narliggande-yrken/",
}


class Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.items: list[tuple[str, str]] = []
        self.href: str | None = None
        self.text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            self.href = dict(attrs).get("href")
            self.text = []

    def handle_data(self, data: str) -> None:
        if self.href is not None:
            self.text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self.href is not None:
            self.items.append((self.href, re.sub(r"\s+", " ", " ".join(self.text)).strip()))
            self.href = None
            self.text = []


def get(url: str, timeout: int = 120) -> tuple[bytes, str, str]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        body = response.read()
        return body, response.geturl(), response.headers.get("content-type", "")


def shape(value: Any, depth: int = 0) -> Any:
    if depth >= 4:
        if isinstance(value, list):
            return f"list[{len(value)}]"
        if isinstance(value, dict):
            return f"object[{len(value)}]"
        return type(value).__name__
    if isinstance(value, dict):
        return {str(k): shape(v, depth + 1) for k, v in list(value.items())[:35]}
    if isinstance(value, list):
        return [] if not value else [shape(value[0], depth + 1), f"count={len(value)}"]
    return type(value).__name__


def html_links(url: str) -> list[str]:
    body, final, ctype = get(url)
    print("INDEX", json.dumps({
        "url": url,
        "final_url": final,
        "content_type": ctype,
        "bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
    }, ensure_ascii=False))
    if "html" not in ctype:
        return []
    parser = Links()
    parser.feed(body.decode("utf-8", errors="replace"))
    urls: list[str] = []
    for href, _ in parser.items:
        absolute = urllib.parse.urljoin(final, href)
        path = urllib.parse.urlparse(absolute).path.lower()
        if path.endswith(".json") or path.rstrip("/").endswith("/v1"):
            urls.append(absolute)
    return sorted(set(urls))


def choose_version_file(urls: list[str]) -> str | None:
    markers = (f"t{TARGET_VERSION}.json", f"v{TARGET_VERSION}.json", f"-{TARGET_VERSION}.json", f"_{TARGET_VERSION}.json")
    for url in urls:
        if any(marker in url.lower() for marker in markers):
            return url
    jsons = [u for u in urls if u.lower().endswith(".json")]
    return jsons[-1] if jsons else None


def probe(name: str, root: str) -> None:
    print(f"\n=== {name} ===")
    candidates: list[str] = []
    for url in (root, urllib.parse.urljoin(root, "index.html"), urllib.parse.urljoin(root, "v1/"), urllib.parse.urljoin(root, "v1/index.html")):
        try:
            candidates.extend(html_links(url))
        except Exception as exc:
            print("INDEX_ERROR", json.dumps({"url": url, "error": repr(exc)}, ensure_ascii=False))
    candidates = sorted(set(candidates))
    print("FILES", json.dumps(candidates, ensure_ascii=False))
    chosen = choose_version_file(candidates)
    if not chosen:
        print("NO_JSON_FILE_RESOLVED")
        return
    body, final, ctype = get(chosen, timeout=180)
    digest = hashlib.sha256(body).hexdigest()
    print("CHOSEN", json.dumps({
        "url": chosen,
        "final_url": final,
        "content_type": ctype,
        "bytes": len(body),
        "sha256": digest,
    }, ensure_ascii=False))
    try:
        value = json.loads(body)
    except Exception as exc:
        print("JSON_ERROR", repr(exc))
        return
    print("JSON_SHAPE", json.dumps(shape(value), ensure_ascii=False)[:30000])
    if isinstance(value, list) and value:
        print("SAMPLE", json.dumps(value[0], ensure_ascii=False)[:12000])
    elif isinstance(value, dict):
        for key in ("data", "concepts", "occupations", "items", "results"):
            child = value.get(key)
            if isinstance(child, list) and child:
                print("SAMPLE", json.dumps(child[0], ensure_ascii=False)[:12000])
                break
            if isinstance(child, dict):
                print("SAMPLE", json.dumps({key: child}, ensure_ascii=False)[:12000])
                break


def main() -> int:
    for name, root in ROOTS.items():
        probe(name, root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
