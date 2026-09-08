# ASSET_INTELLIGENCE_FACTORY_PLAN.md

**Asset:** `tourvstravel.com` (TourVsTravel)
**Plan version:** 1.1.0
**Current revision date:** 2026-09-08
**Revision note (1.1.0):** D-010 adopts the evidence-first phase in §16:
Evidence → Adoption → Economics. §16 supersedes conflicting priorities,
authority claims, and success criteria in the retained v1.0.7 text below.
Sections 0–15 and earlier revision notes remain historical context; their
completed-work entries are not a fresh production audit. Unconflicted standing
constraints continue to apply. GOVERNANCE.md remains authoritative.
**Companion status:** STRATEGIC_DEVELOPMENT_PLAN_AR.md is supporting guidance,
not a second governing plan; §16 controls sequencing and release gates.
**Plan date:** 2026-07-03
**Revision note (1.0.1):** P0 executed same day — "200 destinations" claim retired
(DECISIONS.md D-002), `GOVERNANCE.md`/`DECISIONS.md` added (D-003), claims-restraint
build gate added. Corrected audit: link integrity was already a build gate
(`_verify_local_links` fails the build on broken internal links), not merely a scan.
**Revision note (1.0.2):** P1 executed same day (D-004) — TSO v1, TDIS v1 (with the
Structure Fit Protocol as its operational section), public changelog, and machine
layer v1 published in seven languages; build contract extended to cover the new
page families and JSON artifacts. Site now 253 pages, 0 broken internal links.
**Revision note (1.0.3):** Artifact discipline (D-005) — `output/` removed from
version control; the deploy pipeline is the sole producer of build artifacts.
Page counts in this plan describe verified build output, reproducible with
`python -m scripts.build`.
**Revision note (1.0.4):** Compass v1 shipped (D-006) — first operating SFP
implementation, seven languages, client-side, engine settings from tools_config.
**Revision note (1.0.5):** Buyer-facing coherence (D-007) — acquire page updated to
describe the published infrastructure in all seven languages; tools index card and
system-step localization completed for fr/es/de/zh/ja.
**Revision note (1.0.6):** Destinations governed batch 1 (D-008) — 10 destinations
×7 languages with family-fit priors, official sources, and a missing/phantom-page
build gate. Site now 330 pages, 0 broken internal links. Comparison pages and the
Compass destination input are the next tranche.
**Revision note (1.0.7):** Pre-P3 closures (D-009) — machine layer unified under
`/api/index.json` with a bidirectional shipped-vs-listed gate, Compass engine spec
and destinations batch added to the machine mirror, sitemap x-default aligned with
the site-wide hreflang policy and gated against drift.
**Methodology:** Sovereign Asset System — Category Intelligence Factory model
**Status:** Governing document. Changes to this plan are append/version only.

---

## 0. What this document is

This is the governing development plan that converts `tourvstravel.com` from a
well-built reference site into a **Category Intelligence Factory**: an asset that
does not merely publish travel content, but produces **governed intelligence**
about a category it names, defines, classifies, measures, and serves — to humans,
search engines, and AI agents.

Every claim in this plan about the current state of the asset was verified
against the repository on the plan date. Claims restraint applies to this
document exactly as it applies to the public site.

---

## 1. Verified current state (audit snapshot, 2026-07-03)

What the asset already is — verified, not aspirational:

| Layer | Status | Evidence |
|---|---|---|
| Domain thesis | **Exists** | "The same destination is not the same trip" (trust pages, home) |
| Ontology | **Exists** | `data/experience_types.yaml` — 17 travel structures, `source_of_truth: true`, six structural axes |
| Comparison criteria | **Exists (unnamed)** | `data/comparison_criteria.yaml` — canonical criteria, not yet branded as a Standard |
| Engine | **Partial** | 5 tools defined under strict schema in `data/tools_config.yaml`; only Find-Your-Match is publicly built |
| Reference layer | **Exists** | methodology, source policy, editorial standards, travel decision architecture, reference report |
| Governance (build) | **Strong** | staged 23-step build with output-contract verification; immutable generated route keys; validated sitemap; fail-closed loaders |
| i18n | **Strong** | 7 languages (en, ar, fr, es, de, zh, ja), full hreflang + x-default, RTL support |
| Link integrity | **Verified + gated** | 232 generated pages, 226 unique internal hrefs, **0 broken internal links** (scan on plan date); build already fails on broken links via `_verify_local_links` |
| Buyer logic | **Exists** | `/acquire/` page with explicit non-claims section |
| Destinations | **Published (batch 1)** | `data/destinations.yaml` v1: 10 destinations ×7 languages, family-fit priors, official sources; contract-gated pages (D-008) |
| Comparison pages | **Not published** | route family exists (`/{lang}/{destination}/{a}--vs--{b}/`), no pages generated |
| Machine layer | **Absent** | no JSON endpoints, no agent-readable exports |
| Versioning artifacts | **Absent** | no public changelog, no decision log |
| Monetization | **Absent (declared)** | acquire page explicitly claims no revenue — honest, must stay honest |

### 1.1 Integrity finding (P0)

The home page eyebrow claims **"17 travel styles • 200 destinations"** while zero
destination pages are published. This is the single active violation of the
claims-restraint principle. It must be corrected before any other growth work:
either publish the destinations dataset or rewrite the claim to match reality.
A category intelligence asset cannot carry one inflated number anywhere.

---

## 2. Domain thesis — what sentence makes the name necessary?

> **The same destination is not the same trip.**
> A trip is a structure — purpose, pace, constraint, autonomy, support,
> predictability — and the structure changes what the destination means.
> TourVsTravel is the reference system for that prior decision: **tour vs travel**
> is not a word pair, it is the root fork in trip architecture.

The domain name *is* the category question. Every traveler implicitly answers
"tour or travel?" before any booking decision, but no reference system owns that
fork. The name is noun-vs-noun, search-intent aligned, language-independent in
meaning, and literally contains the category's primitive operation: **vs**.

**Category owned:** *Travel Decision Architecture* — the layer above destination
content and below booking. Not "travel content." Not "reviews." The structural
comparison of travel forms.

---

## 3. Category language — the vocabulary the asset will own

The asset does not adopt market language; it issues language the market will
need. Current and planned lexicon (each term gets a stable, citable reference
page):

| Term | Status | Definition anchor |
|---|---|---|
| **Travel Decision Architecture** | live | `/travel-decision-architecture/` |
| **Travel structure** (vs "travel style") | live in ontology | experience_types meta |
| **Structural axes** (structure intensity, autonomy level, support level, pace profile, immersion profile, predictability profile) | live in data, not yet public pages | ontology |
| **Trip architecture** | used, to be formalized | thesis pages |
| **Destination meaning shift** | to be coined | the phenomenon that the same place changes meaning under a different structure |
| **Structure–destination fit** | partially live ("fit") | comparison criteria |
| **Decision layer** | used | home, about |
| **Travel Structure Ontology (TSO)** | to be named publicly | §4 |
| **Travel Decision Integrity Standard (TDIS)** | to be named publicly | §5 |
| **Structure Fit Protocol** | to be named publicly | §6 |

Rule: a term enters the lexicon only with a stable URL, a strict definition, a
"what it is not" section, and a version. Terms are never renamed; they are
superseded with a recorded decision.

---

## 4. Ontology — Travel Structure Ontology (TSO)

**Already exists in substance.** `data/experience_types.yaml` defines 17 travel
structures as decision structures with stable operational meaning, six
structural axes, baseline scores declared as priors (not verdicts), and
profile affinities. This is genuinely rare: most travel sites have tags; this
asset has an ontology with a schema and fail-closed validation.

What remains is **promotion from internal data to public category
infrastructure**:

1. Name it publicly: **Travel Structure Ontology (TSO) v1** — one canonical page
   (`/{lang}/ontology/`) presenting the 17 structures, the six axes, the scale
   semantics, and the versioning rules.
2. Each of the 17 structure pages already exists (`/styles/…`); add to each a
   machine-readable structural profile block (axes + baseline scores) and a
   canonical citation line ("cite this structure as: TSO v1 / guided-group-tour").
3. Publish the ontology as data: `/ontology/tso-v1.json` (see §8, machine layer).
4. Append-only evolution: axes and structure IDs are never deleted; deprecation
   is recorded, never silent.

The ontology makes the asset the **issuer of the category's classification**,
not a consumer of it.

---

## 5. Standard — Travel Decision Integrity Standard (TDIS)

The ontology says what the structures *are*. The Standard says what a **sound
travel decision comparison** is. Raw material already exists in
`data/comparison_criteria.yaml`; it must be elevated into a named, citable,
versioned standard:

**TDIS v1 — a travel decision comparison is sound when:**
1. Both options are identified as travel structures (TSO classes), not moods or
   marketing labels.
2. Comparison runs over explicit criteria with declared scales — never vague
   editorial preference.
3. Baseline scores are declared as structural priors and contextualized per
   destination or traveler profile before recommendation.
4. Cost claims are bands and structures, never fabricated live prices.
5. Sources are identifiable; absence of evidence is stated, not papered over.
6. Fit precedes preference; tradeoff precedes aspiration.
7. No universal winner is declared between structures.

Public surface: `/{lang}/standard/` — the standard, its version history, and a
conformance checklist that third parties (bloggers, tools, AI agents) can apply.
The standard is the asset's gravity: others can copy content; adopting the
standard means citing the asset.

---

## 6. Protocol — Structure Fit Protocol (SFP)

The repeatable procedure that turns the ontology + standard into a diagnosis:

```
INPUT   traveler intent, constraints (time, budget band, mobility,
        social rhythm), destination (optional)
STEP 1  Classify candidate options into TSO structures
STEP 2  Score fit across the six structural axes
STEP 3  Apply TDIS rules (priors → context, bands not prices, no universal winner)
STEP 4  Emit a Structure Fit result: ranked fit + explicit tradeoffs
        + "what this choice costs you" (the honest inverse)
OUTPUT  a governed diagnosis, linkable to the TSO class pages used
```

The protocol page (`/{lang}/methodology/structure-fit-protocol/`) documents this
so that the tools are seen as *implementations of a protocol*, not gadgets. Every
engine output links back to the TSO class pages and the TDIS rules it applied —
engine output → class page → standard → methodology forms a closed reference
loop (this is the internal-link spine, see §10).

---

## 7. Engine — from configured to operating

Five tools are already schema-defined (`travel_decision_compass`,
`tour_vs_travel_cost_comparator`, `destination_experience_matcher`,
`travel_style_index`, `flight_route_comparator`). Activation order, governed by
"one excellent engine beats five stubs":

1. **Travel Decision Compass** (the flagship — implements SFP end to end;
   client-side JS, static-host compatible, works without backend).
   Output = a Structure Fit diagnosis with links into TSO class pages.
2. **Tour vs Travel Cost Comparator** — band-based cost structure comparison
   (never live prices; the precision warning already exists in config).
3. **Destination Experience Matcher** — requires the destinations dataset (P1).
4. `travel_style_index` and `flight_route_comparator` remain gated until they
   can meet TDIS; shipping weak tools is forbidden.

Engine governance rules (already implied by tools_config strict mode, now made
explicit): every tool declares its data vintage, its scale semantics, and what
it does *not* know. A tool that cannot say "I don't know" does not ship.

---

## 8. Reference layer + machine layer (agent-readable asset)

Humans get pages; agents get structure. Both must resolve to the same truth.

**Existing:** canonical URLs, hreflang, JSON-LD (Organization, WebSite, WebPage),
validated sitemap, stable reference pages.

**To build — the machine layer, all static, versioned, immutable once published:**

| Endpoint | Content |
|---|---|
| `/ontology/tso-v1.json` | the 17 structures, axes, scales, baseline priors |
| `/standard/tdis-v1.json` | the standard's rules in structured form |
| `/api/structures/{id}.json` | per-structure profile (mirrors the class page) |
| `/api/criteria-v1.json` | canonical comparison criteria |
| `/.well-known/` summary or `/about.json` | asset identity, thesis, version map |

Rules: JSON mirrors pages 1:1 (no fork between human truth and machine truth);
every JSON file carries `schema_version`, `dataset_version`, `last_reviewed`;
endpoints are append-only (v1 URLs never change meaning). This is what makes the
asset **quotable by AI agents** — the cheapest durable moat available right now,
because agents prefer sources that are stable, structured, and self-describing.

---

## 9. Governance — trust as architecture

Existing technical governance is strong (staged builds, output contracts,
fail-closed loaders, immutable route families, schema validation). The missing
half is **editorial/versioning governance made public**:

1. **`GOVERNANCE.md`** (repo) — the rules: append-only lexicon, versioned
   ontology/standard, claims-restraint policy, quality gates for new page
   families.
2. **Public changelog** (`/{lang}/changelog/` or a section on methodology) —
   dated, human-readable record of every substantive change to TSO, TDIS, tools.
   Buyers and agents both read this as proof of discipline.
3. **Decision log** (`DECISIONS.md`, repo) — why each structural choice was made;
   append-only.
4. **Claims audit** as a build-adjacent check: no number appears in public copy
   (page counts, destination counts, style counts) unless derivable from data
   files. This mechanically prevents a repeat of the "200 destinations" finding.
5. **Quality gates for scale:** destination pages and comparison pages (the
   large combinatorial families) only ship when each page carries real
   differentiated content that meets TDIS. No thin-page floods, ever — phantom
   scale is the one thing that would destroy both SEO and buyer trust
   simultaneously.

---

## 10. SEO doctrine — deterministic, not opportunistic

The routing layer already enforces: one canonical URL per page, HTTPS-only
absolute URLs, validated sitemap entries, directional comparison pairs as
distinct intent pages, reserved-substring defense. The doctrine forward:

1. **No phantom pages.** A URL exists only if its content meets TDIS. The
   combinatorial comparison space (destinations × 17 × 16 ordered pairs) is a
   *capacity*, released in governed batches, never dumped.
2. **No broken links.** The link-integrity scan (0 broken today) becomes a build
   gate: the build fails if any internal href does not resolve. Death of a link
   is treated as a build defect, not a cleanup chore.
3. **Internal-link spine, not random cross-links:** every page links up to its
   governing concept (class → ontology → thesis) and sideways only through
   meaningful contrast (A-vs-B). Link topology mirrors the conceptual model —
   that is what "فائقة القوة" means operationally: links that encode meaning.
4. **Query targets:** own the head term ("tour vs travel" and its 7-language
   equivalents), then the structural long tail ("guided group tour vs
   independent travel", "…in {destination}") — released with the comparison
   batches, never before.
5. **E-E-A-T surface** already exists (methodology, source policy, editorial
   standards); keep every new page family wired into it.

---

## 11. Interface thesis — the interface embodies the fork

**Thesis:** the interface *is* a comparison instrument. The asset's core gesture
is the fork — one destination, two structures, diverging meanings — so the
interface's identity element is the **directional VS composition**: two panels,
one axis, visible tradeoff. Not decoration; the thesis rendered.

Rules (per the Interface Governance discipline):

- The VS composition is the recurring visual primitive: home, comparison pages,
  compass results all express "same input, two architectures, different
  meanings."
- Motion only where it explains divergence (e.g., the two panels separating from
  a shared destination header). No ornamental animation.
- The existing identity (deep institutional blue `#002B49`, restrained gold
  `#D4AF37`, paper background) reads as reference-grade, not travel-brochure.
  Keep it; do not chase trend palettes.
- Every interface decision passes the test battery: does it explain something?
  does the page work without it? does it survive mobile, SEO, accessibility,
  and load-time scrutiny? does it raise trust? If any answer is no, it does not
  ship.
- Order of precedence: **concept → performance → beauty.**
- No WebGL/3D unless it demonstrates structural divergence better than the flat
  composition does — currently it does not.

---

## 12. Monetization before sale — income as an extension of authority

Constraint: nothing that contaminates neutrality. The acquire page currently
declares zero revenue truthfully; every future revenue line must be equally
declarable. Sequenced by trust-safety:

**Phase A (can start once Compass is live):**
1. **Structure Fit Report (premium PDF)** — a personalized, TDIS-conformant
   diagnosis generated from the Compass; free summary, paid full report.
2. **Disclosed affiliate resolution** — after a diagnosis (never before), the
   "next step resources" layer resolves to booking/logistics partners under the
   existing affiliate-disclosure copy. Income follows the decision; it never
   shapes it. Rankings remain algorithmically derived from the ontology.

**Phase B (after reference traction):**
3. **Licensing TSO + TDIS** — the ontology and standard as licensed data/method
   for trip-planning products and AI travel agents (the machine layer of §8 is
   the demo).
4. **Embeddable Compass widget** — the diagnosis engine embedded on partner
   sites, "powered by TourVsTravel," each embed a citation.
5. **Category intelligence briefs** — periodic structural reports (e.g., "state
   of guided vs independent travel demand") for tourism boards and travel-tech;
   sponsorship allowed only as clearly-labeled patronage of an independent
   report, never editorial input.

**Never:** sponsored placements inside comparisons, sold ranking positions,
undisclosed affiliates, fabricated live prices, thin-content ad arbitrage. Each
of these buys months of income by selling the asset's terminal value.

---

## 13. Buyer logic — who must own this, and why not owning it is a loss

**Strategic buyer classes, in order of thesis-fit:**

1. **AI trip-planning platforms / travel agents (agentic).** They need exactly
   what LLMs lack: a governed, versioned, citable classification of travel
   structures to ground their recommendations. Buying the asset = buying the
   category's coordinate system, its name, and its machine layer in one move.
2. **Travel marketplaces/OTAs building decision layers.** Their weakness is
   perceived bias; this asset's whole identity is the neutral layer *before*
   booking. It is the credibility they cannot grow internally.
3. **Travel media groups** moving from content volume to reference authority.
4. **Tourism boards / DMO coalitions** needing multilingual decision
   infrastructure rather than more brochures.

**The moat argument (why "we could build it ourselves" fails):** a competitor
can clone features, but cannot clone (a) the name that *is* the category
question, (b) the accumulated versioned ontology with its public history, (c)
the 7-language reference footprint with clean hreflang topology, (d) the
governance record (changelogs, decision logs, claims restraint) that agents and
buyers can audit, and (e) whatever citation graph the standard accumulates.
Re-deriving that under a weaker name, later, while this asset compounds, is the
loss.

**What makes the domain feel inevitable in its category:** when the head query,
the ontology, the standard, the protocol, the flagship tool, and the machine
endpoints all resolve to the same domain, the category has one address. At that
point, not acquiring it means building a travel-decision product whose central
vocabulary is owned by someone else.

---

## 14. Execution roadmap

**P0 — Integrity (immediately, before growth):** ✅ completed 2026-07-03
- [x] Fix the "200 destinations" claim → replaced with build-gated numbers ("17 travel styles • 7 languages"); retired wording blocked by a new claims-restraint build gate (D-002).
- [x] Add `GOVERNANCE.md` + `DECISIONS.md`; adopt append-only rules (D-003).
- [x] Link-integrity build gate — found to already exist (`_verify_local_links`); claims-restraint gate added alongside it.

**P1 — Name the infrastructure (weeks):** ✅ completed 2026-07-03 (D-004)
- [x] Public TSO v1 page + per-structure citation lines (`/{lang}/ontology/`, 7 languages, rendered from the canonical dataset).
- [x] Public TDIS v1 page + conformance guidance (`/{lang}/standard/`, weighted criteria rendered from data).
- [x] Structure Fit Protocol — published as the operational section of the TDIS page (D-004); dedicated page deferred until the Compass ships as its implementation.
- [x] Machine layer v1: `tso-v1.json`, `tdis-v1.json`, `criteria-v1.json`, 17 per-structure JSON artifacts, `about.json` — all build-gated (parse, version envelope, class count).
- [x] Public changelog page (`/{lang}/changelog/`, rendered from append-only `data/changelog.yaml`).

**P2 — Operate the engine (1–2 months):**
- [x] Ship Travel Decision Compass (client-side, SFP-conformant, outputs linked to class pages) — shipped 2026-07-04 (D-006), 7 languages, engine settings read from tools_config.
- [ ] Ship Cost Comparator (bands only).
- [x] Destinations dataset v1 — batch 1 shipped 2026-07-04 (D-008): 10 destinations to standard.
- [ ] First governed batch of comparison pages (builds on the destinations dataset).

**P3 — Monetize + measure (2–4 months):**
- [ ] Structure Fit Report (paid) + disclosed affiliate resolution layer.
- [ ] Search Console + privacy-safe analytics; record baseline; publish honest usage signals on `/acquire/` only when they exist.
- [ ] Embeddable widget prototype; licensing one-pager for TSO/TDIS.

**Measurement (kept honest):** indexed pages vs published pages (should be ≈1),
head-term rankings in 7 languages, citation/backlink acquisition to
ontology/standard pages, Compass completion rate, report revenue, agent traffic
to JSON endpoints. Vanity metrics are not tracked.

---

## 15. Standing rules (summary of what governs all of the above)

1. Claims restraint: no number without data behind it.
2. Append-only concepts: nothing renamed, nothing silently deleted.
3. No phantom pages, no broken links — both are build defects.
4. One excellent engine before five stubs.
5. Income follows the diagnosis; it never shapes it.
6. Human pages and machine endpoints tell the same truth.
7. Concept → performance → beauty, in that order.
8. Every layer must make the sentence truer: **the same destination is not the same trip — and this domain is where that decision is made.**

---

## 16. Evidence-first development phase — v1.1.0 (2026-09-08)

### 16.1 Authority, scope, and current-state boundary

Adopted by D-010. This is the current execution plan. It supersedes the
unfinished P2/P3 ordering in §14, the commercialization ordering in §12, and
any interpretation of §§2–3 or §13 as proof of category ownership, external
adoption, or an inevitable acquisition. TSO, TDIS, and SFP are project-developed
frameworks; external authority must be supported by specific, verifiable use.
Existing identifiers, definitions, URLs, endpoint meanings, and governance
constraints are preserved. This revision changes planning documents only.

The local source and D-004 through D-009 record the ontology, Compass, ten
destinations, seven-language reference footprint, and machine index. The
historical audit tables above mix earlier snapshots and later additions; they
must not be used as today's inventory. A fresh build, live-site audit, and
search/usage baseline remain implementation work. Traffic, revenue, external
adoption, and current production page counts are not established by this revision.

The strategic sequence is:

**Evidence registry → existing destination evidence cleanup → contextual
decision cases → proven utility → destination-aware Compass → economics.**

The registry begins as the working record for the cleanup, not a separate large
platform project. New destinations, additional standards, Cost Comparator,
paid API development, and broad tourism-economic coverage are deferred.
Calendar dates do not override evidence or release gates.

### 16.2 Close evidence debt across the existing ten destinations

Review every material claim in the existing destination dataset and its
localized projections, including summaries, season guidance, duration guidance,
and family-fit priors. A material claim is one that could change a reader's
decision, a comparison conclusion, or a tool output. A tourism-body homepage
does not by itself substantiate the individual claims on a destination page.

Each claim receives a stable ID and an explicit type:

| Type | Required treatment |
|---|---|
| FACT | Direct supporting evidence with the relevant scope and period; no unsupported superlative |
| DERIVED | Identified input claims/data, units, reproducible calculation, assumptions, and limitations |
| EDITORIAL | Attributed reasoning, supporting evidence where it makes empirical assertions, and explicit limits |
| STRUCTURAL_PRIOR | Identified framework/version, rationale, context limits, and a visible statement that this is not an observed result |

Relabeling an empirical assertion EDITORIAL or STRUCTURAL_PRIOR does not cure
missing evidence. Each unsupported assertion must be supported, narrowed,
removed, or explicitly withheld from publication; its dependent outputs are
identified. Evidence closure means the audit disposition has been applied to
the affected public content, not merely recorded in an internal spreadsheet.

The proposed registry contract records claim ID, type, statement, evidence IDs,
exact source locator, publisher, publication/retrieval dates, observed period,
geography, units where applicable, derivation, reviewer, review date, next review,
rights/reuse status, and dependent pages/tools/machine artifacts. Non-applicable
fields are explicit; unknown rights are not assumed to permit redistribution.
Evidence records have stable IDs, relevant extracts or locators within allowed
rights, and source limitations. Contradictory sources and corrections remain
traceable. A correction propagates to all affected projections.

These are implementation requirements, not claims that a registry or automated
validator already exists. The implementation must define schema validation and
meaningful build gates before releasing evidence-backed cases. Existing v1
machine contracts cannot silently change meaning; corrections or changed
semantics follow the established versioning rule.

### 16.3 Two reference-quality cases before six

Start with two contextual research dossiers. Morocco for a first-time family
and Japan for a first-time visitor are candidate contexts, subject to evidence
availability and editorial capability. Select existing TSO structure IDs during
implementation; informal titles must not introduce new ontology classes.

Each case is one canonical research object with a stable case ID, context,
claim IDs, evidence IDs, shared calculations, assumptions, alternatives,
tradeoffs, uncertainty, reviewer, and version history. Its language versions
are localized editorial projections of that same object. The canonical research
object is not an instruction to canonicalize every language URL to English;
existing localized canonical/hreflang policy remains in force.

All existing seven-language reference release obligations continue to apply.
There is no language exception in this decision. Research is performed once;
translations share claim and evidence IDs and calculations, and receive language
review. Two cases are not fourteen independent studies.

Both cases must pass these gates before expansion to four additional cases:

1. **Evidence integrity:** all material claims are classified and defensible;
   direct evidence supports the exact assertion and all derivations reproduce.
2. **Editorial review:** an identified independent reviewer checks reasoning,
   limits, conflicts of interest, and translation fidelity; no unresolved
   decision-changing error remains.
3. **User comprehension:** at least five formative reader sessions per case;
   at least four readers per case can explain a conditional fit and one material
   limitation. Failures trigger revision and retesting. This is a proposed
   usability gate, not a population-level confidence estimate.
4. **Citation usability:** a reviewer can retrieve the claim, exact source,
   relevant period, case version, and permitted citation from the published
   representation without guessing.
5. **Machine parity:** machine and human projections resolve the same IDs,
   evidence, context, and calculations; existing route, localization, and build
   contracts pass. No machine endpoint or case is advertised before it ships.

### 16.4 First 90 days — conditional delivery schedule

Day 1 is the start of implementation, not a claim that work began on the plan date.

| Window | Deliverable | Accountable role | Exit condition |
|---|---|---|---|
| Days 1–14: evidence debt closure | Working registry; material-claim audit of all ten destinations and languages; corrections applied; current build/production and search baseline where access exists | Research editor with developer support | Every material claim has a reviewed disposition; unsupported assertions are corrected or withheld in affected outputs; missing access is recorded, not treated as zero traffic |
| Days 15–30: two reference-quality cases | Two canonical dossiers, reviewed localized projections, reproducible calculations and machine representation | Research editor + independent reviewer + developer | Both cases pass all five §16.3 gates |
| Days 31–60: prove repeatability | Up to four more cases using the same schema and workflow; record production and maintenance cost | Product owner + editor | Each added case passes the same gates; no template-generated evidence gaps; reduce volume if review capacity is insufficient |
| Days 61–90: prove utility | Compass comprehension study and a bounded agency workflow pilot | Product owner + agency participant | Fifteen Compass sessions, with at least twelve participants explaining a fit and limitation; documented repeat agency use or explicit reasons for non-use |

If debt closure or a case gate fails, fix it before expanding. Agency recruitment
and access setup may proceed alongside research when separately authorized;
outreach is not performed by adopting this plan. The pilot may use reviewed cases
and the existing Compass without changing destination scoring.

Destination-aware Compass requires reviewed destination priors and accepted cases
for every enabled destination context, explicit scoring derivations, scenario
tests, explanation of changed results, and machine parity. Unsupported contexts
remain unavailable. Passing a usability study alone does not validate the priors.

### 16.5 Adoption before economics

Months 4–6 test repeated agency/advisor use and a narrowly scoped willingness-to-pay
offer. Months 7–9 develop the product supported by that evidence (for example a
reusable case workflow or an embed), subject to positive service economics.
Months 10–12 consolidate the evidence history, corrections, reusable data,
permissions, operational documentation, and verifiable institutional use.
These are hypotheses and decision windows, not revenue commitments.

Tourism economics is in scope only when it explains the effects or tradeoffs of
travel structures using suitable data. Aggregate tourism counts cannot establish
TSO structure shares, and spending is not profit. A broad statistics portal and
a paid API are not current delivery goals. Existing monetization constraints
continue: diagnosis is independent, sponsorship cannot buy comparison positions,
and data cannot be resold without appropriate rights.

The primary evidence of progress is defensible claims, reproducible cases,
reader understanding, repeat use, independent citations, and paid demand when
tested. Track maintenance cost and rights alongside revenue. Indexed/published
page ratio near one, page volume, terminology, JSON availability, and rankings
alone are not success criteria; this supersedes the measurement wording in §14.
No traffic, adoption, valuation, or defensibility score is invented.

### 16.6 Implementation boundaries and companion document

STRATEGIC_DEVELOPMENT_PLAN_AR.md remains explanatory guidance for audiences,
SEO, staffing, and longer-term options. Its original schedules and any conflicting
priorities are superseded by this section. There is one governing execution plan.

Subsequent production changes should be independently reviewable: evidence
schema and cleanup; first two cases and their release gates; repeatability;
utility evaluation; then any eligible engine change. Substantive changes receive
their own decision entries. No public changelog, destination data, scoring,
routes, or generated output changes are included in this planning revision.
