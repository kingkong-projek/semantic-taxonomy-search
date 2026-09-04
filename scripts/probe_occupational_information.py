#!/usr/bin/env python3
"""Discover the actual published Occupational Information interim distribution.

This is deliberately a discovery probe, not a coverage adapter. The catalog page
has previously exposed anomalous metadata, so we only follow links explicitly
present in the fetched HTML/JSON-LD and report redirects/content hashes before
any semantic use is accepted.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Any

PAGE = "https://data.arbetsformedlingen.se/dataset/occupational-information-interim-solution/"
UA = "semantic-taxonomy-search-occupational-info-probe/0.1"


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []
        self.jsonld: list[str] = []
        self._jsonld = False
        self._jsonld_buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_d = dict(attrs)
        if tag == "a" and attrs_d.get("href"):
            self._href = str(attrs_d["href"])
            self._text = []
        if tag == "script" and str(attrs_d.get("type") or "").lower() == "application/ld+json":
            self._jsonld = True
            self._jsonld_buf = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)
        if self._jsonld:
            self._jsonld_buf.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join("".join(self._text).split())))
            self._href = None
            self._text = []
        if tag == "script" and self._jsonld:
            self.jsonld.append("".join(self._jsonld_buf))
            self._jsonld = False
            self._jsonld_buf = []


def fetch(url: str, accept: str = "*/*") -> tuple[bytes, str, str, int]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    with urllib.request.urlopen(req, timeout=120) as r:
        body = r.read()
        return body, r.geturl(), str(r.headers.get("Content-Type") or ""), int(r.status)


def walk_json_urls(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for k, v in value.items():
            if isinstance(v, str) and (
                k.lower() in {"contenturl", "downloadurl", "accessurl", "url"}
                or v.lower().endswith(".json")
            ):
                found.append(v)
            found.extend(walk_json_urls(v))
    elif isinstance(value, list):
        for v in value:
            found.extend(walk_json_urls(v))
    return found


def main() -> int:
    body, final_url, content_type, status = fetch(PAGE, "text/html,application/xhtml+xml")
    text = body.decode("utf-8", errors="replace")
    parser = LinkParser()
    parser.feed(text)

    explicit: dict[str, dict[str, str]] = {}
    for href, label in parser.links:
        absolute = urllib.parse.urljoin(final_url, href)
        if absolute.startswith("https://data.arbetsformedlingen.se/"):
            explicit[absolute] = {"origin": "html_anchor", "label": label}

    jsonld_errors: list[str] = []
    for raw in parser.jsonld:
        try:
            obj = json.loads(raw)
        except Exception as exc:  # probe: retain malformed metadata fact
            jsonld_errors.append(repr(exc))
            continue
        for candidate in walk_json_urls(obj):
            absolute = urllib.parse.urljoin(final_url, candidate)
            if absolute.startswith("https://data.arbetsformedlingen.se/"):
                explicit.setdefault(absolute, {"origin": "json_ld", "label": ""})

    # Also report absolute URLs literally embedded in page source, but mark them
    # separately. This catches generated download controls without inventing paths.
    for candidate in re.findall(r'https://data\.arbetsformedlingen\.se/[^"\'<>\\\s]+', text):
        candidate = candidate.replace("&amp;", "&")
        explicit.setdefault(candidate, {"origin": "literal_html_url", "label": ""})

    candidates = []
    for url, meta in sorted(explicit.items()):
        lower = url.lower()
        interesting = (
            lower.endswith(".json")
            or "occupational" in lower
            or "yrkesinformation" in lower
            or "distribution" in lower
            or "download" in lower
        )
        if not interesting:
            continue
        record: dict[str, Any] = {"url": url, **meta}
        try:
            candidate_body, candidate_final, candidate_type, candidate_status = fetch(url)
            record.update({
                "status": candidate_status,
                "final_url": candidate_final,
                "content_type": candidate_type,
                "bytes": len(candidate_body),
                "sha256": hashlib.sha256(candidate_body).hexdigest(),
                "looks_json": candidate_body.lstrip().startswith((b"{", b"[")),
                "prefix": candidate_body[:300].decode("utf-8", errors="replace"),
            })
            if record["looks_json"]:
                try:
                    parsed = json.loads(candidate_body)
                    record["json_top_type"] = type(parsed).__name__
                    record["json_top_keys"] = sorted(parsed.keys()) if isinstance(parsed, dict) else None
                    if isinstance(parsed, dict) and isinstance(parsed.get("metadata"), dict):
                        record["metadata"] = parsed["metadata"]
                except Exception as exc:
                    record["json_parse_error"] = repr(exc)
        except Exception as exc:
            record["fetch_error"] = repr(exc)
        candidates.append(record)

    result = {
        "schema_version": 1,
        "catalog_page": {
            "url": PAGE,
            "final_url": final_url,
            "status": status,
            "content_type": content_type,
            "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
        },
        "html_links": [{"href": h, "label": t} for h, t in parser.links],
        "json_ld_blocks": len(parser.jsonld),
        "json_ld_errors": jsonld_errors,
        "candidate_distributions": candidates,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
