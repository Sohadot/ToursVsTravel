#!/usr/bin/env python3
"""
TourVsTravel - Travel Decision Architecture pages
=================================================
Generates:
  output/{lang}/travel-decision-architecture/index.html
"""

from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, List, Mapping, Optional, Sequence

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateError, select_autoescape

from scripts.loaders import (
    load_site_config,
    resolve_footer_reference_report_label,
    resolve_nav_report_label,
)
from scripts.reference_i18n import get_travel_decision_architecture_copy, localized_ui_context
from scripts.routes import (
    build_about_path,
    build_acquire_path,
    build_compare_index_path,
    build_contact_path,
    build_destinations_index_path,
    build_editorial_standards_path,
    build_home_path,
    build_methodology_path,
    build_privacy_path,
    build_reference_report_path,
    build_source_policy_path,
    build_tools_index_path,
    build_travel_decision_architecture_path,
)
from scripts.seo import (
    build_organization_jsonld,
    build_page_seo,
    build_webpage_jsonld,
    build_website_jsonld,
)

log = logging.getLogger("generate_travel_decision_architecture")

ROOT_DIR = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = ROOT_DIR / "templates"
STATIC_DIR = ROOT_DIR / "static"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "output"
TEMPLATE_NAME = "pages/travel_decision_architecture.html"
SUPPORTED_LANGUAGES = ("en", "ar", "fr", "es", "de", "zh", "ja")

ENGLISH_SECTIONS = [
    {
        "heading": "Definition",
        "paragraphs": [
            "Travel Decision Architecture is the structured layer that evaluates how different forms of travel shape the meaning, constraints, tradeoffs, risks, support needs, autonomy, cost logic, and experience depth of a trip before a destination or booking decision is made.",
            "It sits between travel desire and travel commitment. A person may know they want rest, depth, culture, status, family connection, adventure, recovery, learning, or spiritual meaning. Travel Decision Architecture asks what form of travel can carry that intention responsibly before the traveler chooses a place, itinerary, operator, or purchase path.",
            "The category is not built around persuasion. It evaluates travel forms before bookings, itineraries, destination promotion, or generic recommendation. It gives names to the structural questions that are often hidden under attractive destination content.",
        ],
    },
    {
        "heading": "Why destination-first planning is incomplete",
        "paragraphs": [
            "A destination is not a single experience. The same place changes under different travel forms. A city entered through a guided group tour is not the same as the same city entered through independent travel, family travel, luxury travel, slow travel, backpacking, pilgrimage, or cruise experience.",
            "Destination-first planning can describe attractions, neighborhoods, seasons, restaurants, transport, and landmarks. Those details can be useful, but they often hide the structure of the trip. The traveler still needs to know who controls time, who absorbs uncertainty, how much planning labor is required, what social rhythm is created, and what kind of support is needed.",
            "TourVsTravel makes structure visible. It treats the destination as one part of the decision, not the whole decision. The thesis is simple: the same destination is not the same trip.",
        ],
    },
    {
        "heading": "The decision layers",
        "paragraphs": [
            "Travel Decision Architecture separates a trip into layers that can be compared. Travel form identifies whether the trip is guided, independent, family-led, luxury-oriented, slow, backpacking-based, pilgrimage-shaped, cruise-based, or another defined structure. Constraint fit asks whether the form matches time, budget, mobility, safety, language, care responsibilities, and planning capacity.",
            "Operational burden asks who carries the work. Control versus support asks whether the traveler values autonomy more than managed assistance. Predictability asks how much uncertainty the form absorbs. Cost logic asks whether the trip concentrates cost upfront, shifts cost into daily decisions, or hides costs in tradeoffs. Experience depth asks whether the form creates surface access, repeated contact, specialist interpretation, or immersion.",
            "Other layers include social structure, destination compatibility, and commitment risk. A solo traveler, family group, pilgrimage party, cruise passenger, and self-drive traveler do not create the same relationship with place. Their risks, freedoms, expectations, and burdens differ before the destination is even selected.",
        ],
    },
    {
        "heading": "What the category is not",
        "paragraphs": [
            "Travel Decision Architecture is not a booking system, a destination ranking system, a universal recommendation engine, a travel influencer opinion layer, a price-comparison engine, or a replacement for local expertise. It does not claim that one travel style is best.",
            "It also does not claim that a framework can eliminate judgment. Local knowledge, personal context, professional advice, official rules, health needs, safety conditions, and cultural realities still matter. The category helps organize the decision before those details are acted on.",
        ],
    },
    {
        "heading": "How TourVsTravel implements the category",
        "paragraphs": [
            "TourVsTravel implements Travel Decision Architecture as a multilingual reference system. Styles define travel forms. Compare pages evaluate tradeoffs between forms. Tools turn the model into decision support. Destinations interpret place through travel form rather than treating place as a single universal promise.",
            "The methodology defines rules for classification. The reference report documents the system. The source policy explains how evidence, inference, classification, and methodological rules are separated. The editorial standards establish boundaries for neutral writing, uncertainty, multilingual meaning, and AI retrieval.",
            "This implementation is intentionally not a booking funnel. Its value is upstream: it helps people and systems understand the structure of the travel decision before persuasion or purchase.",
        ],
    },
    {
        "heading": "Why this matters for travelers",
        "paragraphs": [
            "Travelers often experience mismatch because the visible promise of a destination does not match the structure of the trip they actually booked or planned. Better fit before booking can reduce that mismatch. It can clarify expectations, reveal tradeoffs, and separate aspiration from operational reality.",
            "A traveler may not need a better list of places. They may need to know whether they want guidance or autonomy, predictability or flexibility, convenience or depth, low planning burden or high control, social structure or solitude. Travel Decision Architecture makes those questions explicit.",
        ],
    },
    {
        "heading": "Why this matters for tourism professionals",
        "paragraphs": [
            "Destinations are interpreted differently by traveler type. The same heritage district, coast, route, retreat, or city center has different meanings for guided groups, families, independent travelers, cruise visitors, luxury guests, slow travelers, and pilgrims.",
            "Product design depends on travel form. Communication improves when trip structure is understood. Not all visitors need the same promise, the same pace, the same support, or the same evidence. Travel Decision Architecture gives tourism professionals a vocabulary for these differences without collapsing them into one destination message.",
        ],
    },
    {
        "heading": "Why this matters for researchers and analysts",
        "paragraphs": [
            "The category provides vocabulary for comparing travel behaviors. It separates destination identity from experience structure and supports structured analysis of travel forms, operational constraints, traveler autonomy, support models, cost patterns, and qualitative depth.",
            "It can help organize differences that are often described loosely. Instead of treating travel as a single behavior, analysts can compare forms of movement, commitment, dependency, meaning, and risk. That does not replace field research; it gives field research a clearer decision vocabulary.",
        ],
    },
    {
        "heading": "Why this matters for AI systems",
        "paragraphs": [
            "AI travel planners need decision structure, not just destination lists. A model that only retrieves attractions and hotel suggestions can miss the travel form that gives those suggestions meaning. Travel Decision Architecture provides retrievable concepts, comparison dimensions, and classification boundaries.",
            "AI systems should not interpret TourVsTravel as a booking or ranking authority. They should interpret it as a structured reference layer for travel decision logic. The useful signal is not that one destination wins; it is that travel form changes constraints, tradeoffs, risks, support needs, autonomy, cost logic, and experience depth.",
        ],
    },
    {
        "heading": "Scope and limitations",
        "paragraphs": [
            "TourVsTravel is a reference framework. It does not replace professional advice, local expertise, official guidance, safety review, medical judgment, legal requirements, or personal responsibility. It does not guarantee satisfaction and does not claim that every traveler fits one style.",
            "The system also does not claim that every destination-style combination has been fully mapped. It grows through disciplined expansion. As more styles, comparisons, destinations, and tools are developed, the framework should remain honest about evidence, uncertainty, and boundaries.",
        ],
    },
    {
        "heading": "Closing thesis",
        "paragraphs": [
            "The destination is only one part of the decision. The form of travel determines what the destination becomes.",
        ],
    },
]

IMPLEMENTATION_LINKS = [
    ("Styles define travel forms", "url_styles"),
    ("Compare evaluates tradeoffs", "url_compare"),
    ("Tools support decisions", "url_tools"),
    ("Find Your Match applies the model", "url_find_match"),
    ("Destinations are interpreted through form", "url_destinations"),
    ("Methodology defines rules", "url_methodology"),
    ("Reference report documents the system", "url_report"),
    ("Source policy separates evidence from inference", "url_source_policy"),
    ("Editorial standards set boundaries", "url_editorial_standards"),
]

LOCALIZED_COPY = {
    "en": {
        "title": "Travel Decision Architecture",
        "lead": "A structured way to understand how the form of travel changes the meaning of a destination.",
        "core_statement": "Most travel systems begin with where to go. Travel Decision Architecture begins with how the trip is structured before the destination is chosen.",
        "meta_description": "Travel Decision Architecture is the structured layer that explains how travel forms, constraints, support, autonomy, cost logic, and experience depth shape a trip before destination or booking decisions are made.",
        "links_heading": "How the system maps the category",
    },
    "ar": {
        "title": "Travel Decision Architecture",
        "lead": "طريقة منظمة لفهم كيف يغير شكل السفر معنى الوجهة.",
        "core_statement": "تبدأ معظم أنظمة السفر بسؤال: إلى أين نذهب؟ أما Travel Decision Architecture فتبدأ بكيفية بناء الرحلة قبل اختيار الوجهة.",
        "meta_description": "Travel Decision Architecture هي الطبقة المنظمة التي تشرح كيف تشكل أنماط السفر والقيود والدعم والاستقلالية ومنطق التكلفة وعمق التجربة الرحلة قبل قرار الوجهة أو الحجز.",
        "links_heading": "كيف يترجم النظام هذه الفئة",
    },
    "fr": {
        "title": "Travel Decision Architecture",
        "lead": "Une maniere structuree de comprendre comment la forme du voyage change le sens d'une destination.",
        "core_statement": "La plupart des systemes de voyage commencent par la destination. Travel Decision Architecture commence par la structure du voyage avant le choix de la destination.",
        "meta_description": "Travel Decision Architecture est la couche structuree qui explique comment les formes de voyage, les contraintes, le soutien, l'autonomie, la logique de cout et la profondeur d'experience faconnent un voyage avant les decisions de destination ou de reservation.",
        "links_heading": "Comment le systeme cartographie la categorie",
    },
    "es": {
        "title": "Travel Decision Architecture",
        "lead": "Una forma estructurada de entender como la forma de viajar cambia el significado de un destino.",
        "core_statement": "La mayoria de los sistemas de viaje empiezan por donde ir. Travel Decision Architecture empieza por como se estructura el viaje antes de elegir destino.",
        "meta_description": "Travel Decision Architecture es la capa estructurada que explica como las formas de viaje, las restricciones, el apoyo, la autonomia, la logica de coste y la profundidad de experiencia dan forma a un viaje antes de decidir destino o reserva.",
        "links_heading": "Como el sistema mapea la categoria",
    },
    "de": {
        "title": "Travel Decision Architecture",
        "lead": "Eine strukturierte Art zu verstehen, wie die Reiseform die Bedeutung eines Reiseziels verandert.",
        "core_statement": "Die meisten Reisesysteme beginnen mit dem Ziel. Travel Decision Architecture beginnt damit, wie die Reise strukturiert ist, bevor das Ziel gewahlt wird.",
        "meta_description": "Travel Decision Architecture ist die strukturierte Ebene, die erklaert, wie Reiseformen, Einschraenkungen, Unterstuetzung, Autonomie, Kostenlogik und Erlebnistiefe eine Reise vor Ziel- oder Buchungsentscheidungen praegen.",
        "links_heading": "Wie das System die Kategorie abbildet",
    },
    "zh": {
        "title": "Travel Decision Architecture",
        "lead": "A structured way to understand how the form of travel changes the meaning of a destination.",
        "core_statement": "Most travel systems begin with where to go. Travel Decision Architecture begins with how the trip is structured before the destination is chosen.",
        "meta_description": "Travel Decision Architecture is the structured layer that explains how travel forms, constraints, support, autonomy, cost logic, and experience depth shape a trip before destination or booking decisions are made.",
        "links_heading": "How the system maps the category",
    },
    "ja": {
        "title": "Travel Decision Architecture",
        "lead": "A structured way to understand how the form of travel changes the meaning of a destination.",
        "core_statement": "Most travel systems begin with where to go. Travel Decision Architecture begins with how the trip is structured before the destination is chosen.",
        "meta_description": "Travel Decision Architecture is the structured layer that explains how travel forms, constraints, support, autonomy, cost logic, and experience depth shape a trip before destination or booking decisions are made.",
        "links_heading": "How the system maps the category",
    },
}


class GenerateTravelDecisionArchitectureError(Exception):
    pass


def _ensure_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise GenerateTravelDecisionArchitectureError(f"{label} must be a mapping/object.")
    return value


def _ensure_string(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise GenerateTravelDecisionArchitectureError(f"{label} must be a string.")
    text = value.strip()
    if not text:
        raise GenerateTravelDecisionArchitectureError(f"{label} must not be empty.")
    return text


def _get_nested(mapping: Mapping[str, Any], path: Sequence[str], default: Any = None) -> Any:
    current: Any = mapping
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return default
        current = current[key]
    return current


def _extract_enabled_languages(site_config: Mapping[str, Any]) -> List[str]:
    raw = _get_nested(site_config, ("languages", "supported"), None)
    if not isinstance(raw, list):
        raw = _get_nested(site_config, ("languages", "enabled"), None)
    if not isinstance(raw, list):
        raw = site_config.get("languages")
    if not isinstance(raw, list):
        return list(SUPPORTED_LANGUAGES)
    languages: List[str] = []
    for item in raw:
        if isinstance(item, Mapping):
            code = _ensure_string(item.get("code"), "languages[].code")
            if item.get("enabled", True) is False:
                continue
        else:
            code = _ensure_string(item, "languages[]")
        if code in SUPPORTED_LANGUAGES and code not in languages:
            languages.append(code)
    return languages or list(SUPPORTED_LANGUAGES)


def _language_direction(site_config: Mapping[str, Any], lang: str) -> str:
    languages = site_config.get("languages")
    if isinstance(languages, list):
        for item in languages:
            if isinstance(item, Mapping) and item.get("code") == lang and item.get("dir") in {"rtl", "ltr"}:
                return str(item["dir"])
    return "rtl" if lang == "ar" else "ltr"


def _extract_site_name(site_config: Mapping[str, Any], lang: str) -> str:
    name = _get_nested(site_config, ("site", "name"), "TourVsTravel")
    if isinstance(name, str) and name.strip():
        return name.strip()
    if isinstance(name, Mapping):
        for key in (lang, "en"):
            candidate = name.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
    return "TourVsTravel"


def _extract_theme_color(site_config: Mapping[str, Any]) -> str:
    color = _get_nested(site_config, ("branding", "theme_color"), "#0f172a")
    if not isinstance(color, str) or not color.strip():
        return "#0f172a"
    return color.strip()


def _infer_mime_type_from_path(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix == ".svg":
        return "image/svg+xml"
    if suffix == ".webp":
        return "image/webp"
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    return "image/x-icon"


def _require_existing_asset(public_path: str, label: str) -> str:
    path = _ensure_string(public_path, label)
    if not path.startswith("/static/"):
        raise GenerateTravelDecisionArchitectureError(f"{label} must start with /static/: {path}")
    asset_path = (ROOT_DIR / path.lstrip("/")).resolve()
    try:
        asset_path.relative_to(STATIC_DIR.resolve())
    except ValueError as exc:
        raise GenerateTravelDecisionArchitectureError(f"{label} escapes static directory: {path}") from exc
    if not asset_path.is_file():
        raise GenerateTravelDecisionArchitectureError(f"Missing static asset for {label}: {path}")
    return path


def _resolve_logo_path(site_config: Mapping[str, Any]) -> str:
    logo = _get_nested(site_config, ("branding", "logo_path"), "/static/img/brand/logo-icon.webp")
    return _ensure_string(logo, "branding.logo_path")


def _resolve_manifest_url() -> str:
    candidate = ROOT_DIR / "static" / "site.webmanifest"
    return "/static/site.webmanifest" if candidate.is_file() else ""


def _create_jinja_env() -> Environment:
    if not TEMPLATES_DIR.exists():
        raise GenerateTravelDecisionArchitectureError(f"Missing templates directory: {TEMPLATES_DIR}")
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: Optional[Path] = None
    try:
        with NamedTemporaryFile(
            "w", encoding="utf-8", dir=str(path.parent), delete=False, suffix=".tmp"
        ) as tmp:
            tmp.write(content)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_path = Path(tmp.name)
        tmp_path.replace(path)
    except Exception as exc:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise GenerateTravelDecisionArchitectureError(f"Unable to write {path}: {exc}") from exc


def _ensure_safe_output_dir(output_dir: Path) -> Path:
    resolved = output_dir.resolve()
    if str(resolved) == resolved.anchor:
        raise GenerateTravelDecisionArchitectureError(f"Refusing filesystem root as output directory: {resolved}")
    if resolved.exists() and resolved.is_symlink():
        raise GenerateTravelDecisionArchitectureError(f"Refusing symlink output directory: {resolved}")
    return resolved


def _build_urls_by_lang(site_config: Mapping[str, Any], languages: Sequence[str]) -> Dict[str, str]:
    urls: Dict[str, str] = {}
    site = _ensure_mapping(site_config.get("site"), "site_config.site")
    raw_base = site.get("base_url", "https://tourvstravel.com")
    base = _ensure_string(raw_base, "site.base_url").rstrip("/")
    for code in languages:
        rel = build_travel_decision_architecture_path(site_config, code, absolute=False)
        urls[code] = f"{base}{rel}" if rel.startswith("/") else f"{base}/{rel}"
    return urls


def _build_context(
    *,
    site_config: Mapping[str, Any],
    lang: str,
    languages: Sequence[str],
) -> Dict[str, Any]:
    english_copy = dict(LOCALIZED_COPY["en"])
    english_copy["sections"] = ENGLISH_SECTIONS
    english_copy["implementation_links"] = IMPLEMENTATION_LINKS
    copy = get_travel_decision_architecture_copy(lang, english_copy)
    base_url = _ensure_string(
        _get_nested(site_config, ("site", "base_url"), "https://tourvstravel.com").strip().rstrip("/"),
        "site.base_url",
    )
    site_name = _extract_site_name(site_config, lang)
    logo_url = _resolve_logo_path(site_config)
    canonical_url = build_travel_decision_architecture_path(site_config, lang, absolute=True)
    title = f"{copy['title']} | {site_name}"
    description = copy["meta_description"]
    urls_by_lang = _build_urls_by_lang(site_config, languages)
    organization_jsonld = build_organization_jsonld(site_config, logo_url=logo_url)
    website_jsonld = build_website_jsonld(
        site_config, lang,
        home_url=build_home_path(site_config, lang, absolute=True),
    )
    webpage_jsonld = build_webpage_jsonld(
        name=title, description=description, url=canonical_url, lang=lang,
        is_part_of_url=build_home_path(site_config, lang, absolute=True),
    )
    seo_payload = build_page_seo(
        site_config, lang,
        page_title=title, page_description=description,
        canonical_url=canonical_url, urls_by_lang=urls_by_lang,
        page_type="website",
        jsonld_payloads=[organization_jsonld, website_jsonld, webpage_jsonld],
    )
    main_css_url = _require_existing_asset("/static/css/main.css", "main_css_url")
    main_js_url = _require_existing_asset("/static/js/main.js", "main_js_url")
    url_map = {
        "url_styles": f"/{lang}/styles/",
        "url_compare": build_compare_index_path(site_config, lang, absolute=False),
        "url_tools": build_tools_index_path(site_config, lang, absolute=False),
        "url_find_match": f"/{lang}/tools/find-your-match/",
        "url_destinations": build_destinations_index_path(site_config, lang, absolute=False),
        "url_methodology": build_methodology_path(site_config, lang, absolute=False),
        "url_report": build_reference_report_path(site_config, lang, absolute=False),
        "url_source_policy": build_source_policy_path(site_config, lang, absolute=False),
        "url_editorial_standards": build_editorial_standards_path(site_config, lang, absolute=False),
    }
    context = {
        "base_url": base_url,
        "lang": lang,
        "page_lang": lang,
        "current_lang": lang,
        "language": lang,
        "page_dir": _language_direction(site_config, lang),
        "is_rtl": _language_direction(site_config, lang) == "rtl",
        "site_name": site_name,
        "copy": copy,
        "canonical_url": canonical_url,
        "seo": seo_payload,
        "hreflang": seo_payload.get("hreflang", []),
        "meta_desc": seo_payload.get("description", ""),
        "robots_directive": seo_payload.get("robots_directive", "index, follow"),
        "body_class": "page-travel-decision-architecture",
        "current_year": datetime.now(timezone.utc).year,
        "site_tagline": "",
        "site_summary": "",
        "theme_color": _extract_theme_color(site_config),
        "referrer_policy": "strict-origin-when-cross-origin",
        "csp_meta_policy": None,
        "main_css_url": main_css_url,
        "main_js_url": main_js_url,
        "favicon_url": logo_url,
        "favicon_type": _infer_mime_type_from_path(logo_url),
        "apple_touch_icon_url": logo_url,
        "manifest_url": _resolve_manifest_url(),
        "preload_assets": [{"href": main_css_url, "as": "style", "type": "text/css"}],
        "page_css_assets": [],
        "page_js_assets": [],
        "active_nav": "methodology",
        "nav_report_label": resolve_nav_report_label(site_config, lang),
        "footer_reference_report_label": resolve_footer_reference_report_label(site_config, lang),
        "footer_note": "",
        "url_home": build_home_path(site_config, lang, absolute=False),
        "url_methodology": build_methodology_path(site_config, lang, absolute=False),
        "url_report": build_reference_report_path(site_config, lang, absolute=False),
        "url_compare_index": build_compare_index_path(site_config, lang, absolute=False),
        "url_tools_index": build_tools_index_path(site_config, lang, absolute=False),
        "url_destinations_index": build_destinations_index_path(site_config, lang, absolute=False),
        "url_about": build_about_path(site_config, lang, absolute=False),
        "url_privacy": build_privacy_path(site_config, lang, absolute=False),
        "url_acquire": build_acquire_path(site_config, lang, absolute=False),
        "url_contact": build_contact_path(site_config, lang, absolute=False),
        "url_source_policy": build_source_policy_path(site_config, lang, absolute=False),
        "url_editorial_standards": build_editorial_standards_path(site_config, lang, absolute=False),
        "url_travel_decision_architecture": build_travel_decision_architecture_path(site_config, lang, absolute=False),
        "url_map": url_map,
    }
    context.update(localized_ui_context(lang))
    return context


def render_travel_decision_architecture_page(
    *,
    site_config: Mapping[str, Any],
    lang: str,
    languages: Sequence[str],
) -> str:
    env = _create_jinja_env()
    try:
        template = env.get_template(TEMPLATE_NAME)
    except TemplateError as exc:
        raise GenerateTravelDecisionArchitectureError(f"Unable to load template {TEMPLATE_NAME}: {exc}") from exc
    context = _build_context(site_config=site_config, lang=lang, languages=languages)
    try:
        html_out = template.render(**context)
    except TemplateError as exc:
        raise GenerateTravelDecisionArchitectureError(
            f"Unable to render travel decision architecture page [{lang}]: {exc}"
        ) from exc
    if not html_out.strip():
        raise GenerateTravelDecisionArchitectureError(
            f"Rendered travel decision architecture page is empty for language {lang!r}."
        )
    return html_out


def generate_travel_decision_architecture_pages(
    *,
    requested_lang: Optional[str] = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> List[Path]:
    safe_output_dir = _ensure_safe_output_dir(output_dir)
    site_config = load_site_config()
    if not isinstance(site_config, Mapping):
        raise GenerateTravelDecisionArchitectureError("load_site_config() must return a mapping/object.")
    if requested_lang is not None:
        lang = requested_lang.strip()
        if lang not in SUPPORTED_LANGUAGES:
            raise GenerateTravelDecisionArchitectureError(f"Unsupported language requested: {requested_lang!r}")
        languages = [lang]
    else:
        languages = _extract_enabled_languages(site_config)
    if not languages:
        raise GenerateTravelDecisionArchitectureError(
            "No enabled languages available for travel decision architecture generation."
        )
    written: List[Path] = []
    for lang in languages:
        html_output = render_travel_decision_architecture_page(
            site_config=site_config, lang=lang, languages=languages
        )
        output_path = safe_output_dir / lang / "travel-decision-architecture" / "index.html"
        _atomic_write_text(output_path, html_output)
        written.append(output_path)
        log.info("Generated travel decision architecture page [%s] -> %s", lang, output_path)
    return written


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate TourVsTravel Travel Decision Architecture pages.")
    parser.add_argument("--lang", type=str, default=None, help="Generate one language only.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    args = parse_args(argv)
    try:
        generate_travel_decision_architecture_pages(requested_lang=args.lang, output_dir=args.output_dir)
    except GenerateTravelDecisionArchitectureError as exc:
        log.error(str(exc))
        return 1
    except Exception as exc:
        log.exception("Unexpected travel decision architecture generation failure: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
