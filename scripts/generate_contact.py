#!/usr/bin/env python3
"""
TourVsTravel — Contact pages and legacy /reports/ alias
=======================================================

Generates:
  output/{lang}/contact/index.html
  output/{lang}/reports/index.html  (immediate redirect to ../report/)
"""

from __future__ import annotations

import argparse
import html
import json
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

log = logging.getLogger("generate_contact")

ROOT_DIR = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = ROOT_DIR / "templates"
STATIC_DIR = ROOT_DIR / "static"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "output"
TEMPLATE_NAME = "pages/contact.html"
SUPPORTED_LANGUAGES = ("en", "ar", "fr", "es", "de", "zh", "ja")

PAGE_COPY: Dict[str, Dict[str, str]] = {
    "en": {
        "title": "Contact",
        "lead": (
            "TourVsTravel is a reference infrastructure for comparing travel structures. "
            "For general questions, start with the methodology and reference report."
        ),
        "note_label": "Where to go next",
        "ln_methodology": "Methodology",
        "ln_report": "Reference report",
        "ln_compare": "Compare",
        "ln_tools": "Tools",
        "ln_destinations": "Destinations",
    },
    "ar": {
        "title": "اتصل بنا",
        "lead": (
            "TourVsTravel بنية مرجعية لمقارنة أشكال السفر. للأسئلة العامة، ابدأ بالمنهجية والتقرير المرجعي."
        ),
        "note_label": "الخطوات التالية",
        "ln_methodology": "المنهجية",
        "ln_report": "التقرير المرجعي",
        "ln_compare": "المقارنة",
        "ln_tools": "الأدوات",
        "ln_destinations": "الوجهات",
    },
    "fr": {
        "title": "Contact",
        "lead": (
            "TourVsTravel est une infrastructure de référence pour comparer des formes de voyage. "
            "Pour toute question générale, commencez par la méthodologie et le rapport de référence."
        ),
        "note_label": "Pour aller plus loin",
        "ln_methodology": "Méthodologie",
        "ln_report": "Rapport de référence",
        "ln_compare": "Comparer",
        "ln_tools": "Outils",
        "ln_destinations": "Destinations",
    },
    "es": {
        "title": "Contacto",
        "lead": (
            "TourVsTravel es una infraestructura de referencia para comparar formas de viaje. "
            "Para consultas generales, comience por la metodología y el informe de referencia."
        ),
        "note_label": "Próximos pasos",
        "ln_methodology": "Metodología",
        "ln_report": "Informe de referencia",
        "ln_compare": "Comparar",
        "ln_tools": "Herramientas",
        "ln_destinations": "Destinos",
    },
    "de": {
        "title": "Kontakt",
        "lead": (
            "TourVsTravel ist eine Referenzinfrastruktur zum Vergleichen von Reiseformen. "
            "Für allgemeine Fragen beginnen Sie mit Methodik und Referenzbericht."
        ),
        "note_label": "Weiter",
        "ln_methodology": "Methodik",
        "ln_report": "Referenzbericht",
        "ln_compare": "Vergleichen",
        "ln_tools": "Werkzeuge",
        "ln_destinations": "Reiseziele",
    },
    "zh": {
        "title": "联系",
        "lead": (
            "TourVsTravel 用于比较旅行方式的参考体系。一般问题请先阅读方法论与参考报告。"
        ),
        "note_label": "推荐阅读",
        "ln_methodology": "方法论",
        "ln_report": "参考报告",
        "ln_compare": "比较",
        "ln_tools": "工具",
        "ln_destinations": "目的地",
    },
    "ja": {
        "title": "お問い合わせ",
        "lead": (
            "TourVsTravel は旅行の構造を比較するための参照基盤です。一般的な質問は方法論とリファレンスレポートからどうぞ。"
        ),
        "note_label": "次のステップ",
        "ln_methodology": "方法論",
        "ln_report": "リファレンスレポート",
        "ln_compare": "比較",
        "ln_tools": "ツール",
        "ln_destinations": "目的地",
    },
}


class GenerateContactError(Exception):
    pass


def _ensure_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise GenerateContactError(f"{label} must be a mapping/object.")
    return value


def _ensure_string(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise GenerateContactError(f"{label} must be a string.")
    text = value.strip()
    if not text:
        raise GenerateContactError(f"{label} must not be empty.")
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
        raise GenerateContactError(f"{label} must start with /static/: {path}")
    asset_path = (ROOT_DIR / path.lstrip("/")).resolve()
    try:
        asset_path.relative_to(STATIC_DIR.resolve())
    except ValueError as exc:
        raise GenerateContactError(f"{label} escapes static directory: {path}") from exc
    if not asset_path.is_file():
        raise GenerateContactError(f"Missing static asset for {label}: {path}")
    return path


def _resolve_logo_path(site_config: Mapping[str, Any]) -> str:
    logo = _get_nested(site_config, ("branding", "logo_path"), "/static/img/brand/logo-icon.webp")
    return _ensure_string(logo, "branding.logo_path")


def _resolve_manifest_url() -> str:
    candidate = ROOT_DIR / "static" / "site.webmanifest"
    return "/static/site.webmanifest" if candidate.is_file() else ""


def _create_jinja_env() -> Environment:
    if not TEMPLATES_DIR.exists():
        raise GenerateContactError(f"Missing templates directory: {TEMPLATES_DIR}")
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
        raise GenerateContactError(f"Unable to write {path}: {exc}") from exc


def _ensure_safe_output_dir(output_dir: Path) -> Path:
    resolved = output_dir.resolve()
    if str(resolved) == resolved.anchor:
        raise GenerateContactError(f"Refusing filesystem root as output directory: {resolved}")
    if resolved.exists() and resolved.is_symlink():
        raise GenerateContactError(f"Refusing symlink output directory: {resolved}")
    return resolved


def _build_urls_by_lang(site_config: Mapping[str, Any], languages: Sequence[str]) -> Dict[str, str]:
    urls: Dict[str, str] = {}
    site = _ensure_mapping(site_config.get("site"), "site_config.site")
    raw_base = site.get("base_url", "https://tourvstravel.com")
    base = _ensure_string(raw_base, "site.base_url").rstrip("/")

    for code in languages:
        rel = build_contact_path(site_config, code, absolute=False)
        urls[code] = f"{base}{rel}" if rel.startswith("/") else f"{base}/{rel}"
    return urls


def _build_context(
    *,
    site_config: Mapping[str, Any],
    lang: str,
    languages: Sequence[str],
) -> Dict[str, Any]:
    copy = get_trust_page_copy("contact", lang)
    base_url = _ensure_string(
        _get_nested(site_config, ("site", "base_url"), "https://tourvstravel.com").strip().rstrip("/"),
        "site.base_url",
    )
    site_name = _extract_site_name(site_config, lang)
    logo_url = _resolve_logo_path(site_config)
    canonical_url = build_contact_path(site_config, lang, absolute=True)
    title = f"{copy['title']} | {site_name}"
    description = copy["lead"]

    urls_by_lang = _build_urls_by_lang(site_config, languages)

    organization_jsonld = build_organization_jsonld(site_config, logo_url=logo_url)
    website_jsonld = build_website_jsonld(
        site_config,
        lang,
        home_url=build_home_path(site_config, lang, absolute=True),
    )
    webpage_jsonld = build_webpage_jsonld(
        name=title,
        description=description,
        url=canonical_url,
        lang=lang,
        is_part_of_url=build_home_path(site_config, lang, absolute=True),
    )

    seo_payload = build_page_seo(
        site_config,
        lang,
        page_title=title,
        page_description=description,
        canonical_url=canonical_url,
        urls_by_lang=urls_by_lang,
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
        "body_class": "page-contact",
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
        "url_source_policy": build_source_policy_path(site_config, lang, absolute=False),
        "url_editorial_standards": build_editorial_standards_path(site_config, lang, absolute=False),
        "url_map": {
            "url_source_policy": build_source_policy_path(site_config, lang, absolute=False),
            "url_editorial_standards": build_editorial_standards_path(site_config, lang, absolute=False),
            "url_acquire": build_acquire_path(site_config, lang, absolute=False),
            "url_methodology": build_methodology_path(site_config, lang, absolute=False),
            "url_report": build_reference_report_path(site_config, lang, absolute=False),
        },
    }
    context.update(localized_ui_context(lang))
    return context


def render_contact_page(
    *,
    site_config: Mapping[str, Any],
    lang: str,
    languages: Sequence[str],
) -> str:
    env = _create_jinja_env()
    try:
        template = env.get_template(TEMPLATE_NAME)
    except TemplateError as exc:
        raise GenerateContactError(f"Unable to load template {TEMPLATE_NAME}: {exc}") from exc

    context = _build_context(site_config=site_config, lang=lang, languages=languages)
    try:
        html_out = template.render(**context)
    except TemplateError as exc:
        raise GenerateContactError(f"Unable to render contact page [{lang}]: {exc}") from exc
    if not html_out.strip():
        raise GenerateContactError(f"Rendered contact page is empty for language {lang!r}.")
    return html_out


def _render_reports_alias_page(*, site_config: Mapping[str, Any], lang: str) -> str:
    target = build_reference_report_path(site_config, lang, absolute=False)
    if not target.startswith("/"):
        target = f"/{target}"
    canonical = build_reference_report_path(site_config, lang, absolute=True)
    safe_target = html.escape(target, quote=True)
    safe_canonical = html.escape(canonical, quote=True)
    safe_lang = html.escape(lang, quote=True)
    return f"""<!DOCTYPE html>
<html lang="{safe_lang}">
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="0;url={safe_target}">
  <link rel="canonical" href="{safe_canonical}">
  <meta name="robots" content="noindex, follow">
  <title>Redirecting…</title>
  <script>window.location.replace({json.dumps(target)});</script>
</head>
<body>
  <p><a href="{safe_target}">Continue to reference report</a>.</p>
</body>
</html>
"""


def generate_contact_pages(
    *,
    requested_lang: Optional[str] = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> List[Path]:
    safe_output_dir = _ensure_safe_output_dir(output_dir)
    site_config = load_site_config()
    if not isinstance(site_config, Mapping):
        raise GenerateContactError("load_site_config() must return a mapping/object.")

    if requested_lang is not None:
        lang = requested_lang.strip()
        if lang not in SUPPORTED_LANGUAGES:
            raise GenerateContactError(f"Unsupported language requested: {requested_lang!r}")
        languages = [lang]
    else:
        languages = _extract_enabled_languages(site_config)

    if not languages:
        raise GenerateContactError("No enabled languages available for contact generation.")

    written: List[Path] = []
    for lang in languages:
        html_output = render_contact_page(
            site_config=site_config, lang=lang, languages=languages
        )
        output_path = safe_output_dir / lang / "contact" / "index.html"
        _atomic_write_text(output_path, html_output)
        written.append(output_path)
        log.info("Generated contact page [%s] -> %s", lang, output_path)

    for lang in languages:
        alias_html = _render_reports_alias_page(site_config=site_config, lang=lang)
        alias_path = safe_output_dir / lang / "reports" / "index.html"
        _atomic_write_text(alias_path, alias_html)
        written.append(alias_path)
        log.info("Generated reports alias [%s] -> %s", lang, alias_path)

    return written


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate TourVsTravel contact and /reports/ alias pages.")
    parser.add_argument("--lang", type=str, default=None, help="Generate one language only.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Output directory root.")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S",
        )
    args = parse_args(argv)
    try:
        generate_contact_pages(requested_lang=args.lang, output_dir=args.output_dir)
    except GenerateContactError as exc:
        log.error(str(exc))
        return 1
    except Exception as exc:
        log.exception("Unexpected contact generation failure: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
