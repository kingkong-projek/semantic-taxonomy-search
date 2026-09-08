#!/usr/bin/env python3
"""Generate a prefrozen source-bound A593 training-language diversity falsifier.

Opened 17/88 queries are never loaded. The old A593 teacher corpus is used only to
recover the frozen 593 concept IDs; its phrases are never sent to the model.

The script creates two independently generated corpora from canonical public v31
source evidence:
  1) additional lexically distant training descriptions;
  2) held-out user-like queries from a different prompt/call.

Both prompts are frozen in this file before generation. Generated text containing a
canonical/alternative title or any contiguous four-token source sequence is rejected.
Held-out queries additionally may not share a contiguous four-token sequence with the
new training descriptions for the same concept.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

MODEL = "gemma-4-26b-a4b-it"
TAXONOMY_URL = (
    "https://data.jobtechdev.se/taxonomy/version/31/query/"
    "concepts-and-common-relations/concepts-and-common-relations.json"
)
EXPECTED_A593 = 593
TOKEN_RE = re.compile(r"[0-9A-Za-zÅÄÖåäöÉéÜü]+", re.UNICODE)

TRAIN_KEYS = ("colloquial_first_person", "indirect_narrative", "elliptical_noisy", "concrete_work")
HOLDOUT_KEYS = ("shift_story", "plain_search", "compressed_note", "outcome_context")


def norm(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().casefold()


def tokens(text: Any) -> list[str]:
    return [m.group(0).casefold() for m in TOKEN_RE.finditer(str(text or ""))]


def ngrams(seq: list[str], n: int) -> set[tuple[str, ...]]:
    if len(seq) < n:
        return set()
    return {tuple(seq[i : i + n]) for i in range(len(seq) - n + 1)}


def has_fourgram_overlap(a: str, b: str) -> bool:
    return bool(ngrams(tokens(a), 4) & ngrams(tokens(b), 4))


def phrase_has_surface(text: str, surfaces: list[str]) -> bool:
    hay = f" {norm(text)} "
    for surface in surfaces:
        needle = norm(surface)
        if needle and f" {needle} " in hay:
            return True
    return False


def fetch_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "semantic-taxonomy-search-language-diversity/0.1"})
    with urllib.request.urlopen(req, timeout=120) as response:
        return response.read()


def expected_taxonomy_hash() -> str:
    registry = json.loads(Path("research/coverage/source-adapters.json").read_text(encoding="utf-8"))
    matches = [x for x in registry.get("adapters", []) if x.get("id") == "taxonomy-common-relations"]
    if len(matches) != 1:
        raise RuntimeError("taxonomy-common-relations source adapter missing/ambiguous")
    digest = str(matches[0].get("source_sha256") or "")
    if len(digest) != 64:
        raise RuntimeError("accepted taxonomy source hash missing")
    return digest


def clean_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
        elif isinstance(item, dict):
            for key in ("label", "name", "value"):
                text = item.get(key)
                if isinstance(text, str) and text.strip():
                    out.append(text.strip())
                    break
    return out


def source_evidence(concept: dict[str, Any]) -> dict[str, Any]:
    label = str(concept.get("preferred_label") or "").strip()
    definition = str(concept.get("definition") or "").strip()
    if norm(definition) == norm(label):
        definition = ""
    return {
        "canonical_label": label,
        "definition": definition,
        "alternative_labels": clean_list(concept.get("alternative_labels")),
    }


def evidence_rich(evidence: dict[str, Any]) -> bool:
    # The experiment is explicitly source-bound: thin label-only concepts should not
    # be used to manufacture user-language evidence.
    return len(tokens(evidence.get("definition"))) >= 18


def load_a593_ids(path: Path) -> list[str]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(rows) != EXPECTED_A593:
        raise RuntimeError(f"A593 teacher row drift: {len(rows)} != {EXPECTED_A593}")
    ids = [str(row.get("concept_id") or "") for row in rows]
    if any(not cid for cid in ids) or len(set(ids)) != EXPECTED_A593:
        raise RuntimeError("invalid/duplicate A593 concept IDs")
    return ids


def confusion_priority_ids(path: Path) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        contrast = row.get("contrast") or {}
        if not contrast.get("distinguishable"):
            continue
        for key in ("a_concept_id", "b_concept_id"):
            cid = str(row.get(key) or "")
            if cid and cid not in seen:
                seen.add(cid)
                out.append(cid)
    return out


def select_cases(a593_ids: list[str], by_id: dict[str, dict[str, Any]], cases: int) -> list[dict[str, Any]]:
    universe = set(a593_ids)
    priority = [cid for cid in confusion_priority_ids(Path("research/training/v31/a593-gemma4-sniper-contrasts-v0.jsonl")) if cid in universe]
    rich = [cid for cid in a593_ids if evidence_rich(source_evidence(by_id[cid]))]
    priority = [cid for cid in priority if cid in rich]
    priority_set = set(priority)
    rest = [cid for cid in rich if cid not in priority_set]
    rest.sort(key=lambda cid: hashlib.sha256(f"a593-language-diversity-v0:{cid}".encode()).hexdigest())
    ordered = priority + rest
    if len(ordered) < cases:
        raise RuntimeError(f"only {len(ordered)} source-rich A593 concepts available for requested {cases}")
    selected = []
    for index, cid in enumerate(ordered[:cases]):
        selected.append({
            "concept_id": cid,
            "selection_reason": "frozen_hard_confusion" if cid in priority_set else "stable_hash_source_rich",
            "selection_index": index,
            "evidence": source_evidence(by_id[cid]),
        })
    return selected


def training_prompt(batch: list[dict[str, Any]]) -> str:
    payload = [{"concept_id": x["concept_id"], "evidence": x["evidence"]} for x in batch]
    return f"""Du skapar SYNTHETISKT träningsspråk för semantisk sökning i en svensk offentlig yrkestaxonomi.

VIKTIG EVIDENSGRÄNS: använd endast fakta som stöds av EVIDENS för respektive koncept. Lägg aldrig till typiska arbetsuppgifter från allmän kunskap. Om evidensen inte räcker för en säker formulering, sätt den formuleringen till null. Hellre null än påhitt.

Syftet med denna körning är LEXIKAL DISTANS från taxonomitexten, inte fler omskrivningar som låter som en definition. En verklig användare känner inte yrkestiteln och skriver vad hen gör.

För varje koncept, skapa fyra korta svenska beskrivningar:
- colloquial_first_person: vardaglig jag-form, ungefär som till en kollega, 7–22 ord;
- indirect_narrative: beskriv situation/ansvar/resultat indirekt utan att låta som en yrkesdefinition, 8–28 ord;
- elliptical_noisy: komprimerad/fragmentarisk söktext, gärna talspråk eller en naturlig liten stav-/grammatikmiss, 4–16 ord;
- concrete_work: konkreta moment/objekt/verktyg/metoder/ansvar som evidensen uttryckligen stödjer, 6–24 ord.

Regler:
- använd INTE canonical_label eller alternative_labels, inte heller uppenbara böjningar av dem;
- kopiera INTE fyra eller fler ord i följd från definitionen;
- undvik fraser som bara säger hjälper/stödjer/jobbar med människor;
- använd olika ordval mellan de fyra formuleringarna;
- returnera endast JSON, inga förklaringar.

Format exakt:
{{"items":[{{"concept_id":"...","phrases":{{"colloquial_first_person":"... eller null","indirect_narrative":"... eller null","elliptical_noisy":"... eller null","concrete_work":"... eller null"}}}}]}}

EVIDENSBATCH:
{json.dumps(payload, ensure_ascii=False, sort_keys=True)}
"""


def holdout_prompt(batch: list[dict[str, Any]]) -> str:
    payload = [{"concept_id": x["concept_id"], "evidence": x["evidence"]} for x in batch]
    return f"""Du skriver FRISTÅENDE syntetiska sökfrågor för att testa en svensk yrkessökning. Dessa är testdata och får inte låta som taxonomins definitioner.

EVIDENSGRÄNS: använd endast fakta som explicit stöds av evidensen för respektive koncept. Använd inte allmän yrkeskunskap. Om en fråga inte går att skriva säkert från evidensen, sätt den till null.

Tänk att personen inte vet vad yrket heter. Skapa fyra olika sökfrågor per koncept:
- shift_story: en kort vardaglig händelse/sekvens från jobbet i jag-form, 10–30 ord;
- plain_search: det personen spontant skulle skriva i ett fritextfält om vad hen brukar göra, 6–20 ord;
- compressed_note: kort och ofullständig anteckningsstil, 4–14 ord;
- outcome_context: beskriver vad personen ansvarar för eller åstadkommer och i vilket arbetssammanhang, utan yrkestitel, 8–24 ord.

Regler:
- använd INTE canonical_label eller alternative_labels eller uppenbara böjningar;
- kopiera INTE fyra eller fler ord i följd från definitionen;
- försök använda vardagligare verb och annan meningsstruktur än källan;
- ingen markdown och ingen förklaring.

Format exakt:
{{"items":[{{"concept_id":"...","queries":{{"shift_story":"... eller null","plain_search":"... eller null","compressed_note":"... eller null","outcome_context":"... eller null"}}}}]}}

EVIDENSBATCH:
{json.dumps(payload, ensure_ascii=False, sort_keys=True)}
"""


def extract_json(payload: dict[str, Any]) -> dict[str, Any]:
    candidates = payload.get("candidates") or []
    if not candidates:
        raise RuntimeError("no candidates")
    parts = candidates[0].get("content", {}).get("parts") or []
    text = "".join(str(p.get("text") or "") for p in parts if isinstance(p, dict) and not p.get("thought")).strip()
    if not text:
        raise RuntimeError("no response text")
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid JSON response: {text[:500]!r}") from exc
    if not isinstance(value, dict):
        raise RuntimeError("response JSON must be object")
    return value


def call_json(api_key: str, prompt: str, *, temperature: float, max_attempts: int = 5) -> tuple[dict[str, Any], dict[str, Any]]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    body = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "thinkingConfig": {"thinkingLevel": "minimal"},
            "responseMimeType": "application/json",
            "temperature": temperature,
            "maxOutputTokens": 8192,
        },
    }, ensure_ascii=False).encode("utf-8")
    for attempt in range(max_attempts):
        req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json", "x-goog-api-key": api_key})
        try:
            with urllib.request.urlopen(req, timeout=180) as response:
                raw = json.load(response)
            return extract_json(raw), raw.get("usageMetadata") or {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            if exc.code != 429 and not (500 <= exc.code < 600):
                raise RuntimeError(f"Gemma HTTP {exc.code}: {detail}") from exc
            if attempt + 1 >= max_attempts:
                raise RuntimeError(f"Gemma HTTP {exc.code} after retries: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
            if attempt + 1 >= max_attempts:
                raise
        delay = min(60.0, 2.0 ** attempt) + random.uniform(0, 1)
        print(f"transient/invalid response; retry in {delay:.1f}s", flush=True)
        time.sleep(delay)
    raise AssertionError("unreachable")


def parse_batch(value: dict[str, Any], batch: list[dict[str, Any]], field: str, keys: tuple[str, ...]) -> dict[str, dict[str, str | None]]:
    expected = {x["concept_id"] for x in batch}
    items = value.get("items")
    if not isinstance(items, list):
        raise RuntimeError("response items missing")
    out: dict[str, dict[str, str | None]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        cid = str(item.get("concept_id") or "")
        values = item.get(field)
        if cid not in expected or cid in out or not isinstance(values, dict):
            continue
        current: dict[str, str | None] = {}
        for key in keys:
            raw = values.get(key)
            current[key] = str(raw).strip() if isinstance(raw, str) and raw.strip() else None
        out[cid] = current
    if set(out) != expected:
        missing = sorted(expected - set(out))
        raise RuntimeError(f"response concept mismatch, missing={missing[:5]} count={len(missing)}")
    return out


def validate_texts(row: dict[str, Any], generated: dict[str, str | None], *, training_texts: list[str] | None = None) -> tuple[dict[str, str | None], dict[str, Any]]:
    evidence = row["evidence"]
    source = " ".join([evidence.get("definition") or "", *(evidence.get("alternative_labels") or [])])
    surfaces = [evidence.get("canonical_label") or "", *(evidence.get("alternative_labels") or [])]
    accepted: dict[str, str | None] = {}
    rejected = {"title_surface": 0, "source_fourgram": 0, "training_fourgram": 0}
    for key, text in generated.items():
        if not text:
            accepted[key] = None
            continue
        if phrase_has_surface(text, surfaces):
            rejected["title_surface"] += 1
            accepted[key] = None
            continue
        if has_fourgram_overlap(text, source):
            rejected["source_fourgram"] += 1
            accepted[key] = None
            continue
        if training_texts and any(has_fourgram_overlap(text, train) for train in training_texts):
            rejected["training_fourgram"] += 1
            accepted[key] = None
            continue
        accepted[key] = text
    usable_count = sum(bool(x) for x in accepted.values())
    return accepted, {"usable_count": usable_count, "rejected": rejected}


def batched(values: list[dict[str, Any]], n: int):
    for i in range(0, len(values), n):
        yield values[i : i + n]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--teacher", required=True)
    ap.add_argument("--cases", type=int, default=150)
    ap.add_argument("--batch-size", type=int, default=12)
    ap.add_argument("--requests-per-minute", type=float, default=6.0)
    ap.add_argument("--training-output", default="artifacts/a593-language-diversity-training-v0.jsonl")
    ap.add_argument("--holdout-output", default="artifacts/a593-language-diversity-holdout-v0.jsonl")
    ap.add_argument("--summary", default="artifacts/a593-language-diversity-generation-v0.json")
    args = ap.parse_args()
    if not (40 <= args.cases <= 250):
        raise RuntimeError("cases must be 40..250")
    if not (4 <= args.batch_size <= 16):
        raise RuntimeError("batch-size must be 4..16")
    if not (0.5 <= args.requests_per_minute <= 6.0):
        raise RuntimeError("requests-per-minute must be 0.5..6")
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY missing")

    taxonomy_wire = fetch_bytes(TAXONOMY_URL)
    actual_hash = hashlib.sha256(taxonomy_wire).hexdigest()
    expected_hash = expected_taxonomy_hash()
    if actual_hash != expected_hash:
        raise RuntimeError(f"taxonomy source drift: {actual_hash} != {expected_hash}")
    taxonomy = json.loads(taxonomy_wire)
    concepts = taxonomy.get("data", {}).get("concepts") or []
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}
    active = {cid for cid, c in by_id.items() if c.get("type") == "occupation-name"}
    if len(active) != 2105:
        raise RuntimeError(f"active occupation universe drift: {len(active)}")

    a593_ids = load_a593_ids(Path(args.teacher))
    if any(cid not in active for cid in a593_ids):
        raise RuntimeError("A593 contains inactive/non-occupation ID")
    selected = select_cases(a593_ids, by_id, args.cases)

    interval = 60.0 / args.requests_per_minute
    last_call = 0.0
    training_raw: dict[str, dict[str, str | None]] = {}
    holdout_raw: dict[str, dict[str, str | None]] = {}
    usage = {"training": [], "holdout": []}

    def rate_limit():
        nonlocal last_call
        elapsed = time.time() - last_call
        if last_call and elapsed < interval:
            time.sleep(interval - elapsed)
        last_call = time.time()

    for batch_index, batch in enumerate(batched(selected, args.batch_size), 1):
        rate_limit()
        print(f"training batch {batch_index}: {len(batch)} concepts", flush=True)
        value, meta = call_json(api_key, training_prompt(batch), temperature=0.55)
        training_raw.update(parse_batch(value, batch, "phrases", TRAIN_KEYS))
        usage["training"].append(meta)

    for batch_index, batch in enumerate(batched(selected, args.batch_size), 1):
        rate_limit()
        print(f"holdout batch {batch_index}: {len(batch)} concepts", flush=True)
        value, meta = call_json(api_key, holdout_prompt(batch), temperature=0.7)
        holdout_raw.update(parse_batch(value, batch, "queries", HOLDOUT_KEYS))
        usage["holdout"].append(meta)

    training_rows = []
    holdout_rows = []
    jointly_usable = 0
    for row in selected:
        cid = row["concept_id"]
        train, train_diag = validate_texts(row, training_raw[cid])
        train_texts = [x for x in train.values() if x]
        hold, hold_diag = validate_texts(row, holdout_raw[cid], training_texts=train_texts)
        train_usable = train_diag["usable_count"] >= 3
        hold_usable = hold_diag["usable_count"] >= 3
        jointly_usable += int(train_usable and hold_usable)
        common = {
            "concept_id": cid,
            "label": row["evidence"]["canonical_label"],
            "selection_index": row["selection_index"],
            "selection_reason": row["selection_reason"],
            "source_evidence": row["evidence"],
            "model": MODEL,
            "taxonomy_sha256": actual_hash,
        }
        training_rows.append({
            **common,
            "phrases": train,
            "usable": train_usable,
            "validation": train_diag,
            "provenance": "separate source-bound Gemma language-diversity training call; no old A593 phrases or opened 17/88",
        })
        holdout_rows.append({
            **common,
            "queries": hold,
            "usable": hold_usable,
            "validation": hold_diag,
            "provenance": "separate source-bound Gemma held-out query call; no old A593 phrases or opened 17/88; fourgram-separated from new training phrases",
        })

    if jointly_usable < max(80, round(args.cases * 0.70)):
        raise RuntimeError(f"too few jointly usable concepts: {jointly_usable}/{args.cases}")

    train_path = Path(args.training_output)
    hold_path = Path(args.holdout_output)
    summary_path = Path(args.summary)
    for path in (train_path, hold_path, summary_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    train_path.write_text("".join(json.dumps(x, ensure_ascii=False, sort_keys=True) + "\n" for x in training_rows), encoding="utf-8")
    hold_path.write_text("".join(json.dumps(x, ensure_ascii=False, sort_keys=True) + "\n" for x in holdout_rows), encoding="utf-8")
    summary = {
        "id": "YV-A593-language-diversity-generation-v0",
        "model": MODEL,
        "requested_concepts": args.cases,
        "jointly_usable_concepts": jointly_usable,
        "selection": {
            "priority": "all source-rich concepts in frozen distinguishable A593 confusion pairs first",
            "remainder": "stable SHA256 order among source-rich A593 concepts",
            "opened_outcomes_used": false,
        },
        "generation": {
            "batch_size": args.batch_size,
            "requests_per_minute_cap": args.requests_per_minute,
            "training_temperature": 0.55,
            "holdout_temperature": 0.7,
            "old_a593_teacher_phrases_sent_to_model": false,
            "opened_17_88_loaded": false,
            "validation": "reject title surfaces, source fourgrams, and holdout/new-training fourgram overlap",
        },
        "taxonomy_sha256": actual_hash,
        "training_sha256": hashlib.sha256(train_path.read_bytes()).hexdigest(),
        "holdout_sha256": hashlib.sha256(hold_path.read_bytes()).hexdigest(),
        "usage_metadata": usage,
        "evidence_warning": "Synthetic/model-authored source-bound architecture evidence only; not human accuracy.",
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "usage_metadata"}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
