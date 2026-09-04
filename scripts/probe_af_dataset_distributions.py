#!/usr/bin/env python3
"""Discover Arbetsförmedlingen dataset distribution/file-area links and schemas.

The open-data catalogue renders distribution labels without always exposing the
actual file URL in text-oriented clients. This diagnostic fetches the public
HTML directly, records every link, follows likely distribution/file-area links
and prints the first-level shape of JSON resources or directory listings.

It is a research probe, not a production source adapter. Once a stable source
URL/schema is verified, that URL belongs in `research/coverage/source-adapters.json`
and a dedicated adapter should be written against it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Any

USER_AGENT = "semantic-taxonomy-search-distribution-probe/0.1"

DEFAULT_DATASETS = {
    "yrkesvaljaren": "https://data.arbetsformedlingen.se/dataset/occupation-suggester/",
    "relevant-skills": "https://data.arbetsformedlingen.se/dataset/relevant-skills/",
    "skill-selector": "https://data.arbetsformedlingen.se/dataset/skill-selector/",
    "nearby-occupations": "https://data.arbetsformedlingen.se/dataset/related-occupations/",
    "occupational-information": "https://data.arbetsformedlingen.se/dataset/occupational-information-interim-solution/",
}


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attrs_dict = dict(attrs)
        self._href = attrs_dict.get("href")
        self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href is not None:
            text = re.sub(r"\s+", " ", " ".join(self._text)).strip()
            self.links.append((self._href, text))
            self._href = None
            self._text = []


def fetch(url: str, timeout: int = 90) -> tuple[int, dict[str, str], bytes, str]:
    request = urllib.request.Request(
        url,
        headers={"Accept": "*/*", "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read()
        headers = {k.lower(): v for k, v in response.headers.items()}
        return response.status, headers, body, response.geturl()


def json_shape(value: Any, depth: int = 0) -> Any:
    if depth >= 3:
        if isinstance(value, list):
            return f"list[{len(value)}]"
        if isinstance(value, dict):
            return f"object[{len(value)}]"
        return type(value).__name__
    if isinstance(value, dict):
        return {str(k): json_shape(v, depth + 1) for k, v in list(value.items())[:25]}
    if isinstance(value, list):
        if not value:
            return []
        return [json_shape(value[0], depth + 1), f"count={len(value)}"]
    return type(value).__name__


def candidate_score(url: str, text: str) -> int:
    haystack = f"{url} {text}".casefold()
    score = 0
    for token, weight in (
        ("data.jobtechdev.se", 8),
        (".json", 8),
        ("file", 3),
        ("filyta", 4),
        ("download", 3),
        ("distribution", 2),
        ("dataset", 1),
    ):
        if token in haystack:
            score += weight
    return score


def probe_dataset(name: str, page_url: str) -> None:
    print(f"\n=== DATASET {name} ===")
    print("page", page_url)
    try:
        status, headers, body, final_url = fetch(page_url)
    except Exception as exc:
        print("PAGE_ERROR", repr(exc))
        return

    print("page_status", status)
    print("page_final_url", final_url)
    print("page_content_type", headers.get("content-type"))
    print("page_sha256", hashlib.sha256(body).hexdigest())

    parser = LinkParser()
    parser.feed(body.decode("utf-8", errors="replace"))
    resolved: list[tuple[int, str, str]] = []
    for href, text in parser.links:
        absolute = urllib.parse.urljoin(final_url, href)
        resolved.append((candidate_score(absolute, text), absolute, text))

    # Print all non-navigation links with the most source-like links first.
    dedup: dict[str, tuple[int, str]] = {}
    for score, url, text in resolved:
        previous = dedup.get(url)
        if previous is None or score > previous[0]:
            dedup[url] = (score, text)

    ranked = sorted(
        ((score, url, text) for url, (score, text) in dedup.items()),
        key=lambda x: (-x[0], x[1]),
    )
    for score, url, text in ranked[:40]:
        if score > 0 or "arbetsformedlingen.se" not in urllib.parse.urlparse(url).netloc:
            print("link", json.dumps({"score": score, "url": url, "text": text}, ensure_ascii=False))

    candidates = [item for item in ranked if item[0] >= 5][:8]
    for score, url, text in candidates:
        print("FOLLOW", json.dumps({"score": score, "url": url, "text": text}, ensure_ascii=False))
        try:
            child_status, child_headers, child_body, child_final = fetch(url, timeout=120)
        except Exception as exc:
            print("FOLLOW_ERROR", url, repr(exc))
            continue
        content_type = child_headers.get("content-type", "")
        print(
            "FOLLOW_META",
            json.dumps(
                {
                    "status": child_status,
                    "final_url": child_final,
                    "content_type": content_type,
                    "bytes": len(child_body),
                    "sha256": hashlib.sha256(child_body).hexdigest(),
                },
                ensure_ascii=False,
            ),
        )
        if "json" in content_type or child_final.lower().endswith(".json"):
            try:
                value = json.loads(child_body)
                print("JSON_SHAPE", json.dumps(json_shape(value), ensure_ascii=False)[:20000])
            except Exception as exc:
                print("JSON_PARSE_ERROR", repr(exc))
        elif "html" in content_type:
            child_parser = LinkParser()
            child_parser.feed(child_body.decode("utf-8", errors="replace"))
            child_links = []
            for href, link_text in child_parser.links:
                absolute = urllib.parse.urljoin(child_final, href)
                score2 = candidate_score(absolute, link_text)
                if score2 >= 5 or absolute.lower().endswith((".json", ".zip", ".csv")):
                    child_links.append((score2, absolute, link_text))
            for score2, absolute, link_text in sorted(child_links, key=lambda x: (-x[0], x[1]))[:40]:
                print(
                    "CHILD_LINK",
                    json.dumps({"score": score2, "url": absolute, "text": link_text}, ensure_ascii=False),
                )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", action="append", choices=sorted(DEFAULT_DATASETS))
    args = parser.parse_args()
    names = args.dataset or list(DEFAULT_DATASETS)
    for name in names:
        probe_dataset(name, DEFAULT_DATASETS[name])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
