#!/usr/bin/env python3
"""
TourVsTravel - Destination detail pages (governed batch)
========================================================
Generates:
  output/{lang}/destinations/{destination_id}/index.html

Governance:
- Renders data/destinations.yaml (governed batch dataset, all seven
  languages required per entry) through the travel-structure lens:
  family-fit priors, structural facts, official sources.
- Family labels and member structures come from the canonical ontology
  dataset, so the destination pages form a link spine into the 17 class
  pages.
- Family-fit levels are structural priors (TDIS rule priors-context);
  the page says so explicitly in every language.
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

from scripts.generate_category_infrastructure import (
    GenerateCategoryInfrastructureError,
    load_ontology_structures,
)
from scripts.generate_compass import VALUE_LABELS
from scripts.loaders import (
    load_destinations,
    load_experience_types,
    load_site_config,
    resolve_footer_reference_report_label,
    resolve_nav_report_label,
)
from scripts.reference_i18n import localized_ui_context
from scripts.routes import (
    build_about_path,
    build_acquire_path,
    build_changelog_path,
    build_compare_index_path,
    build_contact_path,
    build_destination_language_url_map,
    build_destination_path,
    build_destinations_index_path,
    build_editorial_standards_path,
    build_experience_type_path,
    build_home_path,
    build_methodology_path,
    build_ontology_path,
    build_privacy_path,
    build_reference_report_path,
    build_source_policy_path,
    build_standard_path,
    build_tools_index_path,
    build_travel_decision_architecture_path,
)
from scripts.seo import (
    build_organization_jsonld,
    build_page_seo,
    build_webpage_jsonld,
    build_website_jsonld,
)

log = logging.getLogger("generate_destination_pages")

ROOT_DIR = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = ROOT_DIR / "templates"
STATIC_DIR = ROOT_DIR / "static"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "output"
TEMPLATE_NAME = "pages/destination.html"
SUPPORTED_LANGUAGES = ("en", "ar", "fr", "es", "de", "zh", "ja")

FAMILY_ORDER = (
    "structured_supported",
    "independent_autonomous",
    "comfort_premium",
    "purpose_led",
    "mobility_led",
    "values_led",
)

FIT_SCALE = ("high", "medium", "low")


class GenerateDestinationPagesError(Exception):
    pass


PAGE_COPY: Dict[str, Dict[str, str]] = {
    "en": {
        "lead_suffix": "Interpreted through travel structures, not attractions.",
        "fit_heading": "How this destination behaves across travel structures",
        "fit_intro": "Family-fit levels are structural priors from the governed destinations dataset: they describe how the place tends to support each structure family before traveler context is applied. They are not verdicts, and no destination is universally best.",
        "structures_in_family_label": "Structures in this family",
        "facts_heading": "Structural facts",
        "seasons_label": "Best seasons",
        "duration_label": "Typical duration",
        "region_label": "Region",
        "sources_heading": "Official sources",
        "sources_intro": "Destination facts should be verified against the responsible official body. These links leave TourVsTravel.",
        "next_heading": "Decide the structure first",
        "next_intro": "The same destination is not the same trip. Run the Compass to diagnose which structures fit your constraints, or read the ontology the diagnosis is built on.",
        "link_compass": "Travel Decision Compass",
        "link_ontology": "Travel Structure Ontology (TSO) v1",
        "link_destinations": "All destinations",
    },
    "ar": {
        "lead_suffix": "تُقرأ عبر بنى السفر لا عبر المعالم.",
        "fit_heading": "كيف تتصرف هذه الوجهة عبر بنى السفر",
        "fit_intro": "مستويات ملاءمة العائلات افتراضات بنيوية مسبقة من مجموعة بيانات الوجهات المحكومة: تصف كيف يميل المكان إلى دعم كل عائلة بنى قبل تطبيق سياق المسافر. ليست أحكامًا نهائية، ولا توجد وجهة أفضل للجميع."
        ,
        "structures_in_family_label": "البنى في هذه العائلة",
        "facts_heading": "حقائق بنيوية",
        "seasons_label": "أفضل المواسم",
        "duration_label": "المدة المعتادة",
        "region_label": "المنطقة",
        "sources_heading": "مصادر رسمية",
        "sources_intro": "ينبغي التحقق من حقائق الوجهة لدى الجهة الرسمية المسؤولة. هذه الروابط تغادر TourVsTravel.",
        "next_heading": "قرر البنية أولًا",
        "next_intro": "الوجهة نفسها ليست الرحلة نفسها. شغّل البوصلة لتشخيص البنى الملائمة لقيودك، أو اقرأ الأنطولوجيا التي بُني عليها التشخيص.",
        "link_compass": "بوصلة قرار السفر",
        "link_ontology": "أنطولوجيا بنى السفر (TSO) v1",
        "link_destinations": "كل الوجهات",
    },
    "fr": {
        "lead_suffix": "Interprétée à travers les structures de voyage, non les attractions.",
        "fit_heading": "Comment cette destination se comporte selon les structures de voyage",
        "fit_intro": "Les niveaux d'adéquation par famille sont des a priori structurels issus du jeu de données gouverné des destinations : ils décrivent comment le lieu tend à soutenir chaque famille de structures avant l'application du contexte du voyageur. Ce ne sont pas des verdicts, et aucune destination n'est universellement meilleure.",
        "structures_in_family_label": "Structures de cette famille",
        "facts_heading": "Repères structurels",
        "seasons_label": "Meilleures saisons",
        "duration_label": "Durée typique",
        "region_label": "Région",
        "sources_heading": "Sources officielles",
        "sources_intro": "Les faits de destination doivent être vérifiés auprès de l'organisme officiel responsable. Ces liens quittent TourVsTravel.",
        "next_heading": "Décidez d'abord la structure",
        "next_intro": "La même destination n'est pas le même voyage. Lancez la Boussole pour diagnostiquer les structures adaptées à vos contraintes, ou lisez l'ontologie sur laquelle repose le diagnostic.",
        "link_compass": "Boussole de Décision de Voyage",
        "link_ontology": "Ontologie des structures de voyage (TSO) v1",
        "link_destinations": "Toutes les destinations",
    },
    "es": {
        "lead_suffix": "Interpretado a través de estructuras de viaje, no de atracciones.",
        "fit_heading": "Cómo se comporta este destino según las estructuras de viaje",
        "fit_intro": "Los niveles de ajuste por familia son priores estructurales del conjunto de datos gobernado de destinos: describen cómo tiende el lugar a sostener cada familia de estructuras antes de aplicar el contexto del viajero. No son veredictos, y ningún destino es universalmente mejor.",
        "structures_in_family_label": "Estructuras de esta familia",
        "facts_heading": "Datos estructurales",
        "seasons_label": "Mejores temporadas",
        "duration_label": "Duración típica",
        "region_label": "Región",
        "sources_heading": "Fuentes oficiales",
        "sources_intro": "Los datos del destino deben verificarse con el organismo oficial responsable. Estos enlaces salen de TourVsTravel.",
        "next_heading": "Decide primero la estructura",
        "next_intro": "El mismo destino no es el mismo viaje. Ejecuta la Brújula para diagnosticar qué estructuras encajan con tus restricciones, o lee la ontología en la que se basa el diagnóstico.",
        "link_compass": "Brújula de Decisión de Viaje",
        "link_ontology": "Ontología de estructuras de viaje (TSO) v1",
        "link_destinations": "Todos los destinos",
    },
    "de": {
        "lead_suffix": "Interpretiert durch Reisestrukturen, nicht Attraktionen.",
        "fit_heading": "Wie sich dieses Ziel über Reisestrukturen hinweg verhält",
        "fit_intro": "Familien-Passungswerte sind strukturelle Prioren aus dem regelgeleiteten Reiseziel-Datensatz: Sie beschreiben, wie der Ort jede Strukturfamilie tendenziell trägt, bevor der Reisendenkontext angewendet wird. Sie sind keine Urteile, und kein Ziel ist universell das beste.",
        "structures_in_family_label": "Strukturen dieser Familie",
        "facts_heading": "Strukturelle Eckdaten",
        "seasons_label": "Beste Reisezeiten",
        "duration_label": "Typische Dauer",
        "region_label": "Region",
        "sources_heading": "Offizielle Quellen",
        "sources_intro": "Zielfakten sollten bei der zuständigen offiziellen Stelle geprüft werden. Diese Links verlassen TourVsTravel.",
        "next_heading": "Entscheiden Sie zuerst die Struktur",
        "next_intro": "Dasselbe Ziel ist nicht dieselbe Reise. Führen Sie den Kompass aus, um passende Strukturen für Ihre Beschränkungen zu diagnostizieren, oder lesen Sie die Ontologie, auf der die Diagnose beruht.",
        "link_compass": "Reise-Entscheidungskompass",
        "link_ontology": "Ontologie der Reisestrukturen (TSO) v1",
        "link_destinations": "Alle Reiseziele",
    },
    "zh": {
        "lead_suffix": "通过旅行结构而非景点来解读。",
        "fit_heading": "这一目的地在不同旅行结构下的表现",
        "fit_intro": "家族适配等级是来自受治理目的地数据集的结构性先验：它们描述在应用旅行者情境之前，该地倾向于如何支撑每个结构族。它们不是结论，也没有对所有人都最优的目的地。",
        "structures_in_family_label": "该族中的结构",
        "facts_heading": "结构要点",
        "seasons_label": "最佳季节",
        "duration_label": "典型时长",
        "region_label": "地区",
        "sources_heading": "官方来源",
        "sources_intro": "目的地信息应向负责的官方机构核实。这些链接将离开 TourVsTravel。",
        "next_heading": "先决定结构",
        "next_intro": "同一目的地并非同一旅程。运行指南针来诊断哪些结构符合你的约束，或阅读诊断所依据的本体。",
        "link_compass": "旅行决策指南针",
        "link_ontology": "旅行结构本体（TSO）v1",
        "link_destinations": "全部目的地",
    },
    "ja": {
        "lead_suffix": "観光名所ではなく旅行構造で読み解く。",
        "fit_heading": "この目的地が旅行構造ごとにどう振る舞うか",
        "fit_intro": "ファミリー適合レベルは、統治された目的地データセットに基づく構造的事前値である。旅行者の文脈を適用する前に、その土地が各構造ファミリーをどう支える傾向にあるかを記述する。評決ではなく、普遍的に最良の目的地は存在しない。",
        "structures_in_family_label": "このファミリーの構造",
        "facts_heading": "構造ファクト",
        "seasons_label": "最適な季節",
        "duration_label": "典型的な期間",
        "region_label": "地域",
        "sources_heading": "公式ソース",
        "sources_intro": "目的地に関する事実は、責任ある公式機関で確認すべきである。これらのリンクは TourVsTravel の外部へ移動する。",
        "next_heading": "まず構造を決める",
        "next_intro": "同じ目的地は同じ旅ではない。コンパスを実行して制約に合う構造を診断するか、診断の基盤であるオントロジーを読むこと。",
        "link_compass": "トラベル・ディシジョン・コンパス",
        "link_ontology": "旅行構造オントロジー（TSO）v1",
        "link_destinations": "すべての目的地",
    },
}


# ============================================================================
# Dataset loading and validation (fail closed)
# ============================================================================

def _ensure_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise GenerateDestinationPagesError(f"{label} must be a mapping/object.")
    return value


def _ensure_string(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise GenerateDestinationPagesError(f"{label} must be a string.")
    text = value.strip()
    if not text:
        raise GenerateDestinationPagesError(f"{label} must not be empty.")
    return text


def _require_all_languages(value: Any, label: str) -> Dict[str, str]:
    mapping = _ensure_mapping(value, label)
    return {lang: _ensure_string(mapping.get(lang), f"{label}.{lang}") for lang in SUPPORTED_LANGUAGES}


def load_governed_destinations() -> List[Dict[str, Any]]:
    items = load_destinations()
    output: List[Dict[str, Any]] = []
    for idx, raw in enumerate(items):
        item = _ensure_mapping(raw, f"destinations[{idx}]")
        if item.get("enabled") is False:
            continue
        dest_id = _ensure_string(item.get("id"), f"destinations[{idx}].id")

        fit_raw = _ensure_mapping(item.get("family_fit"), f"destinations[{idx}].family_fit")
        family_fit: Dict[str, str] = {}
        for family_id in FAMILY_ORDER:
            level = _ensure_string(fit_raw.get(family_id), f"destinations[{idx}].family_fit.{family_id}")
            if level not in FIT_SCALE:
                raise GenerateDestinationPagesError(
                    f"destinations[{idx}].family_fit.{family_id} must be one of {FIT_SCALE}, got {level!r}"
                )
            family_fit[family_id] = level

        sources_raw = item.get("sources")
        if not isinstance(sources_raw, list) or not sources_raw:
            raise GenerateDestinationPagesError(f"destinations[{idx}].sources must be a non-empty list.")
        sources: List[Dict[str, str]] = []
        for sidx, source in enumerate(sources_raw):
            source_map = _ensure_mapping(source, f"destinations[{idx}].sources[{sidx}]")
            url = _ensure_string(source_map.get("url"), f"destinations[{idx}].sources[{sidx}].url")
            if not url.startswith("https://"):
                raise GenerateDestinationPagesError(
                    f"destinations[{idx}].sources[{sidx}].url must be HTTPS: {url!r}"
                )
            sources.append({
                "label": _ensure_string(source_map.get("label"), f"destinations[{idx}].sources[{sidx}].label"),
                "url": url,
            })

        output.append({
            "id": dest_id,
            "order": item.get("order", idx),
            "name": _require_all_languages(item.get("name"), f"destinations[{idx}].name"),
            "region": _require_all_languages(item.get("region"), f"destinations[{idx}].region"),
            "summary": _require_all_languages(item.get("summary"), f"destinations[{idx}].summary"),
            "best_seasons": _require_all_languages(item.get("best_seasons"), f"destinations[{idx}].best_seasons"),
            "typical_duration": _require_all_languages(
                item.get("typical_duration"), f"destinations[{idx}].typical_duration"),
            "family_fit": family_fit,
            "sources": sources,
        })

    if not output:
        raise GenerateDestinationPagesError("No enabled destinations found in destinations.yaml.")
    output.sort(key=lambda entry: entry["order"])
    return output


def _load_family_labels() -> Dict[str, Dict[str, str]]:
    data = load_experience_types()
    families = data.get("families")
    if not isinstance(families, list):
        raise GenerateDestinationPagesError("experience_types.families must be a list.")
    labels: Dict[str, Dict[str, str]] = {}
    for idx, family in enumerate(families):
        fam = _ensure_mapping(family, f"families[{idx}]")
        fam_id = _ensure_string(fam.get("id"), f"families[{idx}].id")
        labels[fam_id] = _require_all_languages(fam.get("label"), f"families[{idx}].label")
    missing = set(FAMILY_ORDER) - set(labels)
    if missing:
        raise GenerateDestinationPagesError(f"experience_types.families missing ids: {sorted(missing)}")
    return labels


# ============================================================================
# Rendering plumbing
# ============================================================================

def _extract_enabled_languages(site_config: Mapping[str, Any]) -> List[str]:
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
    site = site_config.get("site")
    if isinstance(site, Mapping):
        name = site.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return "TourVsTravel"


def _extract_theme_color(site_config: Mapping[str, Any]) -> str:
    branding = site_config.get("branding")
    if isinstance(branding, Mapping):
        color = branding.get("theme_color")
        if isinstance(color, str) and color.strip():
            return color.strip()
    return "#0f172a"


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
        raise GenerateDestinationPagesError(f"{label} must start with /static/: {path}")
    asset_path = (ROOT_DIR / path.lstrip("/")).resolve()
    try:
        asset_path.relative_to(STATIC_DIR.resolve())
    except ValueError as exc:
        raise GenerateDestinationPagesError(f"{label} escapes static directory: {path}") from exc
    if not asset_path.is_file():
        raise GenerateDestinationPagesError(f"Missing static asset for {label}: {path}")
    return path


def _resolve_logo_path(site_config: Mapping[str, Any]) -> str:
    branding = site_config.get("branding")
    if isinstance(branding, Mapping):
        logo = branding.get("logo_path")
        if isinstance(logo, str) and logo.strip():
            return logo.strip()
    return "/static/img/brand/logo-icon.webp"


def _resolve_manifest_url() -> str:
    candidate = ROOT_DIR / "static" / "site.webmanifest"
    return "/static/site.webmanifest" if candidate.is_file() else ""


def _create_jinja_env() -> Environment:
    if not TEMPLATES_DIR.exists():
        raise GenerateDestinationPagesError(f"Missing templates directory: {TEMPLATES_DIR}")
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
        raise GenerateDestinationPagesError(f"Unable to write {path}: {exc}") from exc


def _ensure_safe_output_dir(output_dir: Path) -> Path:
    resolved = output_dir.resolve()
    if str(resolved) == resolved.anchor:
        raise GenerateDestinationPagesError(f"Refusing filesystem root as output directory: {resolved}")
    if resolved.exists() and resolved.is_symlink():
        raise GenerateDestinationPagesError(f"Refusing symlink output directory: {resolved}")
    return resolved


def _build_family_fit_view(
    site_config: Mapping[str, Any],
    destination: Mapping[str, Any],
    structures: Sequence[Mapping[str, Any]],
    family_labels: Mapping[str, Mapping[str, str]],
    lang: str,
) -> List[Dict[str, Any]]:
    members_by_family: Dict[str, List[Dict[str, str]]] = {family_id: [] for family_id in FAMILY_ORDER}
    for structure in structures:
        family_id = structure["family"]
        if family_id in members_by_family:
            members_by_family[family_id].append({
                "label": structure["label"][lang],
                "url": build_experience_type_path(site_config, lang, structure["slug"], absolute=False),
            })

    view: List[Dict[str, Any]] = []
    for family_id in FAMILY_ORDER:
        members = members_by_family[family_id]
        if not members:
            raise GenerateDestinationPagesError(f"Ontology family {family_id!r} has no member structures.")
        fit_value = destination["family_fit"][family_id]
        view.append({
            "id": family_id,
            "label": family_labels[family_id][lang],
            "fit_value": fit_value,
            "fit_label": VALUE_LABELS[fit_value][lang],
            "members": members,
        })
    return view


def _build_context(
    *,
    site_config: Mapping[str, Any],
    destination: Mapping[str, Any],
    structures: Sequence[Mapping[str, Any]],
    family_labels: Mapping[str, Mapping[str, str]],
    lang: str,
) -> Dict[str, Any]:
    copy = PAGE_COPY[lang]
    site = _ensure_mapping(site_config.get("site"), "site_config.site")
    base_url = _ensure_string(site.get("base_url", "https://tourvstravel.com"), "site.base_url").rstrip("/")
    site_name = _extract_site_name(site_config, lang)
    logo_url = _resolve_logo_path(site_config)

    localized_destination = {
        "id": destination["id"],
        "name": destination["name"][lang],
        "region": destination["region"][lang],
        "summary": destination["summary"][lang],
        "best_seasons": destination["best_seasons"][lang],
        "typical_duration": destination["typical_duration"][lang],
        "sources": destination["sources"],
    }

    canonical_url = build_destination_path(site_config, lang, destination["id"], absolute=True)
    title = f"{localized_destination['name']} | {site_name}"
    description = localized_destination["summary"]
    urls_by_lang = build_destination_language_url_map(site_config, destination["id"])

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
        "destination": localized_destination,
        "family_fit": _build_family_fit_view(site_config, destination, structures, family_labels, lang),
        "canonical_url": canonical_url,
        "seo": seo_payload,
        "hreflang": seo_payload.get("hreflang", []),
        "meta_desc": seo_payload.get("description", ""),
        "robots_directive": seo_payload.get("robots_directive", "index, follow"),
        "body_class": "page-destination",
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
        "active_nav": "destinations",
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
        "url_ontology": build_ontology_path(site_config, lang, absolute=False),
        "url_standard": build_standard_path(site_config, lang, absolute=False),
        "url_changelog": build_changelog_path(site_config, lang, absolute=False),
    }
    context.update(localized_ui_context(lang))
    return context


def generate_destination_detail_pages(
    *,
    requested_lang: Optional[str] = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> List[Path]:
    safe_output_dir = _ensure_safe_output_dir(output_dir)
    site_config = load_site_config()
    if not isinstance(site_config, Mapping):
        raise GenerateDestinationPagesError("load_site_config() must return a mapping/object.")

    if requested_lang is not None:
        lang = requested_lang.strip()
        if lang not in SUPPORTED_LANGUAGES:
            raise GenerateDestinationPagesError(f"Unsupported language requested: {requested_lang!r}")
        languages = [lang]
    else:
        languages = _extract_enabled_languages(site_config)

    destinations = load_governed_destinations()
    try:
        structures = load_ontology_structures()
    except GenerateCategoryInfrastructureError as exc:
        raise GenerateDestinationPagesError(f"Ontology loading failed: {exc}") from exc
    family_labels = _load_family_labels()

    env = _create_jinja_env()
    try:
        template = env.get_template(TEMPLATE_NAME)
    except TemplateError as exc:
        raise GenerateDestinationPagesError(f"Unable to load template {TEMPLATE_NAME}: {exc}") from exc

    written: List[Path] = []
    for destination in destinations:
        for lang in languages:
            context = _build_context(
                site_config=site_config,
                destination=destination,
                structures=structures,
                family_labels=family_labels,
                lang=lang,
            )
            try:
                html_out = template.render(**context)
            except TemplateError as exc:
                raise GenerateDestinationPagesError(
                    f"Unable to render destination page {destination['id']!r} [{lang}]: {exc}"
                ) from exc
            if not html_out.strip():
                raise GenerateDestinationPagesError(
                    f"Rendered destination page is empty: {destination['id']!r} [{lang}]"
                )
            output_path = safe_output_dir / lang / "destinations" / destination["id"] / "index.html"
            _atomic_write_text(output_path, html_out)
            written.append(output_path)
            log.info("Generated destination page [%s/%s] -> %s", destination["id"], lang, output_path)
    return written


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate TourVsTravel destination detail pages.")
    parser.add_argument("--lang", type=str, default=None, help="Generate one language only.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    args = parse_args(argv)
    try:
        generate_destination_detail_pages(requested_lang=args.lang, output_dir=args.output_dir)
    except GenerateDestinationPagesError as exc:
        log.error(str(exc))
        return 1
    except Exception as exc:
        log.exception("Unexpected destination page generation failure: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
