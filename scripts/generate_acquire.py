#!/usr/bin/env python3
"""
TourVsTravel — Acquire pages
=============================
Generates:
  output/{lang}/acquire/index.html
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
from scripts.reference_i18n import localized_ui_context
from scripts.trust_authority_copy import get_trust_page_copy

log = logging.getLogger("generate_acquire")

ROOT_DIR = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = ROOT_DIR / "templates"
STATIC_DIR = ROOT_DIR / "static"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "output"
TEMPLATE_NAME = "pages/acquire.html"
SUPPORTED_LANGUAGES = ("en", "ar", "fr", "es", "de", "zh", "ja")

PAGE_COPY: Dict[str, Dict[str, str]] = {
    "en": {
        "title": "Acquire",
        "lead": "Information for organizations interested in licensing or acquiring TourVsTravel reference data or infrastructure.",
        "details_label": "What is available",
        "details_body": "TourVsTravel produces structured, multilingual reference data comparing travel experience types across destinations. Licensing inquiries for data sets, white-label infrastructure, or research partnerships are welcome.",
        "next_label": "Before you reach out",
        "ln_methodology": "Methodology",
        "ln_contact": "Contact",
    },
    "ar": {
        "title": "الاستحواذ",
        "lead": "معلومات للمؤسسات المهتمة بترخيص أو اقتناء بيانات أو بنية TourVsTravel المرجعية.",
        "details_label": "ما هو متاح",
        "details_body": "ينتج TourVsTravel بيانات مرجعية منظمة ومتعددة اللغات لمقارنة أنواع تجارب السفر عبر الوجهات. نرحب باستفسارات ترخيص مجموعات البيانات أو البنية ذات العلامة البيضاء أو شراكات البحث.",
        "next_label": "قبل التواصل",
        "ln_methodology": "المنهجية",
        "ln_contact": "اتصل بنا",
    },
    "fr": {
        "title": "Acquisition",
        "lead": "Informations pour les organisations souhaitant licencier ou acquérir les données de référence ou l’infrastructure TourVsTravel.",
        "details_label": "Ce qui est disponible",
        "details_body": "TourVsTravel produit des données de référence structurées et multilingues comparant les types d’expériences de voyage à travers les destinations. Les demandes de licence pour les ensembles de données, l’infrastructure en marque blanche ou les partenariats de recherche sont les bienvenues.",
        "next_label": "Avant de nous contacter",
        "ln_methodology": "Méthodologie",
        "ln_contact": "Contact",
    },
    "es": {
        "title": "Adquisición",
        "lead": "Información para organizaciones interesadas en licenciar o adquirir los datos de referencia o la infraestructura de TourVsTravel.",
        "details_label": "Qué está disponible",
        "details_body": "TourVsTravel produce datos de referencia estructurados y multilingües que comparan tipos de experiencias de viaje en diferentes destinos. Se aceptan consultas de licencias para conjuntos de datos, infraestructura de marca blanca o asociaciones de investigación.",
        "next_label": "Antes de contactarnos",
        "ln_methodology": "Metodología",
        "ln_contact": "Contacto",
    },
    "de": {
        "title": "Erwerb",
        "lead": "Informationen für Organisationen, die an der Lizenzierung oder dem Erwerb von TourVsTravel-Referenzdaten oder -Infrastruktur interessiert sind.",
        "details_label": "Was verfügbar ist",
        "details_body": "TourVsTravel produziert strukturierte, mehrsprachige Referenzdaten zum Vergleich von Reiseerfahrungstypen über Reiseziele hinweg. Lizenzanfragen für Datensätze, White-Label-Infrastruktur oder Forschungspartnerschaften sind willkommen.",
        "next_label": "Bevor Sie sich melden",
        "ln_methodology": "Methodik",
        "ln_contact": "Kontakt",
    },
    "zh": {
        "title": "获取",
        "lead": "面向有意授权或获取 TourVsTravel 参考数据或基础设施的机构的信息。",
        "details_label": "可获取内容",
        "details_body": "TourVsTravel 生成结构化、多语言参考数据，比较各目的地的旅行体验类型。欢迎就数据集、白标基础设施或研究合作的许可进行咋询。",
        "next_label": "联系我们之前",
        "ln_methodology": "方法论",
        "ln_contact": "联系我们",
    },
    "ja": {
        "title": "取得",
        "lead": "TourVsTravel のリファレンスデータまたはインフラのライセンスや取得に関心のある組織向け情報です。",
        "details_label": "利用可能なもの",
        "details_body": "TourVsTravel は、目的地別の旅行体験タイプを比較する構造化された多言語リファレンスデータを制作しています。データセット、ホワイトラベルインフラ、研究パートナーシップのライセンスに関するお問い合わせを歓迎します。",
        "next_label": "ご連絡の前に",
        "ln_methodology": "方法論",
        "ln_contact": "お問い合わせ",
    },
}


class GenerateAcquireError(Exception):
    pass


def _ensure_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise GenerateAcquireError(f"{label} must be a mapping/object.")
    return value


def _ensure_string(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise GenerateAcquireError(f"{label} must be a string.")
    text = value.strip()
    if not text:
        raise GenerateAcquireError(f"{label} must not be empty.")
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
    direction = _get_nested(site_config, ("languages", "direction", lang), None)
    if direction in {"rtl", "ltr"}:
        return str(direction)
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
        raise GenerateAcquireError(f"{label} must start with /static/: {path}")
    asset_path = (ROOT_DIR / path.lstrip("/")).resolve()
    try:
        asset_path.relative_to(STATIC_DIR.resolve())
    except ValueError as exc:
        raise GenerateAcquireError(f"{label} escapes static directory: {path}") from exc
    if not asset_path.is_file():
        raise GenerateAcquireError(f"Missing static asset for {label}: {path}")
    return path


def _resolve_logo_path(site_config: Mapping[str, Any]) -> str:
    logo = _get_nested(site_config, ("branding", "logo_path"), "/static/img/brand/logo-icon.webp")
    return _ensure_string(logo, "branding.logo_path")


def _resolve_manifest_url() -> str:
    candidate = ROOT_DIR / "static" / "site.webmanifest"
    return "/static/site.webmanifest" if candidate.is_file() else ""


def _create_jinja_env() -> Environment:
    if not TEMPLATES_DIR.exists():
        raise GenerateAcquireError(f"Missing templates directory: {TEMPLATES_DIR}")
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
        raise GenerateAcquireError(f"Unable to write {path}: {exc}") from exc


def _ensure_safe_output_dir(output_dir: Path) -> Path:
    resolved = output_dir.resolve()
    if str(resolved) == resolved.anchor:
        raise GenerateAcquireError(f"Refusing filesystem root as output directory: {resolved}")
    if resolved.exists() and resolved.is_symlink():
        raise GenerateAcquireError(f"Refusing symlink output directory: {resolved}")
    return resolved


def _build_urls_by_lang(site_config: Mapping[str, Any], languages: Sequence[str]) -> Dict[str, str]:
    urls: Dict[str, str] = {}
    site = _ensure_mapping(site_config.get("site"), "site_config.site")
    raw_base = site.get("base_url", "https://tourvstravel.com")
    base = _ensure_string(raw_base, "site.base_url").rstrip("/")
    for code in languages:
        rel = build_acquire_path(site_config, code, absolute=False)
        urls[code] = f"{base}{rel}" if rel.startswith("/") else f"{base}/{rel}"
    return urls


def _build_context(
    *,
    site_config: Mapping[str, Any],
    lang: str,
    languages: Sequence[str],
) -> Dict[str, Any]:
    copy = get_trust_page_copy("acquire", lang)
    base_url = _ensure_string(
        _get_nested(site_config, ("site", "base_url"), "https://tourvstravel.com").strip().rstrip("/"),
        "site.base_url",
    )
    site_name = _extract_site_name(site_config, lang)
    logo_url = _resolve_logo_path(site_config)
    canonical_url = build_acquire_path(site_config, lang, absolute=True)
    title = f"{copy['title']} | {site_name}"
    description = copy["lead"]
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
        "body_class": "page-acquire",
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
        "active_nav": "home",
        "nav_report_label": resolve_nav_report_label(site_config, lang),
        "footer_reference_report_label": resolve_footer_reference_report_label(site_config, lang),
        "footer_note": "",
        "url_methodology": build_methodology_path(site_config, lang, absolute=False),
        "url_report": build_reference_report_path(site_config, lang, absolute=False),
        "url_compare": build_compare_index_path(site_config, lang, absolute=False),
        "url_tools": build_tools_index_path(site_config, lang, absolute=False),
        "url_destinations": build_destinations_index_path(site_config, lang, absolute=False),
        "url_about": build_about_path(site_config, lang, absolute=False),
        "url_privacy": build_privacy_path(site_config, lang, absolute=False),
        "url_acquire": build_acquire_path(site_config, lang, absolute=False),
        "url_contact": build_contact_path(site_config, lang, absolute=False),
        "url_source_policy": build_source_policy_path(site_config, lang, absolute=False),
        "url_editorial_standards": build_editorial_standards_path(site_config, lang, absolute=False),
        "url_map": {
            "url_contact": build_contact_path(site_config, lang, absolute=False),
            "url_about": build_about_path(site_config, lang, absolute=False),
            "url_methodology": build_methodology_path(site_config, lang, absolute=False),
            "url_editorial_standards": build_editorial_standards_path(site_config, lang, absolute=False),
            "url_travel_decision_architecture": build_travel_decision_architecture_path(site_config, lang, absolute=False),
        },
    }
    context.update(localized_ui_context(lang))
    return context


def render_acquire_page(
    *,
    site_config: Mapping[str, Any],
    lang: str,
    languages: Sequence[str],
) -> str:
    env = _create_jinja_env()
    try:
        template = env.get_template(TEMPLATE_NAME)
    except TemplateError as exc:
        raise GenerateAcquireError(f"Unable to load template {TEMPLATE_NAME}: {exc}") from exc
    context = _build_context(site_config=site_config, lang=lang, languages=languages)
    try:
        html_out = template.render(**context)
    except TemplateError as exc:
        raise GenerateAcquireError(f"Unable to render acquire page [{lang}]: {exc}") from exc
    if not html_out.strip():
        raise GenerateAcquireError(f"Rendered acquire page is empty for language {lang!r}.")
    return html_out


def generate_acquire_pages(
    *,
    requested_lang: Optional[str] = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> List[Path]:
    safe_output_dir = _ensure_safe_output_dir(output_dir)
    site_config = load_site_config()
    if not isinstance(site_config, Mapping):
        raise GenerateAcquireError("load_site_config() must return a mapping/object.")
    if requested_lang is not None:
        lang = requested_lang.strip()
        if lang not in SUPPORTED_LANGUAGES:
            raise GenerateAcquireError(f"Unsupported language requested: {requested_lang!r}")
        languages = [lang]
    else:
        languages = _extract_enabled_languages(site_config)
    if not languages:
        raise GenerateAcquireError("No enabled languages available for acquire generation.")
    written: List[Path] = []
    for lang in languages:
        html_output = render_acquire_page(site_config=site_config, lang=lang, languages=languages)
        output_path = safe_output_dir / lang / "acquire" / "index.html"
        _atomic_write_text(output_path, html_output)
        written.append(output_path)
        log.info("Generated acquire page [%s] -> %s", lang, output_path)
    return written


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate TourVsTravel acquire pages.")
    parser.add_argument("--lang", type=str, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    args = parse_args(argv)
    try:
        generate_acquire_pages(requested_lang=args.lang, output_dir=args.output_dir)
    except GenerateAcquireError as exc:
        log.error(str(exc))
        return 1
    except Exception as exc:
        log.exception("Unexpected acquire generation failure: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
