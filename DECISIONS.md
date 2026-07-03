# DECISIONS.md

Append-only decision log for `tourvstravel.com`. Entries are never edited or
deleted; corrections are new entries referencing the superseded ID.
Procedure: see `GOVERNANCE.md` §6.

---

## D-001 — Adopt the Category Intelligence Factory plan

- **Date:** 2026-07-03
- **Decision:** `ASSET_INTELLIGENCE_FACTORY_PLAN.md` v1.0.0 is adopted as the
  governing development plan for the asset, under the Sovereign Asset System
  methodology. The asset's target state is a Category Intelligence Factory for
  the category *Travel Decision Architecture*: named ontology (TSO), named
  standard (TDIS), named protocol (SFP), operating engine, agent-readable
  machine layer, and governed monetization.
- **Rationale:** The asset already holds the substance (17-structure ontology,
  strict build governance, 7-language reference footprint, zero broken links);
  the plan converts that substance into named, citable, versioned category
  infrastructure.

## D-002 — Retire the "200 destinations" claim

- **Date:** 2026-07-03
- **Decision:** The home-page eyebrow claim "17 travel styles • 200
  destinations • evidence-led comparison" is retired in all seven languages.
  Replacement: "17 travel styles • 7 languages • evidence-led comparison" —
  both numbers are backed by shipped data and enforced by build gates
  (`_verify_experience_type_count`; per-language output contract). The retired
  wording is added to the claims-restraint build gate
  (`scripts/build.py::_verify_claims_restraint`) so its reappearance fails the
  build.
- **Rationale:** Zero destination pages were published while the claim was
  live; no `destinations.yaml` dataset exists yet. Under GOVERNANCE.md §1 this
  is an unverifiable public number — the single active claims-restraint
  violation found in the 2026-07-03 audit (plan §1.1). A destination count may
  return to public copy only when a governed destinations dataset ships and a
  build gate derives the number from it.

## D-003 — Governance layer made explicit

- **Date:** 2026-07-03
- **Decision:** `GOVERNANCE.md` (standing rules) and this `DECISIONS.md`
  (append-only log) are added at the repository root. Substantive changes to
  ontology, standards, public claims, route families, or monetization now
  require a logged decision in the same commit or PR.
- **Rationale:** The asset's technical governance (staged builds, output
  contracts, immutable routes) was already strong but implicit on the
  editorial side. Making the rules and the change history public and auditable
  is itself part of the asset's value thesis: trust as architecture.
