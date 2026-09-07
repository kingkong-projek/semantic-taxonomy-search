# Pareto demand priority — taxonomy v31

**Status:** measured; YV hard-destination interpretation superseded 2026-09-07  
**Measured:** 2026-09-06

> **Interpretation update (2026-09-07):** the measured Pareto counts remain valid, but the conclusion that YV description retrieval should be hard-limited to the 159 P80 occupations is superseded. P80 remains the demand-priority benchmark stratum. Track-2 YV description capability now keeps all 2,105 active v31 `occupation-name` identities eligible and treats weak long-tail evidence as a confidence/abstention problem rather than candidate-universe exclusion. The 316-skill P80 boundary remains the current KV research envelope. See `docs/research-plan.md` and the current human-validation contract.

## Conclusion

The first semantic-search release does not need equal semantic quality across all 2,105 occupations and 6,752 skills.

Historical API exposes server-side taxonomy occurrence statistics for both `occupation-name` and `skill`. Intersected with active v31 identities, the occurrence mass is strongly concentrated:

| share of observed active-v31 occurrence mass | occupations | skills |
|---:|---:|---:|
| 50% | 33 | 63 |
| 80% | **159** | **316** |
| 90% | 302 | 614 |
| 95% | 455 | 976 |
| 99% | 834 | 1,848 |

The **P80 priority core is therefore 159 occupation-name identities + 316 skill identities = 475 canonical targets**. P90 and P95 are explicit priority/expansion tiers rather than equal-quality launch requirements.

Active v31 concepts represented in the Historical stats response:

- occupations: **1,837/2,105 = 87.268%**;
- skills: **2,725/6,752 = 40.358%**.

The frozen aggregate stores the full ranked P95 population. P80/P90 memberships are deterministic prefixes of that ranking, so no hand-maintained allow-list is needed.

## Semantics and boundary

These counts are a **corpus/popularity proxy derived from historical job-ad taxonomy occurrences**. They are useful for deciding what to make good first. They are not:

- user query→selection ground truth;
- proof that a skill is essential or required;
- canonical meaning;
- a reason to remove tail concepts from the products.

The full lexical picker remains the primary deterministic product path over the entire product-valid taxonomy. P80 prioritises evaluation and quality work; for YV occupation descriptions it no longer excludes valid active destination identities.

YV additionally has real Platsbanken search-frequency evidence. That source remains valuable for query sampling and a later traffic-weighted cross-check, but its free text cannot be fully mapped to canonical destinations automatically. Using Historical occurrence counts gives one simple, explicit concept-level priority proxy shared by YV occupations and KV skills.

## v0 simplification — historical decision and current correction

The 2026-09-06 prototype decision was:

- YV description ranking over the 159 P80 `occupation-name` identities, later plus six explicit boundary identities in C1/C2;
- KV semantic destinations over the 316 P80 active `skill` identities;
- YV job titles retained as lexical/router vocabulary rather than direct semantic destinations;
- small safety/regression slices for ambiguity, routing, hard negatives and abstention.

The YV part is now retained only as a bounded prototype/regression result. It was found to conflate demand prioritisation with candidate eligibility: an otherwise valid occupation outside the 165 C1/C2 description documents could never be returned from arbitrary description text. Current Track-2 YV research therefore uses all 2,105 active `occupation-name` identities as the destination universe while preserving P80 as the priority stratum. KV remains on the 316-skill P80 research envelope until separate skill evidence justifies expansion.

## Top observed occupations

- `bXNH_MNX_dUR` — Sjuksköterska, grundutbildad: 434,319
- `eU1q_zvL_9Rf` — Personlig assistent: 285,532
- `8Uhp_XYo_z5f` — Kundtjänstmedarbetare: 175,596
- `p17k_znk_osi` — Utesäljare: 151,017
- `ek9W_CmD_y2M` — Butikssäljare, fackhandel: 132,215
- `bUP3_Ztw_VC1` — Hemförsäljare: 110,114
- `fg7B_yov_smw` — Systemutvecklare/Programmerare: 108,477
- `WZ2C_vH9_8ek` — Telefonförsäljare: 106,067
- `jsUx_ngg_Kz2` — Innesäljare: 91,098
- `rUcW_z9R_Qsv` — Förskollärare: 86,516
- `pBhS_6fg_727` — Butikssäljare, dagligvaror/Medarbetare, dagligvaror: 85,209
- `8jrL_5RZ_9Kt` — Account manager/AM: 75,021

## Top observed skills

- `dJa5_Nao_mDS` — Legitimation som sjuksköterska: 4,246
- `dRWb_Mgx_yJf` — Försäljningsvana, uppsökande försäljning företag: 3,659
- `AwhJ_eLD_xpG` — Försäljningsvana, telefonförsäljning: 3,062
- `Tpvt_9yv_KAw` — Taxiförarlegitimation: 2,938
- `yKnk_W7X_Zvk` — Lärarlegitimation: 2,565
- `Azca_cCi_Y21` — Legitimation som psykolog: 2,143
- `MjPH_341_Zmc` — Socionomexamen: 2,018
- `zJZd_pDs_SDf` — Lärarexamen: 1,844
- `FJBT_yzk_BWe` — Uppsökande försäljning: 1,824
- `w8bU_wHe_omF` — MS Office: 1,730
- `Lz84_K5d_CcL` — Digital marknadsföring/Onlinemarknadsföring: 1,666
- `Hh2K_Seb_wZQ` — Kognitiv beteendeterapi: 1,524

## Reproducibility

- Taxonomy v31 source SHA-256: `634fd9d848a172747e54e3e487160a912ae6c0fcb8219c50998767c8c9aacbcc`
- Historical API Swagger SHA-256: `f421f111f96b6de59b007a88c5c6b4dc136fdff8ef4e13cf26be6669c60904eb`
- Normalized Historical statistic-row SHA-256: `21b7333a350ecc595efb22f02f3dfe98001259b2b00c87ed7f2d0020bc93ef3d`
- Hash semantics: `SHA-256 of canonical normalized occupation-name/skill statistic rows (concept_id, label, legacy_ams_taxonomy_id, occurrences); API timing/response metadata excluded`
- Measurement code: `scripts/pareto_demand_coverage.py`
- Frozen machine evidence: `research/coverage/v31/pareto-demand-aggregate.json`
