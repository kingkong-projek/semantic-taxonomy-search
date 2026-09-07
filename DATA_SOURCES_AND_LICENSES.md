# Data sources and licences

This repository researches semantic retrieval over public labour-market data. External source identity and accepted hashes are tracked in [`research/coverage/source-adapters.json`](research/coverage/source-adapters.json).

## Current demo

The current `Beskriv din kompetens` demo is built from:

- Arbetsförmedlingen Labour Market Taxonomy / taxonomy v31 concepts and relations.
- Arbetsförmedlingen's mapping of labour-market-training modules to taxonomy skills.
- Project-generated teacher phrases used as synthetic build-time retrieval evidence. These phrases are not canonical taxonomy data and do not replace source authority.

The two Arbetsförmedlingen datasets above are published as **Creative Commons CC0 1.0** in Arbetsförmedlingen's open-data catalogue. CC0 permits reuse, modification and redistribution without an attribution requirement. We nevertheless retain source URLs, version identifiers and hashes for scientific provenance.

Official catalogue references:

- Labour Market Taxonomy: https://data.arbetsformedlingen.se/dataservice/employer-market-taxonomy/
- Concepts and common relations: https://data.arbetsformedlingen.se/dataset/concepts-and-common-relations/
- Mapping of labour-market training: https://data.arbetsformedlingen.se/dataset/dataset-mapping-of-labour-market-training/
- CC0 1.0: https://creativecommons.org/publicdomain/zero/1.0/

## Other Arbetsförmedlingen / JobTech evidence used in the research repository

The repository also evaluates or derives measurements from public AF/JobTech datasets including:

- Yrkesväljaren
- Kompetensväljaren
- JobSearch Trends
- Relevanta kompetenser
- Närliggande yrken and its keyword/relevance distributions
- Current and historical job-ad data / statistics
- Yrkesinformation interimslösning
- Taxonomy keyword, occupation/skill and substitutability relations

These sources are exposed through Arbetsförmedlingen's open-data catalogue and are published there as **CC0**. For each source actually admitted to an experiment, the repo's source registry records its exact source URL and, where applicable, a SHA-256 digest.

Catalogue: https://data.arbetsformedlingen.se/dataset/

## Derived and generated artefacts

Files under `research/`, `artifacts/` and generated demo assets may be transformations, aggregates, measurements or model-authored research evidence derived from the sources above. A derived artefact is not promoted to canonical truth merely because it is checked into this repository. Provenance classes and authority boundaries are part of the research contract.

## Design system

The demo uses a small local compatibility layer with values adapted from Arbetsförmedlingen's Designsystem rather than loading the full runtime package. Arbetsförmedlingen Designsystem is licensed under **Apache License 2.0**. See [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

## Branding and endorsement

Use of Arbetsförmedlingen open data or design-system conventions does **not** imply that this repository or its GitHub Pages demo is an official Arbetsförmedlingen service, publication or endorsement. The demo is a research prototype.

## Adding a source

Do not add a new external source to the research pipeline until its origin, intended use and licence/reuse terms are documented. If a future source is not CC0 or Apache-2.0, its specific obligations must be recorded before derived data or code is redistributed.
