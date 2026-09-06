import unittest

from scripts.findability_authority import group_surface_rows_by_authority


def norm(value):
    return str(value or '').casefold().strip()


def row(provenance, target):
    return {
        'product': 'KV',
        'query': 'Mode',
        'surface_provenance': provenance,
        'target_type': 'skill',
        'target_id': target,
    }


class FindabilityAuthorityTest(unittest.TestCase):
    def test_current_canonical_alias_is_not_vetoed_by_conflicting_legacy_route(self):
        grouped = group_surface_rows_by_authority([
            row('canonical_alternative_label', 'current'),
            row('deprecated_unique_replacement_label', 'legacy-target'),
        ], norm)

        selected = grouped[('KV', 'mode')]
        self.assertEqual({r['target_id'] for r in selected}, {'current'})

    def test_same_target_legacy_evidence_may_corroborate_current_alias(self):
        grouped = group_surface_rows_by_authority([
            row('canonical_hidden_label', 'current'),
            row('deprecated_unique_replacement_label', 'current'),
        ], norm)

        selected = grouped[('KV', 'mode')]
        self.assertEqual(len(selected), 2)

    def test_current_canonical_ambiguity_remains_fail_closed(self):
        grouped = group_surface_rows_by_authority([
            row('canonical_alternative_label', 'a'),
            row('canonical_hidden_label', 'b'),
            row('deprecated_unique_replacement_label', 'a'),
        ], norm)

        selected = grouped[('KV', 'mode')]
        self.assertEqual({r['target_id'] for r in selected}, {'a', 'b'})
        self.assertTrue(all(r['surface_provenance'].startswith('canonical_') for r in selected))


if __name__ == '__main__':
    unittest.main()
