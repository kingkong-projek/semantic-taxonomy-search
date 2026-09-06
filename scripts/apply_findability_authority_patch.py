from pathlib import Path

path = Path('scripts/build_findability_should_find_cases.py')
text = path.read_text(encoding='utf-8')

old_import = 'from deprecated_compatibility_coverage import as_strings, graphql, relation_ids, resolve_route\n'
new_import = old_import + 'from findability_authority import group_surface_rows_by_authority\n'
if 'from findability_authority import group_surface_rows_by_authority\n' not in text:
    if old_import not in text:
        raise SystemExit('expected import anchor missing')
    text = text.replace(old_import, new_import, 1)

old_group = '''    # Collision filter: a surface is decision-bearing only when all authoritative rows for
    # that product/surface route to the same target. Also do not call a current preferred
    # label a missing-vocabulary alias.
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = collections.defaultdict(list)
    for row in surfaces:
        grouped[(row["product"], norm(row["query"]))].append(row)
'''
new_group = '''    # Current canonical vocabulary outranks migration/history vocabulary. A conflicting
    # deprecated replacement route must not veto or redirect a current canonical alias.
    # Canonical ambiguity itself still fails closed.
    grouped = group_surface_rows_by_authority(surfaces, norm)
'''
if old_group in text:
    text = text.replace(old_group, new_group, 1)
elif new_group not in text:
    raise SystemExit('expected grouping anchor missing')

path.write_text(text, encoding='utf-8')
