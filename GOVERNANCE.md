# GOVERNANCE.md

**Asset:** `tourvstravel.com` (TourVsTravel)
**Scope:** This document governs all public content, data, code, and interface
decisions for the asset. It has the same authority over editorial and
structural changes that the build pipeline has over output.
**Companion documents:** `ASSET_INTELLIGENCE_FACTORY_PLAN.md` (strategy),
`DECISIONS.md` (append-only decision log).

---

## 1. Claims restraint

1. No quantitative claim (counts of styles, destinations, languages, pages,
   users, traffic, revenue) appears in public copy unless it is derivable from
   data files or generated output that ships in the same build.
2. Every public number should be protected by a build gate where practical
   (e.g., the 17-style claim is enforced by `_verify_experience_type_count`;
   the 7-language claim is enforced by the per-language output contract).
3. A claim that loses its backing is retired immediately, and its exact
   wording is added to the retired-claims list in
   `scripts/build.py::_verify_claims_restraint`, which fails the build if the
   claim ever reappears.
4. Aspirations are labeled as aspirations. Capacity ("built to support …") is
   never phrased as inventory ("… destinations").
5. No revenue, traffic, ranking, or endorsement is claimed or implied until it
   exists and can be shown. The `/acquire/` page is the reference example of
   this posture.

## 2. Append-only concepts

1. Category vocabulary (ontology structure IDs, structural axes, named
   standards, protocol names) is never renamed and never silently deleted.
2. Evolution happens by versioning: a concept is superseded by a new version
   with a recorded decision in `DECISIONS.md`; the old identifier remains
   resolvable and marked as superseded.
3. Published machine-layer endpoints (JSON) are immutable in meaning once
   published; corrections ship as new versions.

## 3. Page and link integrity

1. A public URL exists only if its content meets the asset's quality bar
   (see `ASSET_INTELLIGENCE_FACTORY_PLAN.md` §5, TDIS). No thin pages, no
   placeholder pages, no phantom scale.
2. Broken internal links and missing static assets are build defects: the
   build fails on them (`_verify_local_links`,
   `_verify_static_asset_references`). They are never a post-hoc cleanup task.
3. Large combinatorial page families (destinations × style comparisons) are
   released in governed batches, each batch meeting the same bar as a
   hand-built page.
4. Generated route families are immutable at the routing layer
   (`scripts/routes.py`); no generator handcrafts public URLs.

## 4. Content and localization

1. All seven languages ship together for reference pages; localized pages must
   not contain English fallback blocks (enforced by
   `_verify_reference_page_integrity`).
2. Sources must be identifiable. Absence of evidence is stated, not hidden.
3. No fabricated live prices or availability, anywhere, ever. Cost statements
   are bands and structures with an explicit precision warning.
4. No universal winner is declared between travel structures; comparisons
   surface fit and tradeoff, not verdicts.

## 5. Monetization constraints

1. Income follows the diagnosis; it never shapes it. No sponsored placements
   inside comparisons, no sold ranking positions, no undisclosed affiliates.
2. Every revenue mechanism must be declarable in one honest sentence on a
   public page before it launches.
3. Affiliate links, where used, appear only after a comparison or diagnosis is
   rendered, under the standing disclosure copy in `tools_config.yaml`.

## 6. Change procedure

1. Substantive changes to the ontology, standards, public claims, route
   families, or monetization mechanics require an entry in `DECISIONS.md`
   before or with the change (same commit or same PR).
2. `DECISIONS.md` is append-only: entries are never edited or removed;
   corrections are new entries referencing the old ID.
3. The plan (`ASSET_INTELLIGENCE_FACTORY_PLAN.md`) is versioned; material
   revisions bump its version and note what changed.

## 7. Interface discipline

1. Order of precedence: concept → performance → beauty.
2. No interface element ships that fails any of: explains something; page
   works without it; survives mobile, SEO, accessibility, and load-time
   scrutiny; raises trust.
3. Motion and 3D are permitted only where they demonstrate the thesis better
   than a static composition.
