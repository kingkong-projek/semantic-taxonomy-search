#!/usr/bin/env python3
"""Discover concrete files behind unresolved public AF semantic data sources.

The catalogue often exposes a file-area URL while the actual file name lives in
an HTML directory index. This probe crawls only a small allow-listed set of AF
public roots, records link targets and attempts JSON resources it discovers.

It is intentionally diagnostic. A discovered URL is not promoted to an adapter
until its schema/version/join keys are validated by a dedicated extractor.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Any

USER_AGENT = "semantic-taxonomy-search-source-discovery/0.1"
ROOTS = {
    "relevant-skills": "https://data.arbetsformedlingen.se/yrke/relevanta-kompetenser/v1/",
    "nearby-occupations": "https://data.arbetsformedlingen.se/yrke/narliggande-yrken/v1/",
    "taxonomy-v31-query": "https://data.jobtechdev.se/taxonomy/version/31/query/",
}
ALLOWED_HOSTS = {"data.arbetsformedlingen.se", "data.jobtechdev.se"}


class Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
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
            self.links.append((self.href, re.sub(r"\s+", " ", " ".join(self.text)).strip()))
            self.href = None
            self.text = []


def fetch(url: str, timeout: int = 120) -> tuple[bytes, str, str]:
    req = urllib.request.Request(url, headers={"Accept": "*/*", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        body = response.read()
        return body, response.headers.get("content-type", ""), response.geturl()


def json_shape(value: Any, depth: int = 0) -> Any:
    if depth >= 3:
        if isinstance(value, dict):
            return f"object[{len(value)}]"
        if isinstance(value, list):
            return f"list[{len(value)}]"
        return type(value).__name__
    if isinstance(value, dict):
        return {str(k): json_shape(v, depth + 1) for k, v in list(value.items())[:30]}
    if isinstance(value, list):
        return [] if not value else [json_shape(value[0], depth + 1), f"count={len(value)}"]
    return type(value).__name__


def safe(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    return parsed.scheme == "https" and parsed.hostname in ALLOWED_HOSTS


def inspect_json(url: str) -> None:
    try:
        body, content_type, final = fetch(url)
    except Exception as exc:
        print("JSON_FETCH_ERROR", json.dumps({"url": url, "error": repr(exc)}, ensure_ascii=False))
        return
    meta = {
        "url": url,
        "final_url": final,
        "content_type": content_type,
        "bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
    }
    try:
        value = json.loads(body)
    except Exception as exc:
        meta["parse_error"] = repr(exc)
        print("RESOURCE", json.dumps(meta, ensure_ascii=False))
        return
    meta["shape"] = json_shape(value)
    print("JSON_RESOURCE", json.dumps(meta, ensure_ascii=False)[:30000])


def crawl(name: str, root: str) -> None:
    print(f"\n=== {name} ===")
    queue: list[tuple[str, int]] = [(root, 0)]
    seen: set[str] = set()
    json_candidates: set[str] = set()

    while queue:
        url, depth = queue.pop(0)
        if url in seen or depth > 2 or not safe(url):
            continue
        seen.add(url)
        try:
            body, content_type, final = fetch(url)
        except Exception as exc:
            print("FETCH_ERROR", json.dumps({"url": url, "error": repr(exc)}, ensure_ascii=False))
            continue

        print("PAGE", json.dumps({
            "depth": depth,
            "url": url,
            "final_url": final,
            "content_type": content_type,
            "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
        }, ensure_ascii=False))

        if "json" in content_type.lower() or final.lower().split("?")[0].endswith(".json"):
            inspect_json(final)
            continue

        text = body.decode("utf-8", errors="replace")
        parser = Links()
        parser.feed(text)
        links: list[dict[str, str]] = []
        for href, label in parser.links:
            absolute = urllib.parse.urljoin(final, href)
            if not safe(absolute):
                continue
            links.append({"url": absolute, "text": label})
            low = absolute.lower().split("?")[0]
            if low.endswith(".json"):
                json_candidates.add(absolute)
            elif absolute.startswith(root) and absolute.endswith("/") and absolute != url:
                queue.append((absolute, depth + 1))

        print("LINKS", json.dumps(links, ensure_ascii=False)[:30000])

        # Directory index implementations sometimes render file names in text or
        # inline JavaScript rather than as ordinary links. Capture any literal
        # JSON path conservatively and resolve it against the current page.
        for match in re.finditer(r"[A-Za-z0-9_./%+\-]+\.json(?:\?[A-Za-z0-9_=&%+\-]*)?", text):
            candidate = urllib.parse.urljoin(final, match.group(0))
            if safe(candidate):
                json_candidates.add(candidate)

    print("JSON_CANDIDATES", json.dumps(sorted(json_candidates), ensure_ascii=False))
    for candidate in sorted(json_candidates):
        inspect_json(candidate)


def main() -> int:
    for name, root in ROOTS.items():
        crawl(name, root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
