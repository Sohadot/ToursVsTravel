#!/usr/bin/env python3
"""
TourVsTravel — Reference Report Page Generator
==============================================

Emits the multilingual institutional Reference Report:

    /{lang}/report/

This page consolidates the public reference system: ontology, comparison layer,
tools, destination interpretation, methodology, and current scope.
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Sequence

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateError, select_autoescape

from scripts.loaders import (
    load_comparison_criteria,
    load_experience_types,
    load_site_config,
    resolve_footer_reference_report_label,
    resolve_nav_report_label,
)
from scripts.routes import (
    build_compare_index_path,
    build_destinations_index_path,
    build_experience_type_path,
    build_home_path,
    build_methodology_path,
    build_reference_report_path,
    build_tools_index_path,
)
from scripts.i18n import build_absolute_url

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("generate_report")

ROOT_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT_DIR / "static"
TEMPLATES_DIR = ROOT_DIR / "templates"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "output"
TEMPLATE_NAME = "pages/report.html"
SUPPORTED_LANGUAGES = ("en", "ar", "fr", "es", "de", "zh", "ja")

SECTION_ORDER = (
    "what",
    "why_how",
    "styles",
    "criteria",
    "tools",
    "destinations",
    "methodology",
    "scope",
)


class GenerateReportError(Exception):
    """Raised when reference report generation fails."""


class ReportConfigError(GenerateReportError):
    """Raised when report configuration is invalid."""


class ReportRenderError(GenerateReportError):
    """Raised when report rendering fails."""


class ReportWriteError(GenerateReportError):
    """Raised when report output writing fails."""


def _clean_string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _get_nested(mapping: Mapping[str, Any], path: Sequence[str], default: Any = None) -> Any:
    cur: Any = mapping
    for key in path:
        if not isinstance(cur, Mapping) or key not in cur:
            return default
        cur = cur[key]
    return cur


def _extract_enabled_languages(site_config: Mapping[str, Any]) -> List[str]:
    raw = _get_nested(site_config, ("languages", "supported"), None)
    if not isinstance(raw, list):
        raw = _get_nested(site_config, ("languages", "enabled"), None)
    if not isinstance(raw, list):
        languages = list(site_config.get("languages", []))
        if isinstance(languages, list):
            out: List[str] = []
            for item in languages:
                if not isinstance(item, Mapping):
                    continue
                code = _clean_string(item.get("code"))
                if item.get("enabled", True) is False:
                    continue
                if code in SUPPORTED_LANGUAGES and code not in out:
                    out.append(code)
            return out or list(SUPPORTED_LANGUAGES)
        return list(SUPPORTED_LANGUAGES)
    languages: List[str] = []
    for item in raw:
        code = _clean_string(item.get("code") if isinstance(item, Mapping) else item)
        if isinstance(item, Mapping) and item.get("enabled", True) is False:
            continue
        if code in SUPPORTED_LANGUAGES and code not in languages:
            languages.append(code)
    return languages or list(SUPPORTED_LANGUAGES)


def _language_direction(site_config: Mapping[str, Any], lang: str) -> str:
    direction = _get_nested(site_config, ("languages", "direction", lang), None)
    if direction in {"rtl", "ltr"}:
        return str(direction)
    return "rtl" if lang == "ar" else "ltr"


def _normalize_https_base_url(site_config: Mapping[str, Any]) -> str:
    raw = _clean_string(_get_nested(site_config, ("site", "base_url"), "") or _get_nested(site_config, ("site", "domain"), ""))
    if not raw:
        raise ReportConfigError("site.base_url (or site.domain) missing.")
    if raw.startswith("//"):
        raw = f"https:{raw}"
    if not raw.startswith(("http://", "https://")):
        raw = f"https://{raw}"
    if not raw.startswith("https://"):
        raise ReportConfigError(f"site base URL must be HTTPS: {raw!r}")
    from urllib.parse import urlparse

    parsed = urlparse(raw)
    if not parsed.netloc:
        raise ReportConfigError(f"site.base_url invalid: {raw!r}")
    return f"https://{parsed.netloc.rstrip('/')}"


def _extract_site_name(site_config: Mapping[str, Any], lang: str) -> str:
    name = _get_nested(site_config, ("site", "name"), "TourVsTravel")
    if isinstance(name, Mapping):
        return _clean_string(name.get(lang) or name.get("en")) or "TourVsTravel"
    return _clean_string(name) or "TourVsTravel"


def _localized(value: Any, lang: str, *, default: str = "") -> str:
    if isinstance(value, Mapping):
        return _clean_string(value.get(lang) or value.get("en")) or default
    return _clean_string(value) or default


def _resolve_logo_path(site_config: Mapping[str, Any]) -> str:
    logo = _get_nested(site_config, ("branding", "logo", "icon_path"), "/static/img/brand/logo-icon.webp")
    return _clean_string(logo) or "/static/img/brand/logo-icon.webp"


def _extract_theme_color(site_config: Mapping[str, Any]) -> str:
    for path in (("seo", "theme_color"), ("branding", "colors", "primary_blue")):
        v = _get_nested(site_config, path, None)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return "#002B49"


def _infer_mime_type_from_path(path: str) -> str:
    lower = path.lower()
    if lower.endswith(".webp"):
        return "image/webp"
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith(".svg"):
        return "image/svg+xml"
    return "image/webp"


def _resolve_manifest_url() -> str:
    return ""


def _require_existing_asset(public_path: str, label: str) -> str:
    if not public_path.startswith("/static/"):
        raise ReportConfigError(f"{label} must start with /static/: {public_path}")
    asset_path = (ROOT_DIR / public_path.lstrip("/")).resolve()
    try:
        asset_path.relative_to(STATIC_DIR.resolve())
    except ValueError as exc:
        raise ReportConfigError(f"{label} points outside static/: {public_path}") from exc
    if not asset_path.is_file():
        raise ReportConfigError(f"{label} points to a missing static asset: {public_path}")
    return public_path


def _language_locales(site_config: Mapping[str, Any], lang: str) -> tuple[Optional[str], List[str]]:
    langs = site_config.get("languages")
    if not isinstance(langs, list):
        return None, []
    locale_current: Optional[str] = None
    alternates: List[str] = []
    hreflang_by_code: Dict[str, str] = {}
    for item in langs:
        if not isinstance(item, Mapping):
            continue
        code = _clean_string(item.get("code"))
        href = _clean_string(item.get("hreflang"))
        if code and href:
            hreflang_by_code[code] = href
    for item in langs:
        if not isinstance(item, Mapping):
            continue
        code = _clean_string(item.get("code"))
        loc = item.get("locale")
        if code == lang and isinstance(loc, str) and loc.strip():
            locale_current = loc.strip()
    for item in langs:
        if not isinstance(item, Mapping):
            continue
        code = _clean_string(item.get("code"))
        loc = item.get("locale")
        if code != lang and isinstance(loc, str) and loc.strip():
            alternates.append(loc.strip())
    return locale_current, alternates


def _build_hreflang(site_config: Mapping[str, Any], languages: Sequence[str]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for code in languages:
        rel = build_reference_report_path(site_config, code, absolute=False)
        rows.append({"lang": code, "url": build_absolute_url(site_config, rel)})
    return rows


def _merge_og_locales(site_config: Mapping[str, Any], lang: str) -> tuple[Optional[str], List[str]]:
    return _language_locales(site_config, lang)


def _build_seo_payload(
    *,
    site_config: Mapping[str, Any],
    lang: str,
    title: str,
    description: str,
    canonical_url: str,
    base_url: str,
    site_name: str,
    logo_url: str,
    languages: Sequence[str],
) -> Dict[str, Any]:
    locale, alternate_locales = _merge_og_locales(site_config, lang)
    jsonld = [
        json.dumps(
            {
                "@context": "https://schema.org",
                "@type": "WebPage",
                "name": title,
                "description": description,
                "url": canonical_url,
                "inLanguage": lang,
                "isPartOf": {"@type": "WebSite", "name": site_name, "url": base_url},
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    ]
    payload: Dict[str, Any] = {
        "lang": lang,
        "title": title,
        "description": description,
        "canonical_url": canonical_url,
        "robots_directive": "index, follow",
        "hreflang": _build_hreflang(site_config, languages),
        "og": {
            "title": title,
            "description": description,
            "image": f"{base_url}{logo_url}",
            "type": "website",
            "url": canonical_url,
            "site_name": site_name,
            "image_alt": site_name,
        },
        "twitter": {
            "card": "summary_large_image",
            "title": title,
            "description": description,
            "image": f"{base_url}{logo_url}",
            "image_alt": site_name,
        },
        "jsonld": jsonld,
        "extra_meta": [],
    }
    if locale:
        payload["og_locale"] = locale
    if alternate_locales:
        payload["og_locale_alternates"] = alternate_locales
    return payload


def _style_rows(
    site_config: Mapping[str, Any],
    experience_payload: Mapping[str, Any],
    lang: str,
) -> List[Dict[str, str]]:
    raw_items = experience_payload.get("experience_types")
    if not isinstance(raw_items, list):
        return []
    items: List[MutableMapping[str, Any]] = [x for x in raw_items if isinstance(x, Mapping)]
    items.sort(key=lambda x: int(x.get("order", 0)))
    out: List[Dict[str, str]] = []
    for item in items:
        if item.get("enabled", True) is False:
            continue
        slug_raw = item.get("slug")
        slug = _clean_string(slug_raw if isinstance(slug_raw, str) else slug_raw.get(lang) or slug_raw.get("en") if isinstance(slug_raw, Mapping) else "")
        if not slug:
            continue
        title = _localized(item.get("label"), lang, default=slug.replace("-", " ").title())
        summary = _localized(item.get("summary"), lang, default="")
        href = build_experience_type_path(site_config, lang, slug, absolute=False)
        out.append({"title": title, "summary": summary, "href": href, "slug": slug})
    return out


def _criteria_rows(criteria_doc: Mapping[str, Any], lang: str) -> List[Dict[str, Any]]:
    raw = criteria_doc.get("criteria")
    if not isinstance(raw, list):
        return []
    rows: List[Dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, Mapping) or not item.get("enabled", True):
            continue
        copy = item.get("copy")
        if not isinstance(copy, Mapping):
            continue
        name_m = copy.get("name")
        desc_m = copy.get("description")
        name = _localized(name_m, lang, default="")
        desc = _localized(desc_m, lang, default="")
        rows.append(
            {
                "id": _clean_string(item.get("id")),
                "order": int(item.get("order", 0)),
                "weight": item.get("weight"),
                "name": name,
                "description": desc,
            }
        )
    rows.sort(key=lambda x: x["order"])
    return rows


# --- Multilingual copy: institutional tone, eight narrative sections + chrome ---

def _sections_for_lang(lang: str) -> Dict[str, Any]:
    data = PAGE_COPY.get(lang, PAGE_COPY["en"])
    return data["sections"]


PAGE_COPY: Dict[str, Dict[str, Any]] = {
    "en": {
        "eyebrow": "TourVsTravel · Reference Report · System map",
        "title": "The Reference Report",
        "lead": (
            "TourVsTravel is not a catalog of trips. It is a multilingual reference system for how "
            "travel structure changes cost, burden, depth, predictability, and fit. This page maps the "
            "layers that turn “where” into a legible decision."
        ),
        "panel_label": "Report signals",
        "card_thesis": "Core thesis",
        "card_thesis_value": "How you travel reframes the place, the risk profile, and the outcome.",
        "card_layers": "Layers mapped",
        "card_layers_value": "Styles ontology · comparison · tools · destinations · methodology",
        "card_phase": "Phase",
        "card_phase_value": "Public reference v1 — scaling without false coverage",
        "toc_title": "In this report",
        "system_map_title": "System map",
        "system_map_intro": "Each layer is navigable on the site; together they form one decision reference.",
        "map_styles": "Travel style ontology",
        "map_compare": "Comparison layer",
        "map_tools": "Tools hub",
        "map_find_match": "Find Your Match",
        "map_destinations": "Destination interpretation",
        "map_methodology": "Methodology",
        "final_kicker": "Use the system",
        "final_title": "Move from place lists to structured travel decisions",
        "final_lead": "Start with styles, stress-test with comparison, ground destinations in interpretation, and return to methodology when you need the rules of evidence.",
        "cta_styles": "Open the styles ontology",
        "cta_compare": "Open comparison",
        "cta_tools": "Browse tools",
        "cta_match": "Run Find Your Match",
        "cta_destinations": "Destination interpretation hub",
        "cta_methodology": "Read the methodology",
        "sections": {
            "what": {
                "title": "1. What TourVsTravel is",
                "paragraphs": [
                    (
                        "TourVsTravel publishes a bounded ontology of seventeen travel styles, evidence-led "
                        "comparison criteria, practical tools, and a destination interpretation layer. The goal "
                        "is not to sell a default itinerary — it is to make tradeoffs explicit so travelers and "
                        "professionals can reason in structure, not slogans."
                    ),
                    (
                        "Content is generated under a disciplined build contract: no phantom routes, no broken "
                        "static assets, and multilingual hreflang semantics aligned to what actually ships."
                    ),
                ],
            },
            "why_how": {
                "title": "2. Why “how you travel” matters more than “where you go”",
                "paragraphs": [
                    (
                        "A destination entered through a guided group tour is not the same operational object "
                        "as the same coordinates approached through independent travel, slow travel, or "
                        "backpacking. Support, pace, predictability, immersion depth, and cost shape shift with "
                        "the travel form."
                    ),
                    (
                        "TourVsTravel therefore treats “where” as necessary but insufficient. The reference unit "
                        "is the pairing of place and travel structure — that is what our comparisons and tools "
                        "evaluate."
                    ),
                ],
                "pullquote": "The same place is not the same trip.",
            },
            "styles": {
                "title": "3. The seventeen travel styles",
                "intro": (
                    "Each style is defined as a decision structure with inclusion rules, tradeoffs, and scoring "
                    "priors — not a marketing tag. The public index lists all seventeen with links to the "
                    "canonical reference page for each slug."
                ),
            },
            "criteria": {
                "title": "4. Comparison criteria",
                "intro": (
                    "Comparisons run on explicit criteria with weights and plain-language meanings. Criteria "
                    "translate promotional ambiguity into inspectable tradeoffs (constraint fit, operational "
                    "complexity, control vs support, experience depth, predictability, traveler-type fit)."
                ),
            },
            "tools": {
                "title": "5. Decision tools",
                "paragraphs": [
                    (
                        "The tools hub is a repeat-use layer: it hosts utilities that turn the ontology into "
                        "action. Find Your Match is the first live tool — a structured matcher that scores "
                        "styles against traveler intent without pretending to be a booking engine."
                    ),
                    "TourVsTravel does not rely on live price feeds; where relevant it points to official or structured external resources.",
                ],
            },
            "destinations": {
                "title": "6. Destination interpretation layer",
                "paragraphs": [
                    (
                        "The destinations hub explains how meaning, friction, and cost profiles change when the "
                        "same geography is traveled through different styles. It precedes per-destination "
                        "expansion so the site never implies false global coverage."
                    ),
                ],
            },
            "methodology": {
                "title": "7. Methodology and editorial posture",
                "paragraphs": [
                    (
                        "Methodology documents source policy, editorial standards, and how evidence notes attach "
                        "to comparisons. The posture is reference-grade: show assumptions, link identifiable "
                        "sources where applicable, and avoid unstated winner bias."
                    ),
                ],
            },
            "scope": {
                "title": "8. Current scope and what comes next",
                "intro": "This release prioritizes structural clarity over breadth. It explicitly includes:",
                "bullets": [
                    "Seventeen multilingual style reference pages and a styles index.",
                    "Comparison hub and criterion documentation drawn from the canonical YAML datasets.",
                    "Tools hub with Find Your Match; additional tools ship when they clear the same build contract.",
                    "Destination interpretation hub; granular destination pages roll out only with explicit evidence discipline.",
                    "Methodology, source policy, and editorial standards as first-class routes.",
                ],
                "closing": (
                    "Later phases extend coverage depth (more destinations, more tools, richer scoring telemetry) "
                    "without breaking the route or evidence contracts established here."
                ),
            },
        },
    },
    "ar": {
        "eyebrow": "TourVsTravel · تقرير مرجعي · خريطة النظام",
        "title": "التقرير المرجعي",
        "lead": (
            "TourVsTravel ليس كتالوج رحلات، بل نظام مرجعي متعدد اللغات يوضح كيف تغيّر بنية السفر "
            "التكلفة والعبء والعمق والقابلية للتنبؤ والملاءمة. توضح هذه الصفحة الطبقات التي تحوّل «أين» إلى قرار قابل للقراءة."
        ),
        "panel_label": "إشارات التقرير",
        "card_thesis": "الأطروحة الأساسية",
        "card_thesis_value": "طريقة سفرك تعيد تأطير المكان وملف المخاطر والنتيجة.",
        "card_layers": "طبقات مُخطَطة",
        "card_layers_value": "أنماط · مقارنة · أدوات · وجهات · منهجية",
        "card_phase": "المرحلة",
        "card_phase_value": "مرجع عام v1 — توسعة دون تغطية زائفة",
        "toc_title": "في هذا التقرير",
        "system_map_title": "خريطة النظام",
        "system_map_intro": "كل طبقة قابلة للتنقّل؛ معًا تشكّل مرجع قرار واحد.",
        "map_styles": "أنماط السفر",
        "map_compare": "طبقة المقارنة",
        "map_tools": "محور الأدوات",
        "map_find_match": "اعثر على الأنسب",
        "map_destinations": "تفسير الوجهات",
        "map_methodology": "المنهجية",
        "final_kicker": "استخدم النظام",
        "final_title": "من قوائم الأماكن إلى قرارات منظمة",
        "final_lead": "ابدأ بالأنماط، اختبر بالمقارنة، وثبّت الوجهات عبر طبقة التفسير، والرجع إلى المنهجية عند قواعد الأدلة.",
        "cta_styles": "فتح أنماط السفر",
        "cta_compare": "فتح المقارنة",
        "cta_tools": "تصفح الأدوات",
        "cta_match": "تشغيل اعثر على الأنسب",
        "cta_destinations": "محور تفسير الوجهات",
        "cta_methodology": "قراءة المنهجية",
        "sections": {
            "what": {
                "title": "١. ما هو TourVsTravel",
                "paragraphs": [
                    "ينشر TourVsTravel أونطولوجيا محددة لسبعة عشر نمط سفر، ومعايير مقارنة قائمة على الأدلة، وأدوات عملية، وطبقة تفسير للوجهات. الهدف ليس بيع مسار افتراضي، بل جعل المقايضات صريحة.",
                    "يُولَّى المحتوى وفق عقد بناء صارم: بلا مسارات وهمية، وبأصول ثابتة متعددة اللغات تتوافق مع ما يُنشر فعليًا.",
                ],
            },
            "why_how": {
                "title": "٢. لماذا «كيف تسافر» أهم من «إلى أين»",
                "paragraphs": [
                    "الوجهة نفسها عبر جولة جماعية ليست نفس الكيان التشغيلي عند دخولها بسفر مستقل أو بطيء أو backpacking.",
                    "لذلك يُعالج TourVsTravel السؤال «أين» على أنه ضروري لكن غير كافٍ؛ وحدة المرجع هي المكان + بنية السفر.",
                ],
                "pullquote": "نفس المكان ليس نفس الرحلة.",
            },
            "styles": {
                "title": "٣. السبعة عشر نمطًا",
                "intro": "يُعرَّف كل نمط كبنية قرار مع قواعد إدخال ومقايضات؛ الفهرس العام يربط بجميع الصفحات المرجعية.",
            },
            "criteria": {
                "title": "٤. معايير المقارنة",
                "intro": "تعمل المقارنة على معايير صريحة بأوزان ومعانٍ لغوية واضحة، لتحويل العبارات الترويجية إلى مقايضات قابلة للفحص.",
            },
            "tools": {
                "title": "٥. أدوات القرار",
                "paragraphs": [
                    "محور الأدوات يحوّل الأونطولوجيا إلى فعل؛ «اعثر على الأنسب» أول أداة مباشرة مع تسجيلscores من دون ادعاء كونها محرك حجز.",
                    "لا يعتمد الموقع على أسعار حية؛ ويُحيل عند الحاجة إلى مصادر خارجية رسمية أو منظمة.",
                ],
            },
            "destinations": {
                "title": "٦. طبقة تفسير الوجهات",
                "paragraphs": [
                    "يوضح المحور كيف تتبدل الدلالة والاحتكاك وملف التكلفة لذات الجغرافيا باختلاف نمط السفر، قبل توسيع صفحات فردية بمسؤولية أدلة.",
                ],
            },
            "methodology": {
                "title": "٧. المنهجية والموقف التحريري",
                "paragraphs": [
                    "توثق المنهجية سياسة المصادر والمعايير التحريرية وكيف تُرفق الملاحظات المؤيدة. الموقف مرجعي: إبراز الافتراضات وربط المصادر وتجنب تحيز فائز ضمني.",
                ],
            },
            "scope": {
                "title": "٨. نطاق المرحلة وما يليها",
                "intro": "هذا الإصدار يفضّل الوضوح البنيوي على اتساع السطح:",
                "bullets": [
                    "صفحات مرجعية متعددة اللغات لسبعة عشر نمطًا وفهرس أنماط.",
                    "محور مقارنة ومعايير من مجموعات YAML الرسمية.",
                    "محور أدوات مع «اعثر على الأنسب»؛ أدوات إضافية بنفس عقد البناء.",
                    "محور تفسير وجهات؛ الصفحات التفصيلية بتقدّم ضبط أدلة صريح.",
                    "منهجية وسياسات مصادر ومعايير تحريرية كمسارات أولى.",
                ],
                "closing": "المراحل اللاحقة تعمّق التغطية دون كسر عقود المسارات أو الأدلة.",
            },
        },
    },
    "fr": {
        "eyebrow": "TourVsTravel · rapport de référence · carte du système",
        "title": "Le rapport de référence",
        "lead": (
            "TourVsTravel n'est pas un catalogue d'offres. C'est un système multilingue qui rend lisibles "
            "les effets de la structure de voyage sur le coût, la charge, la profondeur, la prévisibilité et "
            "l'adéquation. Cette page cartographie les couches qui transforment le « où » en décision structurée."
        ),
        "panel_label": "Signaux du rapport",
        "card_thesis": "Thèse centrale",
        "card_thesis_value": "La manière de voyager recadre le lieu, le profil de risque et le résultat.",
        "card_layers": "Couches cartographiées",
        "card_layers_value": "Styles · comparaison · outils · destinations · méthodologie",
        "card_phase": "Phase",
        "card_phase_value": "Référence publique v1 — extension sans fausse couverture",
        "toc_title": "Dans ce rapport",
        "system_map_title": "Carte du système",
        "system_map_intro": "Chaque couche est navigable ; ensemble elles forment une référence décisionnelle unique.",
        "map_styles": "Ontologie des styles",
        "map_compare": "Couche de comparaison",
        "map_tools": "Hub d'outils",
        "map_find_match": "Find Your Match",
        "map_destinations": "Interprétation des destinations",
        "map_methodology": "Méthodologie",
        "final_kicker": "Utiliser le système",
        "final_title": "Des listes de lieux aux décisions structurées",
        "final_lead": "Commencez par les styles, contrôlez par la comparaison, ancrez les destinations dans l'interprétation, revisitez la méthodologie pour les règles de preuve.",
        "cta_styles": "Voir l'ontologie des styles",
        "cta_compare": "Ouvrir la comparaison",
        "cta_tools": "Parcourir les outils",
        "cta_match": "Lancer Find Your Match",
        "cta_destinations": "Hub destinations",
        "cta_methodology": "Lire la méthodologie",
        "sections": {
            "what": {
                "title": "1. Ce qu'est TourVsTravel",
                "paragraphs": [
                    "TourVsTravel publie une ontologie bornée de dix-sept structures de voyage, des critères comparatifs explicites, des outils pratiques et une couche d'interprétation des destinations.",
                    "Le contenu est généré sous un contrat de build discipliné : pas d'URL fantômes, actifs statiques valides, hreflang aligné sur ce qui est réellement publié.",
                ],
            },
            "why_how": {
                "title": "2. Pourquoi le « comment » prime sur le « où »",
                "paragraphs": [
                    "Une destination abordée en groupe guidé n'a pas la même structure opérationnelle qu'en voyage indépendant, slow travel ou sac à dos.",
                    "Le « où » est donc nécessaire mais insuffisant ; l'unité de référence est le couple lieu + forme de voyage.",
                ],
                "pullquote": "Le même lieu n'est pas le même voyage.",
            },
            "styles": {
                "title": "3. Les dix-sept styles",
                "intro": "Chaque style est une structure de décision avec règles d'inclusion et tradeoffs documentés, pas un simple label marketing.",
            },
            "criteria": {
                "title": "4. Critères de comparaison",
                "intro": "Les critères rendent les arbitrages inspectables (adéquation aux contraintes, complexité opérationnelle, contrôle vs soutien, profondeur, prévisibilité, adéquation au profil).",
            },
            "tools": {
                "title": "5. Outils de décision",
                "paragraphs": [
                    "Le hub d'outils réutilise l'ontologie pour passer à l'action. Find Your Match en est le premier module public.",
                    "Pas de flux tarifaire temps réel ; renvois vers ressources externes structurées ou officielles quand c'est pertinent.",
                ],
            },
            "destinations": {
                "title": "6. Couche d'interprétation des destinations",
                "paragraphs": [
                    "Le hub explique comment sens, friction et enveloppe de coût changent pour une même géographie selon le style, avant d'ajouter des fiches pays/ville responsables.",
                ],
            },
            "methodology": {
                "title": "7. Méthodologie et posture éditoriale",
                "paragraphs": [
                    "La méthodologie couvre politique des sources, normes éditoriales et rattachement des preuves aux comparaisons — posture de niveau référence.",
                ],
            },
            "scope": {
                "title": "8. Périmètre actuel et suite",
                "intro": "Cette version privilégie la clarté structurelle :",
                "bullets": [
                    "17 pages de référence multilingues + index des styles.",
                    "Hub de comparaison et critères issus des jeux YAML canoniques.",
                    "Hub d'outils avec Find Your Match.",
                    "Hub d'interprétation des destinations ; fiches détaillées sous discipline de preuve.",
                    "Méthodologie et politiques comme routes de premier niveau.",
                ],
                "closing": "Les phases suivantes approfondissent sans rompre les contrats d'URL ni d'évidence.",
            },
        },
    },
    "es": {
        "eyebrow": "TourVsTravel · informe de referencia · mapa del sistema",
        "title": "Informe de referencia",
        "lead": (
            "TourVsTravel no es un catálogo de viajes. Es un sistema multilingüe que explica cómo la estructura "
            "del viaje altera coste, carga, profundidad, previsibilidad y ajuste. Esta página traza las capas que "
            "convierten el «dónde» en una decisión legible."
        ),
        "panel_label": "Señales del informe",
        "card_thesis": "Tesis central",
        "card_thesis_value": "Cómo viajas reencuadra el lugar, el riesgo y el resultado.",
        "card_layers": "Capas mapeadas",
        "card_layers_value": "Estilos · comparación · herramientas · destinos · metodología",
        "card_phase": "Fase",
        "card_phase_value": "Referencia pública v1 — escalar sin cobertura falsa",
        "toc_title": "En este informe",
        "system_map_title": "Mapa del sistema",
        "system_map_intro": "Cada capa es navegable; juntas forman una sola referencia de decisión.",
        "map_styles": "Ontología de estilos",
        "map_compare": "Capa de comparación",
        "map_tools": "Hub de herramientas",
        "map_find_match": "Find Your Match",
        "map_destinations": "Interpretación de destinos",
        "map_methodology": "Metodología",
        "final_kicker": "Usar el sistema",
        "final_title": "De listas de lugares a decisiones estructuradas",
        "final_lead": "Empieza por estilos, contrasta con comparación, ancla destinos en interpretación y vuelve a la metodología para las reglas de evidencia.",
        "cta_styles": "Abrir ontología de estilos",
        "cta_compare": "Abrir comparación",
        "cta_tools": "Ver herramientas",
        "cta_match": "Ejecutar Find Your Match",
        "cta_destinations": "Hub de destinos",
        "cta_methodology": "Leer metodología",
        "sections": {
            "what": {
                "title": "1. Qué es TourVsTravel",
                "paragraphs": [
                    "Publica una ontología acotada de diecisiete estructuras de viaje, criterios comparativos explícitos, herramientas prácticas y una capa de interpretación de destinos.",
                    "El contenido se genera bajo un contrato de build estricto, con hreflang acoplado a lo publicado.",
                ],
            },
            "why_how": {
                "title": "2. Por qué importa más el «cómo» que el «dónde»",
                "paragraphs": [
                    "El mismo punto geográfico con circuito guiado no es el mismo objeto operativo que con viaje independiente o mochila.",
                    "Por ello el «dónde» es necesario pero insuficiente; la unidad de referencia es lugar + forma de viaje.",
                ],
                "pullquote": "El mismo lugar no es el mismo viaje.",
            },
            "styles": {
                "title": "3. Los diecisiete estilos",
                "intro": "Cada estilo es una estructura de decisión documentada, no una etiqueta promocional.",
            },
            "criteria": {
                "title": "4. Criterios de comparación",
                "intro": "Criterios con pesos y significados claros vuelven inspectables los tradeoffs.",
            },
            "tools": {
                "title": "5. Herramientas de decisión",
                "paragraphs": [
                    "El hub convierte la ontología en acción; Find Your Match es el primer módulo público.",
                    "Sin precios en vivo; derivación a fuentes externas estructuradas cuando procede.",
                ],
            },
            "destinations": {
                "title": "6. Capa de interpretación de destinos",
                "paragraphs": [
                    "Explica cómo cambian significado y fricción para la misma geografía según el estilo, antes de páginas granulares.",
                ],
            },
            "methodology": {
                "title": "7. Metodología y postura editorial",
                "paragraphs": [
                    "Documenta política de fuentes, estándares editoriales y vínculo de evidencias con comparaciones.",
                ],
            },
            "scope": {
                "title": "8. Alcance actual y siguientes pasos",
                "intro": "Esta release prioriza claridad estructural:",
                "bullets": [
                    "17 referencias multilingües e índice de estilos.",
                    "Hub de comparación ligado a YAML canónico.",
                    "Hub de herramientas con Find Your Match.",
                    "Hub de interpretación de destinos; fichas bajo disciplina de evidencia.",
                    "Metodología y políticas como rutas de primer nivel.",
                ],
                "closing": "Fases posteriores amplían profundidad sin romper contratos de URL ni de evidencia.",
            },
        },
    },
    "de": {
        "eyebrow": "TourVsTravel · Referenzbericht · Systemkarte",
        "title": "Der Referenzbericht",
        "lead": (
            "TourVsTravel ist kein Reisekatalog, sondern ein mehrsprachiges Referenzsystem: Wie Reisestruktur "
            "Kosten, operative Last, Tiefe, Vorhersehbarkeit und Passung verändert. Diese Seite kartiert die "
            "Schichten, die das «Wo» in eine nachvollziehbare Entscheidung verwandeln."
        ),
        "panel_label": "Berichtssignale",
        "card_thesis": "KernThese",
        "card_thesis_value": "Wie Sie reisen, rahmt Ort, Risikoprofil und Ergebnis neu.",
        "card_layers": "Gemappte Schichten",
        "card_layers_value": "Stile · Vergleich · Werkzeuge · Reiseziele · Methodik",
        "card_phase": "Phase",
        "card_phase_value": "Öffentliche Referenz v1 — Skalierung ohne Scheinabdeckung",
        "toc_title": "In diesem Bericht",
        "system_map_title": "Systemkarte",
        "system_map_intro": "Jede Schicht ist navigierbar; zusammen bilden sie eine Entscheidungsreferenz.",
        "map_styles": "Reise-Stil-Ontologie",
        "map_compare": "Vergleichsschicht",
        "map_tools": "Werkzeug-Hub",
        "map_find_match": "Find Your Match",
        "map_destinations": "Ziel-Interpretation",
        "map_methodology": "Methodik",
        "final_kicker": "System nutzen",
        "final_title": "Von Ortslisten zu strukturierten Reiseentscheidungen",
        "final_lead": "Beginnen Sie mit Stilen, prüfen Sie mit dem Vergleich, verankern Sie Ziele in der Interpretation, lesen Sie die Methodik für Evidenzregeln.",
        "cta_styles": "Stil-Ontologie öffnen",
        "cta_compare": "Vergleich öffnen",
        "cta_tools": "Werkzeuge",
        "cta_match": "Find Your Match starten",
        "cta_destinations": "Ziel-Interpretations-Hub",
        "cta_methodology": "Methodik lesen",
        "sections": {
            "what": {
                "title": "1. Was TourVsTravel ist",
                "paragraphs": [
                    "TourVsTravel veröffentlicht eine begrenzte Ontologie von siebzehn Reiseformen, explizite Vergleichskriterien, praktische Werkzeuge und eine Interpretationsschicht für Reiseziele.",
                    "Inhalt entsteht unter einem strengen Build-Vertrag: keine Phantom-URLs, gültige Statik, hreflang passend zur Realität.",
                ],
            },
            "why_how": {
                "title": "2. Warum das «Wie» wichtiger ist als das «Wo»",
                "paragraphs": [
                    "Dieselbe Geografie als Gruppenreise ist strukturell nicht dasselbe Objekt wie im individuellen oder Backpacking-Modus.",
                    "Das «Wo» ist nötig aber nicht hinreichend; die Referenzeinheit ist Ort + Reiseform.",
                ],
                "pullquote": "Derselbe Ort ist nicht dieselbe Reise.",
            },
            "styles": {
                "title": "3. Die siebzehn Stile",
                "intro": "Jeder Stil ist als Entscheidungsstruktur mit dokumentierten Tradeoffs definiert, nicht als Marketinglabel.",
            },
            "criteria": {
                "title": "4. Vergleichskriterien",
                "intro": "Gewichtete Kriterien mit klaren Bedeutungen machen Tradeoffs prüfbar.",
            },
            "tools": {
                "title": "5. Entscheidungswerkzeuge",
                "paragraphs": [
                    "Der Hub macht aus der Ontologie Handlung; Find Your Match ist das erste öffentliche Modul.",
                    "Keine Live-Preise; Verweise auf strukturierte oder offizielle externe Ressourcen.",
                ],
            },
            "destinations": {
                "title": "6. Ziel-Interpretationsschicht",
                "paragraphs": [
                    "Erklärt, wie Sinn, Reibung und Kostenprofil je Stil wechseln, bevor Detailseiten unter Evidenzdisziplin folgen.",
                ],
            },
            "methodology": {
                "title": "7. Methodik und Redaktionshaltung",
                "paragraphs": [
                    "Dokumentiert Quellenpolitik, redaktionelle Standards und Evidenzbezug in Vergleichen.",
                ],
            },
            "scope": {
                "title": "8. Aktueller Umfang und Ausblick",
                "intro": "Diese Version setzt auf strukturelle Klarheit:",
                "bullets": [
                    "17 mehrsprachige Referenzseiten + Stil-Index.",
                    "Vergleichs-Hub mit kanonischen YAML-Kriterien.",
                    "Werkzeug-Hub mit Find Your Match.",
                    "Ziel-Interpretations-Hub; Detailseiten nur mit Evidenzregeln.",
                    "Methodik und Policies als Erstklass-Routen.",
                ],
                "closing": "Spätere Phasen vertiefen ohne Bruch von URL- oder Evidenzverträgen.",
            },
        },
    },
    "zh": {
        "eyebrow": "TourVsTravel · 参考报告 · 系统地图",
        "title": "参考报告",
        "lead": (
            "TourVsTravel 不是行程超市，而是多语言的旅行决策参考体系：旅行结构如何改变成本、负担、体验深度、可预测性与适配。"
            "本页勾连各层，把「去哪里」还原为可推敲的决定。"
        ),
        "panel_label": "报告要点",
        "card_thesis": "核心论点",
        "card_thesis_value": "旅行方式重塑地点、风险轮廓与结果。",
        "card_layers": "已映射层级",
        "card_layers_value": "风格本体 · 对比 · 工具 · 目的地 · 方法论",
        "card_phase": "阶段",
        "card_phase_value": "公共参考 v1 — 扩展而不伪称全覆盖",
        "toc_title": "本报告包括",
        "system_map_title": "系统地图",
        "system_map_intro": "每层可独立导航，共同构成一套决策参考。",
        "map_styles": "旅行风格本体",
        "map_compare": "对比层",
        "map_tools": "工具枢纽",
        "map_find_match": "找到你的匹配",
        "map_destinations": "目的地阐释",
        "map_methodology": "方法论",
        "final_kicker": "使用体系",
        "final_title": "从地点列表到结构化旅行决策",
        "final_lead": "从风格入手，用对比检验，把目的地放入阐释层，需要证据规则时回到方法论。",
        "cta_styles": "打开风格本体",
        "cta_compare": "打开对比",
        "cta_tools": "浏览工具",
        "cta_match": "运行找到你的匹配",
        "cta_destinations": "目的地阐释枢纽",
        "cta_methodology": "阅读方法论",
        "sections": {
            "what": {
                "title": "1. TourVsTravel 是什么",
                "paragraphs": [
                    "发布十七种旅行结构的受控本体、可对照的比较标准、实用工具与目的地阐释层；目标是把取舍说清楚，而非推销默认路线。",
                    "内容在严格的前端契约下生成：无幽灵路由、静态资源可用、hreflang 与实际上线页面一致。",
                ],
            },
            "why_how": {
                "title": "2. 为何「如何旅行」比「去哪里」更关键",
                "paragraphs": [
                    "同一坐标以团队观光、独立行、慢旅行或背包进入，运营结构并不相同。",
                    "因此「何地」必要但不充分；参考单位是地点 + 旅行结构。",
                ],
                "pullquote": "同一地点，不是同一段旅程。",
            },
            "styles": {
                "title": "3. 十七种旅行风格",
                "intro": "每种风格都是带纳入规则与权衡的决策结构，而非营销标签。",
            },
            "criteria": {
                "title": "4. 比较标准",
                "intro": "显式权重与语义，把模糊口号变成可检查的成本—收益结构。",
            },
            "tools": {
                "title": "5. 决策工具",
                "paragraphs": [
                    "工具枢纽把本体落到行动；「找到你的匹配」是首个公开打分模块，而非预订引擎。",
                    "不依赖实时报价；在需要时指向官方或结构化外部资源。",
                ],
            },
            "destinations": {
                "title": "6. 目的地阐释层",
                "paragraphs": [
                    "说明同一地理在不同风格下意义、摩擦与成本形态如何变化，再在证据纪律下扩展单页。",
                ],
            },
            "methodology": {
                "title": "7. 方法论与编辑立场",
                "paragraphs": [
                    "记录来源政策、编辑标准及对照证据注释的衔接方式；立场是参考级而非软文赢家。",
                ],
            },
            "scope": {
                "title": "8. 当前边界与后续",
                "intro": "当前版本优先结构清晰，而非表面覆盖：",
                "bullets": [
                    "十七个多语言参考页 + 风格索引。",
                    "对比枢纽与 YAML 正统数据集。",
                    "含「找到你的匹配」的工具枢纽。",
                    "目的地阐释枢纽；细粒度页面遵循证据流程。",
                    "方法论与政策类路线为一级入口。",
                ],
                "closing": "后续阶段加深深度，但不破坏路由与证据契约。",
            },
        },
    },
    "ja": {
        "eyebrow": "TourVsTravel · リファレンスレポート · システムマップ",
        "title": "リファレンスレポート",
        "lead": (
            "TourVsTravel は旅行カタログではなく、旅行構造がコスト、負荷、没入度、予測可能性、適合度に与える影響を多言語化した参照系です。"
            "「どこへ」が読み解ける判断に変わる層をこのページで示します。"
        ),
        "panel_label": "レポート要約",
        "card_thesis": "コア命題",
        "card_thesis_value": "旅の仕方が場所・リスク・結果の枠組みを変える。",
        "card_layers": "マップした層",
        "card_layers_value": "スタイル · 比較 · ツール · 目的地 · 方法論",
        "card_phase": "フェーズ",
        "card_phase_value": "公開リファレンス v1 — 偽の網羅なく拡張",
        "toc_title": "本レポートの内容",
        "system_map_title": "システムマップ",
        "system_map_intro": "各層は個別に遷移でき、合わせて一つの判断リファレンスになります。",
        "map_styles": "旅行スタイルのオントロジー",
        "map_compare": "比較レイヤー",
        "map_tools": "ツールハブ",
        "map_find_match": "Find Your Match",
        "map_destinations": "目的地の解釈",
        "map_methodology": "方法論",
        "final_kicker": "システムを使う",
        "final_title": "場所のリストから構造化された判断へ",
        "final_lead": "スタイルから入り、比較で検証し、目的地は解釈レイヤーで固定し、証拠規則は方法論へ。",
        "cta_styles": "スタイル索引を開く",
        "cta_compare": "比較へ",
        "cta_tools": "ツール一覧",
        "cta_match": "Find Your Match を試す",
        "cta_destinations": "目的地ハブ",
        "cta_methodology": "方法論を読む",
        "sections": {
            "what": {
                "title": "1. TourVsTravel とは",
                "paragraphs": [
                    "17 の旅行構造、明示的な比較基準、実務ツール、目的地解釈層を公開する参照インフラ。既定プランを売るのではなくトレードオフを可視化する。",
                    "厳格なビルド契約の下で生成し、phantom URL や壊れた静的資産を避け、hreflang を実公開面に一致させる。",
                ],
            },
            "why_how": {
                "title": "2. 「どう旅するか」が「どこへ」より重要な理由",
                "paragraphs": [
                    "同じ座標でも、団体ガイド付きと独立・スロー・バックパックでは運用上の対象が異なる。",
                    "したがって「どこへ」は必要だが不十分。参照単位は場所 + 旅の構造。",
                ],
                "pullquote": "同じ場所でも、同じ旅ではない。",
            },
            "styles": {
                "title": "3. 17 のスタイル",
                "intro": "各スタイルは包含ルールとトレードオフを伴う判断構造として定義され、装飾ラベルではない。",
            },
            "criteria": {
                "title": "4. 比較基準",
                "intro": "重みと平易な意味づけにより、曖昧な宣伝を検証可能な比較へ変換する。",
            },
            "tools": {
                "title": "5. 意思決定ツール",
                "paragraphs": [
                    "ツールハブはオントロジーを行動へ接続。Find Your Match は最初の公開モジュール。",
                    "ライブ価格には依存せず、必要に応じて公式・構造化された外部へ案内する。",
                ],
            },
            "destinations": {
                "title": "6. 目的地解釈レイヤー",
                "paragraphs": [
                    "同じ地理でもスタイルごとに意味・摩擦・コスト包絡がどう変わるかを示し、詳細ページは証拠規律のもとで拡張する。",
                ],
            },
            "methodology": {
                "title": "7. 方法論と編集姿勢",
                "paragraphs": [
                    "ソース方針、編集基準、比較へのエビデンス紐付けを文書化し、参照品質を維持する。",
                ],
            },
            "scope": {
                "title": "8. 現在の範囲と今後",
                "intro": "このリリースは構造の明晰さを優先する:",
                "bullets": [
                    "17 言語リファレンス + スタイル索引。",
                    "正典 YAML に基づく比較ハブ。",
                    "Find Your Match を含むツールハブ。",
                    "目的地解釈ハブ；詳細ページは証拠プロセス付き。",
                    "方法論とポリシーを一次ルートとして提供。",
                ],
                "closing": "将来フェーズは URL と証拠契約を破壊せずに深度を伸ばす。",
            },
        },
    },
}


def _assemble_sections(
    lang: str,
    site_config: Mapping[str, Any],
    experience_payload: Mapping[str, Any],
    criteria_doc: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    raw = _sections_for_lang(lang)
    styles = _style_rows(site_config, experience_payload, lang)
    criteria = _criteria_rows(criteria_doc, lang)
    out: List[Dict[str, Any]] = []
    for sid in SECTION_ORDER:
        block = dict(raw[sid])  # copy
        block["id"] = sid
        if sid == "styles":
            block["section_type"] = "styles"
            block["rows"] = styles
        elif sid == "criteria":
            block["section_type"] = "criteria"
            block["rows"] = criteria
        else:
            block["section_type"] = "narrative"
        out.append(block)
    return out



def _ensure_safe_output_dir(output_dir: Path) -> Path:
    resolved = output_dir.resolve()
    if str(resolved) == resolved.anchor:
        raise ReportWriteError(f"Refusing filesystem root as output directory: {resolved}")
    if resolved.exists() and resolved.is_symlink():
        raise ReportWriteError(f"Refusing symlink output directory: {resolved}")
    if resolved.parent.exists() and resolved.parent.is_symlink():
        raise ReportWriteError(f"Refusing symlink parent for output directory: {resolved.parent}")
    return resolved


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: Optional[Path] = None
    try:
        import os as os_mod

        from tempfile import NamedTemporaryFile as NT

        with NT("w", encoding="utf-8", dir=str(path.parent), delete=False, suffix=".tmp") as tmp:
            tmp.write(content)
            tmp.flush()
            os_mod.fsync(tmp.fileno())
            tmp_path = Path(tmp.name)
        tmp_path.replace(path)
    except Exception as exc:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise ReportWriteError(f"Unable to write report page {path}: {exc}") from exc


def _create_jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _build_context(
    site_config: Mapping[str, Any],
    experience_payload: Mapping[str, Any],
    criteria_doc: Mapping[str, Any],
    lang: str,
    languages: Sequence[str],
) -> Dict[str, Any]:
    base_url = _normalize_https_base_url(site_config)
    site_name = _extract_site_name(site_config, lang)
    copy_root = PAGE_COPY.get(lang, PAGE_COPY["en"])
    logo_url = _resolve_logo_path(site_config)
    rel_self = build_reference_report_path(site_config, lang, absolute=False)
    canonical_url = build_absolute_url(site_config, rel_self)
    title = f"{copy_root['title']} | {site_name}"
    description = _clean_string(copy_root["lead"])
    seo_payload = _build_seo_payload(
        site_config=site_config,
        lang=lang,
        title=title,
        description=description,
        canonical_url=canonical_url,
        base_url=base_url,
        site_name=site_name,
        logo_url=logo_url,
        languages=languages,
    )
    main_css_url = _require_existing_asset("/static/css/main.css", "main_css_url")
    main_js_url = _require_existing_asset("/static/js/main.js", "main_js_url")

    report_sections = _assemble_sections(lang, site_config, experience_payload, criteria_doc)
    lang_code = lang

    return {
        "base_url": base_url,
        "lang": lang_code,
        "page_lang": lang_code,
        "current_lang": lang_code,
        "language": lang_code,
        "page_dir": _language_direction(site_config, lang_code),
        "is_rtl": _language_direction(site_config, lang_code) == "rtl",
        "body_class": "page-report",
        "current_year": datetime.now(timezone.utc).year,
        "site_name": site_name,
        "copy": copy_root,
        "report_sections": report_sections,
        "canonical_url": canonical_url,
        "seo": seo_payload,
        "hreflang": seo_payload["hreflang"],
        "meta_desc": description,
        "robots_directive": seo_payload["robots_directive"],
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
        "active_nav": "report",
        "footer_note": "",
        "footer_reference_report_label": resolve_footer_reference_report_label(site_config, lang_code),
        "nav_report_label": resolve_nav_report_label(site_config, lang_code),
        "url_styles": f"{build_home_path(site_config, lang_code, absolute=False)}styles/",
        "url_compare": build_compare_index_path(site_config, lang_code, absolute=False),
        "url_tools": build_tools_index_path(site_config, lang_code, absolute=False),
        "url_find_match": f"/{lang_code}/tools/find-your-match/",
        "url_destinations": build_destinations_index_path(site_config, lang_code, absolute=False),
        "url_methodology": build_methodology_path(site_config, lang_code, absolute=False),
    }


def render_report_page(
    *,
    site_config: Mapping[str, Any],
    experience_payload: Mapping[str, Any],
    criteria_doc: Mapping[str, Any],
    lang: str,
    languages: Sequence[str],
) -> str:
    env = _create_jinja_env()
    try:
        template = env.get_template(TEMPLATE_NAME)
    except TemplateError as exc:
        raise ReportRenderError(f"Unable to load template {TEMPLATE_NAME}: {exc}") from exc
    try:
        html_output = template.render(**_build_context(site_config, experience_payload, criteria_doc, lang, languages))
    except TemplateError as exc:
        raise ReportRenderError(f"Unable to render reference report [{lang}]: {exc}") from exc
    if not html_output.strip():
        raise ReportRenderError(f"Rendered reference report is empty for language {lang!r}.")
    return html_output


def generate_report_pages(*, requested_lang: Optional[str] = None, output_dir: Path = DEFAULT_OUTPUT_DIR) -> List[Path]:
    safe_output_dir = _ensure_safe_output_dir(output_dir)
    site_config = load_site_config()
    if not isinstance(site_config, Mapping):
        raise ReportConfigError("load_site_config() must return a mapping/object.")
    experience_payload = load_experience_types()
    if not isinstance(experience_payload, Mapping):
        raise ReportConfigError("load_experience_types() must return a mapping/object.")
    criteria_doc = load_comparison_criteria()
    if not isinstance(criteria_doc, Mapping):
        raise ReportConfigError("load_comparison_criteria() must return a mapping/object.")

    if requested_lang is not None:
        lang = requested_lang.strip()
        if lang not in SUPPORTED_LANGUAGES:
            raise ReportConfigError(f"Unsupported language requested: {requested_lang!r}")
        languages = [lang]
    else:
        languages = _extract_enabled_languages(site_config)
    if not languages:
        raise ReportConfigError("No enabled languages available for report generation.")

    rendered: List[tuple[Path, str, str]] = []
    for lang in languages:
        html_output = render_report_page(
            site_config=site_config,
            experience_payload=experience_payload,
            criteria_doc=criteria_doc,
            lang=lang,
            languages=languages,
        )
        output_path = safe_output_dir / lang / "report" / "index.html"
        rendered.append((output_path, html_output, lang))
    written: List[Path] = []
    for output_path, html_output, lang in rendered:
        _atomic_write_text(output_path, html_output)
        written.append(output_path)
        log.info("Generated reference report page [%s] -> %s", lang, output_path)
    log.info("Reference report generation completed successfully. Files written: %d", len(written))
    return written


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate multilingual TourVsTravel reference report pages.")
    parser.add_argument("--lang", type=str, default=None, help="Generate one language only.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Output directory root.")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        generate_report_pages(requested_lang=args.lang, output_dir=args.output_dir)
    except GenerateReportError as exc:
        log.error(str(exc))
        return 1
    except Exception as exc:
        log.exception("Unexpected reference report generation failure: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())