# Semantic Taxonomy Search

Research and implementation workspace for reusable semantic retrieval over Arbetsförmedlingen's Labour Market Taxonomy.

The goal is a general capability for services where users need to identify or select **occupations** and **skills/competences** without knowing the taxonomy's exact wording. Yrkesväljaren (YV), Kompetensväljaren (KV), JobSearch/Platsbanken query data and other AF datasets are reference products and evidence sources; they do not define the scope of the semantic retrieval core.

The core returns canonical taxonomy identities and keeps consumer-specific admission rules separate. A consuming service may therefore use the same retrieval engine while deciding independently which occupation/skill identities are selectable in that product.

The repository is the single source of truth for the problem definition, evidence inventory, experiments, evaluation protocol and implementation decisions.

## Demo

`demo/` contains a zero-backend research prototype for the `Beskriv din kompetens` fallback. Search runs locally in the browser using a build-time-compiled deterministic retrieval asset. Test feedback stays local until the tester explicitly exports a JSON file.

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
