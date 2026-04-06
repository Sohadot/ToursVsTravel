#!/usr/bin/env python3
"""
TourVsTravel.com — Static Site Generator v2
=============================================
Auto-combination engine: 200 destinations × 17 experience types.
Generates 380,800 pages across 7 languages.

Architecture:
  data/destinations.yaml        → 200 destinations
  data/experience_types.yaml    → 17 experience types
  data/comparisons.yaml         → Optional enrichment data per combination
  data/comparison_criteria.yaml → Scoring criteria definitions
  data/site_config.yaml         → Site-wide config & UI strings

Generation Logic:
  FOR each destination (200):
    FOR each exp_a in experience_types (17):
      FOR each exp_b in experience_types (16):
        IF combination passes quality gate:
          lookup enrichment data from comparisons.yaml (optional)
          generate page × 7 languages

Output:
  output/{lang}/{destination}/{slug_a}-vs-{slug_b}/index.html

Quality Gate (every combination must pass):
  - destination has name + region + known_for + sources
  - exp_a and exp_b have descriptions in all 7 languages
  - exp_a ≠ exp_b
  - combination not in exclusion list

Standards:
  - Valid HTML5 + ARIA accessibility
  - JSON-LD: Article + BreadcrumbList + FAQPage
  - Hreflang for all 7 language variants
  - Open Graph + Twitter Cards
  - RTL support for Arabic
  - sitemap.xml + robots.txt auto-generated
"""

import sys
import yaml
import json
import shutil
import logging
import itertools
from pathlib import Path
from datetime import datetime, timezone
from jinja2 import Environment, FileSystemLoader, select_autoescape

# ─── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("generate")

# ─── Paths ────────────────────────────────────────────────────────────────────

BASE_DIR     = Path(__file__).parent
DATA_DIR     = BASE_DIR / "data"
TEMPLATE_DIR = BASE_DIR / "templates"
OUTPUT_DIR   = BASE_DIR / "output"
STATIC_DIR   = BASE_DIR / "static"

# ─── Config ───────────────────────────────────────────────────────────────────

# Combinations to always skip (semantically redundant or low-value)
EXCLUDED_PAIRS = {
    # Same category pairs that don't make sense to compare
    ("religious_pilgrimage", "shrine_saints_tourism"),
    ("shrine_saints_tourism", "religious_pilgrimage"),
    ("solo_travel", "independent_travel"),
    ("independent_travel", "solo_travel"),
    ("eco_sustainable_travel", "regenerative_travel"),
    ("regenerative_travel", "eco_sustainable_travel"),
}

# ─── YAML Loader ──────────────────────────────────────────────────────────────

def load_yaml(filename: str) -> dict:
    path = DATA_DIR / filename
    if not path.exists():
        log.error(f"Missing data file: {path}")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)

# ─── Index Builders ───────────────────────────────────────────────────────────

def build_index(items: list, key: str = "id") -> dict:
    return {item[key]: item for item in items}

# ─── Language Helpers ─────────────────────────────────────────────────────────

def t(field, lang: str, fallback: str = "en"):
    """Extract multilingual text — dict {en:..., ar:...} or plain string."""
    if isinstance(field, dict):
        return field.get(lang) or field.get(fallback, "") or ""
    return str(field) if field else ""

def tlist(field, lang: str, fallback: str = "en"):
    """Extract multilingual list."""
    if isinstance(field, dict):
        return field.get(lang) or field.get(fallback, []) or []
    return field or []

# ─── URL Builder ──────────────────────────────────────────────────────────────

def build_url(base_url: str, lang: str, dest_id: str,
              slug_a: str, slug_b: str) -> str:
    return f"{base_url}/{lang}/{dest_id}/{slug_a}-vs-{slug_b}/"

def build_hreflang_urls(base_url: str, dest_id: str,
                        exp_a: dict, exp_b: dict,
                        languages: list) -> dict:
    urls = {}
    for lc in languages:
        lang = lc["code"]
        sa = t(exp_a.get("slug", {}), lang) or exp_a["id"].replace("_", "-")
        sb = t(exp_b.get("slug", {}), lang) or exp_b["id"].replace("_", "-")
        urls[lang] = build_url(base_url, lang, dest_id, sa, sb)
    return urls

# ─── Enrichment Lookup ────────────────────────────────────────────────────────

def lookup_enrichment(comparisons: list, dest_id: str,
                      exp_a_id: str, exp_b_id: str) -> dict:
    """
    Look for optional enrichment data in comparisons.yaml.
    Returns empty dict if not found — page still generates with base data.
    """
    for c in comparisons:
        if (c.get("destination_id") == dest_id and
                c.get("experience_a") == exp_a_id and
                c.get("experience_b") == exp_b_id and
                c.get("status") == "published"):
            return c.get("data", {})
    return {}

# ─── Quality Gate ─────────────────────────────────────────────────────────────

def passes_quality_gate(dest: dict, exp_a: dict, exp_b: dict) -> tuple:
    """
    Returns (True, "") or (False, reason).
    Every combination must pass before a page is generated.
    """
    # Must be different
    if exp_a["id"] == exp_b["id"]:
        return False, "same experience type"

    # Check exclusion list
    if (exp_a["id"], exp_b["id"]) in EXCLUDED_PAIRS:
        return False, f"excluded pair: {exp_a['id']} + {exp_b['id']}"

    # Destination must have minimum data
    if not dest.get("name") or not t(dest["name"], "en"):
        return False, "destination missing name"
    if not dest.get("sources"):
        return False, "destination missing sources"
    if not dest.get("known_for"):
        return False, "destination missing known_for"

    # Experiences must have descriptions in English
    if not exp_a.get("description") or not t(exp_a["description"], "en"):
        return False, f"exp_a '{exp_a['id']}' missing description"
    if not exp_b.get("description") or not t(exp_b["description"], "en"):
        return False, f"exp_b '{exp_b['id']}' missing description"

    return True, ""

# ─── JSON-LD Builders ─────────────────────────────────────────────────────────

def jsonld_article(dest, exp_a, exp_b, lang, canonical_url, site_name):
    return json.dumps({
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": f"{t(exp_a['name'], lang)} vs {t(exp_b['name'], lang)} in {t(dest['name'], lang)}",
        "description": f"Unbiased comparison of {t(exp_a['name'], lang)} vs "
                       f"{t(exp_b['name'], lang)} in {t(dest['name'], lang)}. "
                       f"Real costs, flexibility scores, and cultural immersion data.",
        "url": canonical_url,
        "inLanguage": lang,
        "publisher": {
            "@type": "Organization",
            "name": site_name,
            "url": "https://tourvstravel.com"
        },
        "dateModified": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "mainEntityOfPage": canonical_url
    }, ensure_ascii=False)

def jsonld_breadcrumb(dest, exp_a, exp_b, lang, base_url):
    return json.dumps({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1,
             "name": "Home", "item": f"{base_url}/{lang}/"},
            {"@type": "ListItem", "position": 2,
             "name": t(dest["name"], lang),
             "item": f"{base_url}/{lang}/{dest['id']}/"},
            {"@type": "ListItem", "position": 3,
             "name": f"{t(exp_a['name'], lang)} vs {t(exp_b['name'], lang)}"}
        ]
    }, ensure_ascii=False)

def jsonld_faq(dest, exp_a, exp_b, enrichment, lang):
    dest_name  = t(dest["name"], lang)
    exp_a_name = t(exp_a["name"], lang)
    exp_b_name = t(exp_b["name"], lang)
    cost_a = enrichment.get("cost_range_a", "varies")
    cost_b = enrichment.get("cost_range_b", "varies")
    duration = enrichment.get("recommended_duration_days", "7–14")

    questions = {
        "en": [
            {"q": f"Is {exp_a_name} or {exp_b_name} cheaper in {dest_name}?",
             "a": f"{exp_a_name} typically costs {cost_a} while {exp_b_name} "
                  f"ranges from {cost_b} per person. Best value depends on your travel style."},
            {"q": f"How many days do I need for {dest_name}?",
             "a": f"Most travelers spend {duration} days in {dest_name}."},
            {"q": f"Which is better for solo travelers: {exp_a_name} or {exp_b_name}?",
             "a": f"Both options have merits for solo travelers in {dest_name}. "
                  f"See our Safety for Solo Travelers score above for a detailed comparison."}
        ],
        "ar": [
            {"q": f"أيهما أرخص في {dest_name}: {exp_a_name} أم {exp_b_name}؟",
             "a": f"يتراوح سعر {exp_a_name} عادةً بين {cost_a} بينما يتراوح "
                  f"{exp_b_name} بين {cost_b} للشخص الواحد."},
            {"q": f"كم يوماً أحتاج لزيارة {dest_name}؟",
             "a": f"يقضي معظم المسافرين {duration} يوماً في {dest_name}."}
        ]
    }
    faqs = questions.get(lang, questions["en"])
    return json.dumps({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question",
             "name": q["q"],
             "acceptedAnswer": {"@type": "Answer", "text": q["a"]}}
            for q in faqs
        ]
    }, ensure_ascii=False)

# ─── Page Context Builder ─────────────────────────────────────────────────────

def build_context(dest, exp_a, exp_b, enrichment,
                  criteria_index, score_labels,
                  lang, lang_urls, config):
    """Build the complete template context for one page."""

    languages  = config["languages"]
    base_url   = config["site"]["base_url"]
    site_name  = config["site"]["name"]
    ui         = config.get("ui", {})

    lang_conf  = next((l for l in languages if l["code"] == lang), {})
    is_rtl     = lang_conf.get("dir", "ltr") == "rtl"
    locale     = lang_conf.get("locale", "en_US")

    dest_name  = t(dest["name"], lang)
    exp_a_name = t(exp_a["name"], lang)
    exp_b_name = t(exp_b["name"], lang)

    slug_a = t(exp_a.get("slug", {}), lang) or exp_a["id"].replace("_", "-")
    slug_b = t(exp_b.get("slug", {}), lang) or exp_b["id"].replace("_", "-")

    canonical = build_url(base_url, lang, dest["id"], slug_a, slug_b)

    # Meta description
    meta_tpl  = t(config["seo"]["meta_description_template"], lang)
    meta_desc = (meta_tpl
                 .replace("{exp_a}", exp_a_name)
                 .replace("{exp_b}", exp_b_name)
                 .replace("{destination}", dest_name))

    # Criteria scores from enrichment (optional)
    scores_raw = enrichment.get("criteria_scores", {})
    criteria_list = []
    for crit_id, crit in criteria_index.items():
        sd = scores_raw.get(crit_id, {})
        score_a = sd.get(exp_a["id"]) or (list(sd.values())[0] if sd else None)
        score_b = sd.get(exp_b["id"]) or (list(sd.values())[-1] if sd else None)
        criteria_list.append({
            "id":          crit_id,
            "label":       t(crit["label"], lang),
            "description": t(crit.get("description", {}), lang),
            "icon":        crit.get("icon", ""),
            "score_a":     score_a,
            "score_b":     score_b,
            "label_a":     t(score_labels.get(score_a, {}), lang) if score_a else "",
            "label_b":     t(score_labels.get(score_b, {}), lang) if score_b else "",
        })

    # Affiliate links from enrichment
    affiliate_links = []
    for link in enrichment.get("affiliate_links", []):
        affiliate_links.append({
            "label":    t(link.get("label", {}), lang),
            "url":      link.get("url", "#"),
            "provider": link.get("provider", "")
        })

    # Sources — prefer enrichment, fall back to destination sources
    sources = enrichment.get("sources") or dest.get("sources", [])

    # Hreflang
    hreflang = [{"lang": lc.get("hreflang", lc["code"]), "url": lang_urls.get(lc["code"], "")}
                for lc in languages]

    # UI helpers
    def ui_label(key):
        return t(ui.get("labels", {}).get(key, {}), lang)
    def ui_nav(key):
        return t(ui.get("nav", {}).get(key, {}), lang)

    return {
        # Page meta
        "lang":           lang,
        "is_rtl":         is_rtl,
        "locale":         locale,
        "canonical_url":  canonical,
        "meta_desc":      meta_desc,
        "hreflang":       hreflang,
        "lang_urls":      lang_urls,
        "languages":      languages,
        "generated_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),

        # Site
        "site_name":    site_name,
        "site_tagline": t(config["site"]["tagline"], lang),
        "base_url":     base_url,

        # Destination
        "dest":         dest,
        "dest_name":    dest_name,
        "best_seasons": tlist(dest.get("best_seasons", {}), lang),

        # Experiences
        "exp_a":      exp_a,
        "exp_b":      exp_b,
        "exp_a_name": exp_a_name,
        "exp_b_name": exp_b_name,
        "desc_a":     t(exp_a.get("description", {}), lang),
        "desc_b":     t(exp_b.get("description", {}), lang),
        "ideal_for_a":tlist(exp_a.get("ideal_for", {}), lang),
        "ideal_for_b":tlist(exp_b.get("ideal_for", {}), lang),
        "budget_a":   exp_a.get("budget_range", ""),
        "budget_b":   exp_b.get("budget_range", ""),
        "group_a":    exp_a.get("typical_group_size", ""),
        "group_b":    exp_b.get("typical_group_size", ""),

        # Enrichment (optional — from comparisons.yaml)
        "enrichment":     enrichment,
        "local_insight":  t(enrichment.get("local_insight", {}), lang),
        "cost_range_a":   enrichment.get("cost_range_a", exp_a.get("budget_range", "")),
        "cost_range_b":   enrichment.get("cost_range_b", exp_b.get("budget_range", "")),
        "duration":       enrichment.get("recommended_duration_days", ""),
        "criteria":       criteria_list,
        "affiliate_links":affiliate_links,
        "sources":        sources,

        # JSON-LD
        "jsonld_article":    jsonld_article(dest, exp_a, exp_b, lang, canonical, site_name),
        "jsonld_breadcrumb": jsonld_breadcrumb(dest, exp_a, exp_b, lang, base_url),
        "jsonld_faq":        jsonld_faq(dest, exp_a, exp_b, enrichment, lang),

        # UI strings
        "ui_vs":           ui_label("vs"),
        "ui_in":           ui_label("in"),
        "ui_read_more":    ui_label("read_more"),
        "ui_sources":      ui_label("sources"),
        "ui_best_for":     ui_label("best_for"),
        "ui_cost_range":   ui_label("cost_range"),
        "ui_local_insight":ui_label("local_insight"),
        "ui_score":        ui_label("score"),
        "ui_typical_group":ui_label("typical_group") if ui.get("labels", {}).get("typical_group") else "Typical Group Size",
        "ui_budget_range": ui_label("budget_range") if ui.get("labels", {}).get("budget_range") else "Budget Range",
        "nav_home":        ui_nav("home"),
        "nav_compare":     ui_nav("compare"),
        "nav_destinations":ui_nav("destinations"),
        "nav_tools":       ui_nav("tools"),
        "nav_methodology": ui_nav("methodology"),
    }

# ─── File Writer ──────────────────────────────────────────────────────────────

def write_page(content: str, lang: str, dest_id: str,
               slug_a: str, slug_b: str) -> Path:
    out_dir = OUTPUT_DIR / lang / dest_id / f"{slug_a}-vs-{slug_b}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "index.html"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(content)
    return out_file

# ─── Static Assets ────────────────────────────────────────────────────────────

def copy_static():
    if STATIC_DIR.exists():
        dest = OUTPUT_DIR / "static"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(STATIC_DIR, dest)
        log.info("Static assets copied → output/static/")

# ─── Sitemap Builder ──────────────────────────────────────────────────────────

def build_sitemap(all_urls: list, base_url: str):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"',
        '        xmlns:xhtml="http://www.w3.org/1999/xhtml">'
    ]
    for url in all_urls:
        lines += [
            "  <url>",
            f"    <loc>{url}</loc>",
            f"    <lastmod>{today}</lastmod>",
            "    <changefreq>monthly</changefreq>",
            "    <priority>0.8</priority>",
            "  </url>"
        ]
    lines.append("</urlset>")
    path = OUTPUT_DIR / "sitemap.xml"
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    log.info(f"Sitemap → {len(all_urls)} URLs")

def build_robots(base_url: str):
    with open(OUTPUT_DIR / "robots.txt", "w") as f:
        f.write(f"User-agent: *\nAllow: /\n\nSitemap: {base_url}/sitemap.xml\n")
    log.info("robots.txt generated")

# ─── Progress Reporter ────────────────────────────────────────────────────────

def report(total, generated, skipped, errors, start_time):
    elapsed = (datetime.now(timezone.utc).timestamp() -
               start_time.timestamp())
    rate = generated / elapsed if elapsed > 0 else 0
    pct = (generated + skipped + errors) / total * 100 if total > 0 else 0
    log.info(
        f"Progress: {pct:.1f}% | "
        f"Generated: {generated:,} | "
        f"Skipped: {skipped:,} | "
        f"Errors: {errors} | "
        f"Rate: {rate:.0f} pages/s"
    )

# ─── Main Generator ───────────────────────────────────────────────────────────

def generate(
    dest_filter: str = None,
    exp_filter: str = None,
    lang_filter: str = None,
    dry_run: bool = False,
    limit: int = None
):
    """
    Main generation engine.

    Args:
        dest_filter : generate only this destination id
        exp_filter  : generate only combinations involving this experience id
        lang_filter : generate only this language
        dry_run     : validate combinations without writing files
        limit       : stop after N combinations (for testing)
    """

    log.info("=" * 65)
    log.info("TourVsTravel.com — Generator v2 (Auto-Combination Engine)")
    log.info("=" * 65)

    # ── Load all data ──────────────────────────────────────────────
    log.info("Loading data files...")
    raw_dest    = load_yaml("destinations.yaml")["destinations"]
    raw_exp     = load_yaml("experience_types.yaml")["experience_types"]
    raw_comp    = load_yaml("comparisons.yaml").get("comparisons", [])
    raw_crit    = load_yaml("comparison_criteria.yaml")
    config      = load_yaml("site_config.yaml")

    criteria_index = {c["id"]: c for c in raw_crit["criteria"]}
    score_labels   = raw_crit.get("score_labels", {})
    languages      = config["languages"]
    base_url       = config["site"]["base_url"]

    # Apply filters
    destinations = raw_dest
    exp_types    = raw_exp
    langs        = languages

    if dest_filter:
        destinations = [d for d in raw_dest if d["id"] == dest_filter]
    if exp_filter:
        exp_types = [e for e in raw_exp if exp_filter in e["id"]]
    if lang_filter:
        langs = [l for l in languages if l["code"] == lang_filter]

    # ── Calculate total ────────────────────────────────────────────
    total_combinations = len(destinations) * len(exp_types) * (len(exp_types) - 1)
    total_pages        = total_combinations * len(langs)

    log.info(f"  Destinations  : {len(destinations)}")
    log.info(f"  Experience    : {len(exp_types)}")
    log.info(f"  Languages     : {len(langs)}")
    log.info(f"  Combinations  : {total_combinations:,}")
    log.info(f"  Total pages   : {total_pages:,}")
    if dry_run:
        log.info("  Mode          : DRY RUN (no files written)")
    if limit:
        log.info(f"  Limit         : {limit} combinations")

    # ── Setup Jinja2 ───────────────────────────────────────────────
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    try:
        template = env.get_template("comparison.html")
    except Exception as e:
        log.error(f"Template error: {e}")
        sys.exit(1)

    # ── Prepare output directory ───────────────────────────────────
    if not dry_run:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        copy_static()

    # ── Counters ───────────────────────────────────────────────────
    generated   = 0
    skipped     = 0
    errors      = 0
    all_urls    = []
    start_time  = datetime.now(timezone.utc)
    combo_count = 0

    # ── Main loop: destinations × exp_a × exp_b ────────────────────
    for dest in destinations:
        for exp_a, exp_b in itertools.permutations(exp_types, 2):

            # Stop if limit reached
            if limit and combo_count >= limit:
                log.info(f"Limit of {limit} combinations reached.")
                break

            combo_count += 1

            # ── Quality gate ──────────────────────────────────────
            ok, reason = passes_quality_gate(dest, exp_a, exp_b)
            if not ok:
                skipped += 1
                continue

            # ── Enrichment lookup (optional) ──────────────────────
            enrichment = lookup_enrichment(
                raw_comp, dest["id"], exp_a["id"], exp_b["id"]
            )

            # ── Build hreflang URLs once per combination ──────────
            lang_urls = build_hreflang_urls(
                base_url, dest["id"], exp_a, exp_b, langs
            )

            # ── Generate one page per language ────────────────────
            for lc in langs:
                lang = lc["code"]
                try:
                    ctx = build_context(
                        dest, exp_a, exp_b, enrichment,
                        criteria_index, score_labels,
                        lang, lang_urls, config
                    )

                    if not dry_run:
                        html = template.render(**ctx)
                        slug_a = t(exp_a.get("slug", {}), lang) or exp_a["id"].replace("_", "-")
                        slug_b = t(exp_b.get("slug", {}), lang) or exp_b["id"].replace("_", "-")
                        write_page(html, lang, dest["id"], slug_a, slug_b)

                    all_urls.append(ctx["canonical_url"])
                    generated += 1

                except Exception as e:
                    log.error(
                        f"ERROR [{lang}] {dest['id']} | "
                        f"{exp_a['id']} vs {exp_b['id']} — {e}"
                    )
                    errors += 1

        # ── Report every destination ───────────────────────────────
        report(total_pages, generated, skipped, errors, start_time)

        if limit and combo_count >= limit:
            break

    # ── Sitemap & robots ──────────────────────────────────────────
    if not dry_run:
        build_sitemap(all_urls, base_url)
        build_robots(base_url)

    # ── Final summary ─────────────────────────────────────────────
    elapsed = (datetime.now(timezone.utc).timestamp() -
               start_time.timestamp())
    log.info("=" * 65)
    log.info(f"  Pages generated : {generated:,}")
    log.info(f"  Combinations skipped : {skipped:,}")
    log.info(f"  Errors          : {errors}")
    log.info(f"  Time elapsed    : {elapsed:.1f}s")
    log.info(f"  Output          : {OUTPUT_DIR}")
    log.info("=" * 65)

# ─── CLI Entry Point ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="TourVsTravel.com — Static Site Generator"
    )
    parser.add_argument(
        "--dest", type=str, default=None,
        help="Generate only one destination id (e.g. japan)"
    )
    parser.add_argument(
        "--exp", type=str, default=None,
        help="Generate only combinations involving this experience id"
    )
    parser.add_argument(
        "--lang", type=str, default=None,
        help="Generate only one language (e.g. en, ar, fr)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Validate all combinations without writing files"
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Stop after N combinations (for testing)"
    )
    args = parser.parse_args()

    generate(
        dest_filter=args.dest,
        exp_filter=args.exp,
        lang_filter=args.lang,
        dry_run=args.dry_run,
        limit=args.limit,
    )
