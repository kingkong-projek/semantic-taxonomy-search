#!/usr/bin/env python3
"""Resolve distribution access URLs from Arbetsförmedlingen's public DCAT metadata.

Unlike catalogue landing pages, the public metadata repository contains the
actual `distribution.accessURL`. This probe records those URLs and inspects the
first response so dedicated coverage adapters can be written against verified
sources instead of guessed filenames.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Any

USER_AGENT = "semantic-taxonomy-search-metadata-probe/0.1"
RAW_BASE = "https://gitlab.com/arbetsformedlingen/www/data-jobtechdev-se/metadata/-/raw/main"
FILES = {
    "yrkesvaljaren": "yrkesvaljaren.json",
    "relevant-skills": "relevanta_kompetenser.json",
    "skill-selector": "kompetensvaljaren.json",
    "nearby-occupations": "narliggandeyrken.json",
    "occupational-information": "yrkesinformation.json",
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


def fetch(url: str, timeout: int = 120) -> tuple[int, dict[str, str], bytes, str]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return (
            response.status,
            {k.lower(): v for k, v in response.headers.items()},
            response.read(),
            response.geturl(),
        )


def shape(value: Any, depth: int = 0) -> Any:
    if depth >= 4:
        if isinstance(value, list):
            return f"list[{len(value)}]"
        if isinstance(value, dict):
            return f"object[{len(value)}]"
        return type(value).__name__
    if isinstance(value, dict):
        return {k: shape(v, depth + 1) for k, v in list(value.items())[:40]}
    if isinstance(value, list):
        return [] if not value else [shape(value[0], depth + 1), f"count={len(value)}"]
    return type(value).__name__


def access_urls(distribution: Any) -> list[str]:
    items = distribution if isinstance(distribution, list) else [distribution]
    result: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        value = item.get("accessURL") or item.get("downloadURL")
        if isinstance(value, str):
            result.append(value.strip())
        elif isinstance(value, list):
            result.extend(str(v).strip() for v in value if v)
    return list(dict.fromkeys(result))


def inspect_access(url: str) -> None:
    print("ACCESS_URL", url)
    try:
        status, headers, body, final_url = fetch(url)
    except Exception as exc:
        print("ACCESS_ERROR", repr(exc))
        return
    content_type = headers.get("content-type", "")
    print(
        "ACCESS_META",
        json.dumps(
            {
                "status": status,
                "final_url": final_url,
                "content_type": content_type,
                "bytes": len(body),
                "sha256": hashlib.sha256(body).hexdigest(),
            },
            ensure_ascii=False,
        ),
    )
    if "json" in content_type or final_url.lower().endswith(".json"):
        try:
            value = json.loads(body)
            print("JSON_SHAPE", json.dumps(shape(value), ensure_ascii=False)[:30000])
            if isinstance(value, dict):
                for key in ("title", "version", "labour_market_taxonomy_version", "data_created", "$schema"):
                    if key in value:
                        print("JSON_META", key, json.dumps(value[key], ensure_ascii=False))
        except Exception as exc:
            print("JSON_PARSE_ERROR", repr(exc))
    elif "html" in content_type:
        parser = Links()
        parser.feed(body.decode("utf-8", errors="replace"))
        candidates: list[tuple[str, str]] = []
        for href, text in parser.items:
            absolute = urllib.parse.urljoin(final_url, href)
            haystack = f"{absolute} {text}".lower()
            if any(token in haystack for token in (".json", ".zip", ".csv", "schema", "latest", "version")):
                candidates.append((absolute, text))
        for absolute, text in candidates[:100]:
            print("ACCESS_LINK", json.dumps({"url": absolute, "text": text}, ensure_ascii=False))
        # Raw strings can be embedded in JS/JSON rather than anchors.
        decoded = body.decode("utf-8", errors="replace")
        raw_urls = sorted(set(re.findall(r'https?://[^"\'<>\\\s]+', decoded)))
        for candidate in raw_urls:
            if any(token in candidate.lower() for token in (".json", ".zip", ".csv", "jobtech", "taxonomy")):
                print("EMBEDDED_URL", candidate[:1000])


def main() -> int:
    for name, filename in FILES.items():
        print(f"\n=== {name} ===")
        metadata_url = f"{RAW_BASE}/{filename}"
        print("METADATA_URL", metadata_url)
        try:
            status, headers, body, final_url = fetch(metadata_url)
        except Exception as exc:
            print("METADATA_ERROR", repr(exc))
            continue
        print(
            "METADATA_META",
            json.dumps(
                {
                    "status": status,
                    "final_url": final_url,
                    "bytes": len(body),
                    "sha256": hashlib.sha256(body).hexdigest(),
                }
            ),
        )
        try:
            document = json.loads(body)
        except Exception as exc:
            print("METADATA_PARSE_ERROR", repr(exc))
            continue
        dataset = document.get("dcat-dataset", document) if isinstance(document, dict) else {}
        if not isinstance(dataset, dict):
            print("METADATA_SHAPE_ERROR")
            continue
        print(
            "DCAT",
            json.dumps(
                {
                    key: dataset.get(key)
                    for key in ("title-sv", "versionInfo", "issued", "modified", "landingPage", "accrualPeriodicity")
                },
                ensure_ascii=False,
            ),
        )
        urls = access_urls(dataset.get("distribution"))
        print("DISTRIBUTION_URLS", json.dumps(urls, ensure_ascii=False))
        for url in urls:
            inspect_access(url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
