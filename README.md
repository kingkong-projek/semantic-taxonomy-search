# Semantic Taxonomy Search

Research and implementation workspace for reusable semantic retrieval over Arbetsförmedlingen's Labour Market Taxonomy.

The goal is a general capability for services where users need to identify or select **occupations** and **skills/competences** without knowing the taxonomy's exact wording. Yrkesväljaren (YV), Kompetensväljaren (KV), JobSearch/Platsbanken query data and other AF datasets are reference products and evidence sources; they do not define the scope of the semantic retrieval core.

The core returns canonical taxonomy identities and keeps consumer-specific admission rules separate. A consuming service may therefore use the same retrieval engine while deciding independently which occupation/skill identities are selectable in that product.

The repository is the single source of truth for the problem definition, evidence inventory, experiments, evaluation protocol and implementation decisions.

## Demo

`demo/` contains a zero-backend research prototype for both `Beskriv ditt yrke` and `Beskriv din kompetens`. The tester can use the same work description against either destination. Each deterministic retrieval asset is lazy-loaded separately and search runs locally in the browser. Test feedback from both streams stays local until the tester explicitly exports one JSON file.

The occupation path packages the frozen YV **`YV-description-full-v0-canonical-router`** candidate over all 2,105 active v31 occupation-name identities, with exact active job-title → typed occupation-parent routing. Unpromoted AF ad-language and Relevanta-kompetenser lanes are not active in the demo. The skill path packages the frozen KV **G1+T3** retriever. Packaging/runtime parity is checked in CI and does not create new validation evidence.

The demo is a **research prototype, not an official Arbetsförmedlingen service or publication**.

## Data, provenance and third-party material

The Arbetsförmedlingen datasets used by the current demo are published as **Creative Commons CC0 1.0**. Exact research-source URLs and accepted hashes are tracked in `research/coverage/source-adapters.json`.

See:

- [`DATA_SOURCES_AND_LICENSES.md`](DATA_SOURCES_AND_LICENSES.md) — data sources, provenance and reuse terms.
- [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) — third-party software/design material, including Arbetsförmedlingen Designsystem (Apache-2.0).

## License

This project's own code and documentation are licensed under the [Apache License 2.0](LICENSE), unless a file or third-party notice states otherwise. External datasets and third-party material retain the terms documented above.

## Research plan

Start with [`docs/research-plan.md`](docs/research-plan.md).
