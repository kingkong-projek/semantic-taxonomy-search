from __future__ import annotations

import collections
from collections.abc import Callable, Iterable
from typing import Any

CANONICAL_ALIAS_PROVENANCE = {
    "canonical_alternative_label",
    "canonical_hidden_label",
}


def _target(row: dict[str, Any]) -> tuple[str, str]:
    return str(row.get("target_type") or ""), str(row.get("target_id") or "")


def group_surface_rows_by_authority(
    rows: Iterable[dict[str, Any]],
    normalize: Callable[[Any], str],
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """Group should-find surfaces without letting migration history veto current vocabulary.

    Current canonical alternative/hidden labels own a surface whenever they exist.
    Deprecated replacement labels may corroborate that same current target, but a
    conflicting deprecated route cannot suppress or redirect a current canonical alias.
    If current canonical aliases themselves point at multiple targets, the canonical
    ambiguity remains visible and the caller will fail closed.
    """
    raw: dict[tuple[str, str], list[dict[str, Any]]] = collections.defaultdict(list)
    for row in rows:
        raw[(str(row["product"]), normalize(row.get("query")))].append(row)

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for key, surface_rows in raw.items():
        canonical = [
            row
            for row in surface_rows
            if row.get("surface_provenance") in CANONICAL_ALIAS_PROVENANCE
        ]
        if not canonical:
            grouped[key] = surface_rows
            continue

        canonical_targets = {_target(row) for row in canonical}
        if len(canonical_targets) != 1:
            # Keep only the current ambiguity; legacy routes cannot make it safer.
            grouped[key] = canonical
            continue

        current_target = next(iter(canonical_targets))
        grouped[key] = [
            row
            for row in surface_rows
            if row in canonical or _target(row) == current_target
        ]

    return grouped
