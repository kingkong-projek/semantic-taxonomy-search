# Semantic Taxonomy Search

Research and implementation workspace for reusable semantic retrieval over Arbetsförmedlingen's Labour Market Taxonomy.

The goal is a general capability for services where users need to identify or select **occupations** and **skills/competences** without knowing the taxonomy's exact wording. Yrkesväljaren (YV), Kompetensväljaren (KV), JobSearch/Platsbanken query data and other AF datasets are current reference products and evidence sources; they do not define the scope of the semantic retrieval core.

The core must return canonical taxonomy identities and keep consumer-specific admission rules separate. A consuming service may therefore use the same retrieval engine while deciding independently which occupation/skill identities are selectable in that product.

The repository is the single source of truth for the problem definition, evidence inventory, experiments, evaluation protocol and implementation decisions.

Start with [`docs/research-plan.md`](docs/research-plan.md).
