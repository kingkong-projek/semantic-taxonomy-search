#!/usr/bin/env python3
"""Discover the actual published Occupational Information interim distribution.

The catalog page currently renders a download control without an anchor/JSON-LD
URL in server HTML. This probe therefore records HTML attributes and follows the
page's own same-origin JavaScript assets looking for explicit distribution/API
references. It never guesses a data-file path.
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
ORIGIN = "https://data.arbetsformedlingen.se/"
UA = "semantic-taxonomy-search-occupational-info-probe/0.2"


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self.scripts: list[str] = []
        self.attrs: list[dict[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []
        self.jsonld: list[str] = []
        self._jsonld = False
        self._jsonld_buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_d = {str(k): str(v) for k, v in attrs if v is not None}
        if attrs_d:
            self.attrs.append({"tag": tag, **attrs_d})
        if tag == "a" and attrs_d.get("href"):
            self._href = attrs_d["href"]
            self._text = []
        if tag == "script" and attrs_d.get("src"):
            self.scripts.append(attrs_d["src"])
        if tag == "script" and attrs_d.get("type", "").lower() == "application/ld+json":
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
        return r.read(), r.geturl(), str(r.headers.get("Content-Type") or ""), int(r.status)


def walk_urls(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for k, v in value.items():
            if isinstance(v, str) and (
                k.lower() in {"contenturl", "downloadurl", "accessurl", "url"}
                or v.lower().endswith(".json")
            ):
                found.append(v)
            found.extend(walk_urls(v))
    elif isinstance(value, list):
        for v in value:
            found.extend(walk_urls(v))
    return found


def snippets(text: str, patterns: tuple[str, ...], radius: int = 180) -> list[str]:
    lower = text.lower()
    hits: list[str] = []
    seen: set[str] = set()
    for pattern in patterns:
        start = 0
        p = pattern.lower()
        while True:
            idx = lower.find(p, start)
            if idx < 0:
                break
            snippet = " ".join(text[max(0, idx-radius): min(len(text), idx+len(p)+radius)].split())
            if snippet not in seen:
                seen.add(snippet)
                hits.append(snippet)
            start = idx + len(p)
            if len(hits) >= 80:
                return hits
    return hits


def candidate_strings(text: str) -> set[str]:
    values: set[str] = set()
    for url in re.findall(r'https?://[^"\'<>\\\s)]+', text):
        values.add(url.replace("&amp;", "&"))
    for path in re.findall(r'["\']([^"\']*(?:\.json|/api/|distribution|download)[^"\']*)["\']', text, flags=re.I):
        values.add(path)
    return values


def inspect_url(url: str, origin: str, label: str = "") -> dict[str, Any]:
    rec: dict[str, Any] = {"url": url, "origin": origin, "label": label}
    try:
        body, final, ctype, status = fetch(url)
        rec.update({
            "status": status,
            "final_url": final,
            "content_type": ctype,
            "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
            "looks_json": body.lstrip().startswith((b"{", b"[")),
            "prefix": body[:250].decode("utf-8", errors="replace"),
        })
        if rec["looks_json"]:
            try:
                parsed = json.loads(body)
                rec["json_top_type"] = type(parsed).__name__
                rec["json_top_keys"] = sorted(parsed.keys()) if isinstance(parsed, dict) else None
                if isinstance(parsed, dict) and isinstance(parsed.get("metadata"), dict):
                    rec["metadata"] = parsed["metadata"]
            except Exception as exc:
                rec["json_parse_error"] = repr(exc)
    except Exception as exc:
        rec["fetch_error"] = repr(exc)
    return rec


def main() -> int:
    body, final_url, content_type, status = fetch(PAGE, "text/html,application/xhtml+xml")
    text = body.decode("utf-8", errors="replace")
    parser = PageParser()
    parser.feed(text)

    explicit: dict[str, dict[str, str]] = {}
    for href, label in parser.links:
        absolute = urllib.parse.urljoin(final_url, href)
        if absolute.startswith(ORIGIN):
            explicit[absolute] = {"origin": "html_anchor", "label": label}

    jsonld_errors: list[str] = []
    for raw in parser.jsonld:
        try:
            obj = json.loads(raw)
        except Exception as exc:
            jsonld_errors.append(repr(exc))
            continue
        for value in walk_urls(obj):
            absolute = urllib.parse.urljoin(final_url, value)
            if absolute.startswith(ORIGIN):
                explicit.setdefault(absolute, {"origin": "json_ld", "label": ""})

    for value in candidate_strings(text):
        absolute = urllib.parse.urljoin(final_url, value)
        if absolute.startswith(ORIGIN):
            explicit.setdefault(absolute, {"origin": "html_literal_or_attribute", "label": ""})

    asset_findings: list[dict[str, Any]] = []
    asset_candidates: dict[str, str] = {}
    for src in parser.scripts:
        asset_url = urllib.parse.urljoin(final_url, src)
        if not asset_url.startswith(ORIGIN):
            continue
        try:
            asset_body, asset_final, asset_type, asset_status = fetch(asset_url)
            asset_text = asset_body.decode("utf-8", errors="replace")
            hits = snippets(asset_text, ("distribution", "download", "dataset", "occupational", "yrkesinformation", ".json", "/api/"), 220)
            asset_findings.append({
                "url": asset_url,
                "final_url": asset_final,
                "status": asset_status,
                "content_type": asset_type,
                "bytes": len(asset_body),
                "sha256": hashlib.sha256(asset_body).hexdigest(),
                "interesting_snippets": hits[:30],
            })
            for value in candidate_strings(asset_text):
                absolute = urllib.parse.urljoin(asset_final, value)
                if absolute.startswith(ORIGIN):
                    asset_candidates.setdefault(absolute, asset_url)
        except Exception as exc:
            asset_findings.append({"url": asset_url, "fetch_error": repr(exc)})

    for absolute, asset_url in asset_candidates.items():
        explicit.setdefault(absolute, {"origin": f"script_asset:{asset_url}", "label": ""})

    candidates = []
    for url, meta in sorted(explicit.items()):
        lower = url.lower()
        if not any(x in lower for x in (".json", "occupational", "yrkesinformation", "distribution", "download", "/api/")):
            continue
        candidates.append(inspect_url(url, meta["origin"], meta.get("label", "")))

    interesting_attrs = [
        a for a in parser.attrs
        if any(
            token in " ".join(f"{k}={v}" for k, v in a.items()).lower()
            for token in ("download", "distribution", "occupational", "yrkesinformation", ".json", "dataset", "api")
        )
    ]

    result = {
        "schema_version": 2,
        "catalog_page": {
            "url": PAGE,
            "final_url": final_url,
            "status": status,
            "content_type": content_type,
            "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
            "interesting_snippets": snippets(text, ("distribution", "download", "occupational", "yrkesinformation", ".json", "dataset", "api"), 220),
        },
        "html_links": [{"href": h, "label": t} for h, t in parser.links],
        "interesting_html_attributes": interesting_attrs,
        "script_sources": parser.scripts,
        "script_asset_findings": asset_findings,
        "json_ld_blocks": len(parser.jsonld),
        "json_ld_errors": jsonld_errors,
        "candidate_distributions": candidates,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
