#!/usr/bin/env python3
"""
TourVsTravel — Editorial standards pages
==========================================
Generates:
  output/{lang}/methodology/editorial-standards/index.html
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
)
from scripts.seo import (
    build_organization_jsonld,
    build_page_seo,
    build_webpage_jsonld,
    build_website_jsonld,
)
from scripts.reference_i18n import localized_ui_context
from scripts.trust_authority_copy import get_trust_page_copy

log = logging.getLogger("generate_editorial_standards")

ROOT_DIR = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = ROOT_DIR / "templates"
STATIC_DIR = ROOT_DIR / "static"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "output"
TEMPLATE_NAME = "pages/editorial_standards.html"
SUPPORTED_LANGUAGES = ("en", "ar", "fr", "es", "de", "zh", "ja")

PAGE_COPY: Dict[str, Dict[str, str]] = {
    "en": {
        "title": "Editorial Standards",
        "lead": "The principles that govern how TourVsTravel researches, writes, and publishes travel experience comparisons.",
        "principles_label": "Core principles",
        "principles_body": "All comparisons are produced without commercial bias. We do not accept payment for favorable treatment of any travel product, operator, or destination. Comparisons aim to be structurally accurate and reproducible from primary sources.",
        "process_label": "Review process",
        "process_body": "Each comparison page undergoes a factual review against the documented methodology before publication. Material changes to comparison criteria are versioned and noted in the methodology section.",
        "see_also_label": "See also",
        "ln_methodology": "Methodology",
        "ln_source_policy": "Source policy",
    },
    "ar": {
        "title": "معايير التحرير",
        "lead": "المبادئ التي تحكم كيفية بحث TourVsTravel وكتابة ونشر مقارنات تجارب السفر.",
        "principles_label": "المبادئ الأساسية",
        "principles_body": "تُنتج جميع المقارنات دون تحيز تجاري. لا نقبل الدفع مقابل المعاملة التفضيلية لأي منتج سفر أو مشغّل أو وجهة. تهدف المقارنات إلى أن تكون دقيقة هيكليًا وقابلة للتحقق من المصادر الأولية.",
        "process_label": "عملية المراجعة",
        "process_body": "تخضع كل صفحة مقارنة لمراجعة واقعية وفق المنهجية الموثقة قبل النشر. تُوثَّق التغييرات الجوهرية على معايير المقارنة وتُشار إليها في قسم المنهجية.",
        "see_also_label": "انظر أيضًا",
        "ln_methodology": "المنهجية",
        "ln_source_policy": "سياسة المصادر",
    },
    "fr": {
        "title": "Normes éditoriales",
        "lead": "Les principes qui régissent la façon dont TourVsTravel recherche, rédige et publie les comparaisons d’expériences de voyage.",
        "principles_label": "Principes fondamentaux",
        "principles_body": "Toutes les comparaisons sont produites sans biais commercial. Nous n’acceptons pas de paiement pour un traitement favorable de tout produit de voyage, opérateur ou destination. Les comparaisons visent à être structurellement précises et reproductibles à partir de sources primaires.",
        "process_label": "Processus de révision",
        "process_body": "Chaque page de comparaison fait l’objet d’une révision factuelle selon la méthodologie documentée avant publication. Les modifications importantes des critères de comparaison sont versionnées et notées dans la section méthodologie.",
        "see_also_label": "Voir aussi",
        "ln_methodology": "Méthodologie",
        "ln_source_policy": "Politique de sources",
    },
    "es": {
        "title": "Estándares editoriales",
        "lead": "Los principios que rigen cómo TourVsTravel investiga, escribe y publica comparaciones de experiencias de viaje.",
        "principles_label": "Principios fundamentales",
        "principles_body": "Todas las comparaciones se producen sin sesgo comercial. No aceptamos pagos por tratamiento favorable de ningún producto de viaje, operador o destino. Las comparaciones buscan ser estructuralmente precisas y reproducibles a partir de fuentes primarias.",
        "process_label": "Proceso de revisión",
        "process_body": "Cada página de comparación se somete a una revisión factual según la metodología documentada antes de su publicación. Los cambios materiales en los criterios de comparación se versionan y se anotan en la sección de metodología.",
        "see_also_label": "Véase también",
        "ln_methodology": "Metodología",
        "ln_source_policy": "Política de fuentes",
    },
    "de": {
        "title": "Redaktionelle Standards",
        "lead": "Die Grundsätze, die regeln, wie TourVsTravel Reiseerfahrungsvergleiche recherchiert, schreibt und veröffentlicht.",
        "principles_label": "Grundprinzipien",
        "principles_body": "Alle Vergleiche werden ohne kommerzielle Voreingenommenheit erstellt. Wir akzeptieren keine Zahlungen für eine bevorzugte Behandlung von Reiseprodukten, Betreibern oder Reisezielen. Vergleiche zielen darauf ab, strukturell korrekt und aus Primärquellen reproduzierbar zu sein.",
        "process_label": "Überprüfungsprozess",
        "process_body": "Jede Vergleichsseite wird vor der Veröffentlichung einer sachlichen Überprüfung anhand der dokumentierten Methodik unterzogen. Wesentliche Änderungen der Vergleichskriterien werden versioniert und im Methodik-Abschnitt vermerkt.",
        "see_also_label": "Siehe auch",
        "ln_methodology": "Methodik",
        "ln_source_policy": "Quellenrichtlinie",
    },
    "zh": {
        "title": "编辑标准",
        "lead": "规范 TourVsTravel 研究、撰写和发布旅行体验比较内容的原则。",
        "principles_label": "核心原则",
        "principles_body": "所有比较均在无商业偏见的情况下生成。我们不接受任何旅行产品、运营商或目的地的付费优待。比较旨在结构准确，并可从主要来源重现。",
        "process_label": "审核流程",
        "process_body": "每个比较页面在发布前均根据已记录的方法论进行事实核查。比较标准的重大变更将进行版本管理，并在方法论部分注明。",
        "see_also_label": "另见",
        "ln_methodology": "方法论",
        "ln_source_policy": "信息来源政策",
    },
    "ja": {
        "title": "編集基準",
        "lead": "TourVsTravel が旅行体験比較を調査・執筆・公開する方法を規定する原則について。",
        "principles_label": "基本原則",
        "principles_body": "すべての比較は商業的バイアスなしに作成されます。旅行商品、オペレーター、目的地の否派ない取り扱いに対する支払いは一切受け付けておりません。比較は構造的に正確であり、一次情報源から再現可能であることを目指しています。",
        "process_label": "レビュープロセス",
        "process_body": "各比較ページは公開前に、文書化された方法論に基づいて事実確認を受けます。比較基準への重要な変更はバージョン管理され、方法論のセクションに記載されます。",
        "see_also_label": "関連情報",
        "ln_methodology": "方法論",
        "ln_source_policy": "情報源ポリシー",
    },
}


class GenerateEditorialStandardsError(Exception):
    pass


def _ensure_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise GenerateEditorialStandardsError(f"{label} must be a mapping/object.")
    return value


def _ensure_string(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise GenerateEditorialStandardsError(f"{label} must be a string.")
    text = value.strip()
    if not text:
        raise GenerateEditorialStandardsError(f"{label} must not be empty.")
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
        raise GenerateEditorialStandardsError(f"{label} must start with /static/: {path}")
    asset_path = (ROOT_DIR / path.lstrip("/")).resolve()
    try:
        asset_path.relative_to(STATIC_DIR.resolve())
    except ValueError as exc:
        raise GenerateEditorialStandardsError(f"{label} escapes static directory: {path}") from exc
    if not asset_path.is_file():
        raise GenerateEditorialStandardsError(f"Missing static asset for {label}: {path}")
    return path


def _resolve_logo_path(site_config: Mapping[str, Any]) -> str:
    logo = _get_nested(site_config, ("branding", "logo_path"), "/static/img/brand/logo-icon.webp")
    return _ensure_string(logo, "branding.logo_path")


def _resolve_manifest_url() -> str:
    candidate = ROOT_DIR / "static" / "site.webmanifest"
    return "/static/site.webmanifest" if candidate.is_file() else ""


def _create_jinja_env() -> Environment:
    if not TEMPLATES_DIR.exists():
        raise GenerateEditorialStandardsError(f"Missing templates directory: {TEMPLATES_DIR}")
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
        raise GenerateEditorialStandardsError(f"Unable to write {path}: {exc}") from exc


def _ensure_safe_output_dir(output_dir: Path) -> Path:
    resolved = output_dir.resolve()
    if str(resolved) == resolved.anchor:
        raise GenerateEditorialStandardsError(f"Refusing filesystem root as output directory: {resolved}")
    if resolved.exists() and resolved.is_symlink():
        raise GenerateEditorialStandardsError(f"Refusing symlink output directory: {resolved}")
    return resolved


def _build_urls_by_lang(site_config: Mapping[str, Any], languages: Sequence[str]) -> Dict[str, str]:
    urls: Dict[str, str] = {}
    site = _ensure_mapping(site_config.get("site"), "site_config.site")
    raw_base = site.get("base_url", "https://tourvstravel.com")
    base = _ensure_string(raw_base, "site.base_url").rstrip("/")
    for code in languages:
        rel = build_editorial_standards_path(site_config, code, absolute=False)
        urls[code] = f"{base}{rel}" if rel.startswith("/") else f"{base}/{rel}"
    return urls


def _build_context(
    *,
    site_config: Mapping[str, Any],
    lang: str,
    languages: Sequence[str],
) -> Dict[str, Any]:
    copy = get_trust_page_copy("editorial_standards", lang)
    base_url = _ensure_string(
        _get_nested(site_config, ("site", "base_url"), "https://tourvstravel.com").strip().rstrip("/"),
        "site.base_url",
    )
    site_name = _extract_site_name(site_config, lang)
    logo_url = _resolve_logo_path(site_config)
    canonical_url = build_editorial_standards_path(site_config, lang, absolute=True)
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
        "body_class": "page-editorial-standards",
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
            "url_source_policy": build_source_policy_path(site_config, lang, absolute=False),
            "url_methodology": build_methodology_path(site_config, lang, absolute=False),
            "url_about": build_about_path(site_config, lang, absolute=False),
            "url_contact": build_contact_path(site_config, lang, absolute=False),
        },
    }
    context.update(localized_ui_context(lang))
    return context


def render_editorial_standards_page(
    *,
    site_config: Mapping[str, Any],
    lang: str,
    languages: Sequence[str],
) -> str:
    env = _create_jinja_env()
    try:
        template = env.get_template(TEMPLATE_NAME)
    except TemplateError as exc:
        raise GenerateEditorialStandardsError(f"Unable to load template {TEMPLATE_NAME}: {exc}") from exc
    context = _build_context(site_config=site_config, lang=lang, languages=languages)
    try:
        html_out = template.render(**context)
    except TemplateError as exc:
        raise GenerateEditorialStandardsError(f"Unable to render editorial standards page [{lang}]: {exc}") from exc
    if not html_out.strip():
        raise GenerateEditorialStandardsError(f"Rendered editorial standards page is empty for language {lang!r}.")
    return html_out


def generate_editorial_standards_pages(
    *,
    requested_lang: Optional[str] = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> List[Path]:
    safe_output_dir = _ensure_safe_output_dir(output_dir)
    site_config = load_site_config()
    if not isinstance(site_config, Mapping):
        raise GenerateEditorialStandardsError("load_site_config() must return a mapping/object.")
    if requested_lang is not None:
        lang = requested_lang.strip()
        if lang not in SUPPORTED_LANGUAGES:
            raise GenerateEditorialStandardsError(f"Unsupported language requested: {requested_lang!r}")
        languages = [lang]
    else:
        languages = _extract_enabled_languages(site_config)
    if not languages:
        raise GenerateEditorialStandardsError("No enabled languages available for editorial standards generation.")
    written: List[Path] = []
    for lang in languages:
        html_output = render_editorial_standards_page(site_config=site_config, lang=lang, languages=languages)
        output_path = safe_output_dir / lang / "methodology" / "editorial-standards" / "index.html"
        _atomic_write_text(output_path, html_output)
        written.append(output_path)
        log.info("Generated editorial standards page [%s] -> %s", lang, output_path)
    return written


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate TourVsTravel editorial standards pages.")
    parser.add_argument("--lang", type=str, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    args = parse_args(argv)
    try:
        generate_editorial_standards_pages(requested_lang=args.lang, output_dir=args.output_dir)
    except GenerateEditorialStandardsError as exc:
        log.error(str(exc))
        return 1
    except Exception as exc:
        log.exception("Unexpected editorial standards generation failure: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
