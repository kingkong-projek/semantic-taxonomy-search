# Typed ESCO coverage on the validated KV G1 residual — v31

**Status:** coverage diagnostic only; no ESCO ranking/fusion change.

The three remaining `KV-G1-4slot` second-holdout misses were inspected against the pinned v31 `exact_match`, `close_match`, `broad_match` and `narrow_match` relations. Mapping semantics remain separate.

## Kabelinstallationer

No exact ESCO match exists. There is one close match, `reparera ledningar`, whose definition explicitly covers locating faults in wires/cables with special equipment and repairing them. Eight narrower ESCO concepts include `skarva kabel`, `kabeltillbehör`, `skala kablar` and `kabelsele`.

This is useful language, but it sits behind weaker close/narrow semantics and multiple edges. It does not justify blanket document expansion.

## Städmaterial

There is one exact match: `rengöringsprodukter`.

Its definition states that the concept covers the ingredients used in cleaning products and their properties and risks. This is materially closer to the held-out phrase about *kemisk-tekniska produkter och dess användningsområden* than the current non-holdout training descriptions for `Städmaterial`.

Two narrower mappings — `använda lösningsmedel` and `se till att det finns en uppsättning städartiklar` — add further cleaning-material language.

This is the strongest evidence that a **separate typed ESCO candidate lane** could complement G1 for a genuine source-language gap. It is not evidence for reintroducing the previously rejected blanket exact-ESCO document expansion.

## Produktionsplanering, tillverkning

There is one exact match: `planera tillverkningsprocesser`, defined around planning production/assembly work, labour and equipment. Twenty-nine narrower concepts include `schemalägga produktion`, `delta i produktionsplanläggning` and `använda programvara för produktionsplanering`.

ESCO therefore represents the target domain well. The benchmark case nevertheless remains semantically close to the already surfaced `Produktionsteknik` and `Ständiga förbättringar/Lean`, both explicitly named by the query.

## Decision

Do not alter `KV-G1-4slot-single-desc` yet. The next experiment is only an **oracle/complement diagnostic**: build exact/close/broad/narrow ESCO BM25 lanes keyed back to AF skill identities and measure how often each lane independently recovers cases the validated G1 top-5 misses. No fusion policy is chosen in that experiment.

If the complement is negligible, stop the ESCO path. If it is material, only then compare a bounded fusion and require fresh independent validation before promotion.

Evidence: `research/evaluation/v31/skill-g1-residual-esco.json`; run `34061405681`, artifact `9997577903`.
