#!/usr/bin/env python3
"""
TourVsTravel — Source policy pages
====================================
Generates:
  output/{lang}/methodology/source-policy/index.html
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
from scripts.trust_authority_copy import get_trust_page_copy

log = logging.getLogger("generate_source_policy")

ROOT_DIR = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = ROOT_DIR / "templates"
STATIC_DIR = ROOT_DIR / "static"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "output"
TEMPLATE_NAME = "pages/source_policy.html"
SUPPORTED_LANGUAGES = ("en", "ar", "fr", "es", "de", "zh", "ja")

PAGE_COPY: Dict[str, Dict[str, str]] = {
    "en": {
        "title": "Source Policy",
        "lead": "How TourVsTravel selects, evaluates, and cites information used in travel experience comparisons.",
        "standards_label": "Sourcing standards",
        "standards_body": "All factual claims used in comparisons draw from primary sources: official tourism authority data, peer-reviewed academic research, and publicly documented operator specifications. We do not accept sponsored placements or affiliate arrangements that influence content.",
        "types_label": "Source types",
        "types_body": "Accepted source categories include government tourism statistics, published academic studies on travel behavior, certified operator specifications, and independently verified traveler accounts. Unverifiable anecdotal sources are excluded.",
        "see_also_label": "See also",
        "ln_methodology": "Methodology",
        "ln_editorial_standards": "Editorial standards",
    },
    "ar": {
        "title": "سياسة المصادر",
        "lead": "كيف يختار TourVsTravel المعلومات المستخدمة في مقارنات تجارب السفر ويقيّمها ويستشهد بها.",
        "standards_label": "معايير الاستشهاد بالمصادر",
        "standards_body": "تستند جميع الادعاءات الواقعية المستخدمة في المقارنات إلى مصادر أولية: بيانات هيئات السياحة الرسمية، والأبحاث الأكاديمية المحكّمة، ومواصفات المشغّلين الموثقة علنًا. لا نقبل عروضًا برعاية أو ترتيبات تسويق بالعمولة تؤثر على المحتوى.",
        "types_label": "أنواع المصادر",
        "types_body": "تشمل فئات المصادر المقبولة: الإحصائيات السياحية الحكومية، والدراسات الأكاديمية المنشورة حول سلوك السفر، ومواصفات المشغّلين المعتمدين، وروايات المسافرين التي تم التحقق منها بشكل مستقل. تُستبعد المصادر الشفهية غير القابلة للتحقق.",
        "see_also_label": "انظر أيضًا",
        "ln_methodology": "المنهجية",
        "ln_editorial_standards": "معايير التحرير",
    },
    "fr": {
        "title": "Politique de sources",
        "lead": "Comment TourVsTravel sélectionne, évalue et cite les informations utilisées dans les comparaisons d’expériences de voyage.",
        "standards_label": "Normes de sourcing",
        "standards_body": "Toutes les affirmations factuelles utilisées dans les comparaisons proviennent de sources primaires : données officielles des autorités touristiques, recherches académiques évaluées par des pairs et spécifications d’opérateurs documentées publiquement. Nous n’acceptons pas de placements sponsorisés ni d’arrangements d’affiliation influencant le contenu.",
        "types_label": "Types de sources",
        "types_body": "Les catégories de sources acceptées comprennent les statistiques touristiques gouvernementales, les études académiques publiées sur le comportement des voyageurs, les spécifications d’opérateurs certifiés et les témoignages de voyageurs vérifiés indépendamment. Les sources anecdotiques invérifiables sont exclues.",
        "see_also_label": "Voir aussi",
        "ln_methodology": "Méthodologie",
        "ln_editorial_standards": "Normes éditoriales",
    },
    "es": {
        "title": "Política de fuentes",
        "lead": "Cómo TourVsTravel selecciona, evalúa y cita la información utilizada en las comparaciones de experiencias de viaje.",
        "standards_label": "Estándares de obtención de fuentes",
        "standards_body": "Todas las afirmaciones factuales utilizadas en las comparaciones provienen de fuentes primarias: datos oficiales de autoridades turísticas, investigaciones académicas revisadas por pares y especificaciones de operadores documentadas públicamente. No aceptamos colocaciones patrocinadas ni acuerdos de afiliados que influyan en el contenido.",
        "types_label": "Tipos de fuentes",
        "types_body": "Las categorías de fuentes aceptadas incluyen estadísticas de turismo gubernamentales, estudios académicos publicados sobre comportamiento de viajeros, especificaciones de operadores certificados y relatos de viajeros verificados de forma independiente. Se excluyen las fuentes anecdotóticas inverificables.",
        "see_also_label": "Véase también",
        "ln_methodology": "Metodología",
        "ln_editorial_standards": "Estándares editoriales",
    },
    "de": {
        "title": "Quellenrichtlinie",
        "lead": "Wie TourVsTravel Informationen für Reiseerfahrungsvergleiche auswählt, bewertet und zitiert.",
        "standards_label": "Beschaffungsstandards",
        "standards_body": "Alle in Vergleichen verwendeten Tatsachenbehauptungen stammen aus Primärquellen: offizielle Daten der Tourismusbehörden, von Experten begutachtete akademische Forschung und öffentlich dokumentierte Betreiberspezifikationen. Wir akzeptieren keine gesponserten Platzierungen oder Affiliate-Vereinbarungen, die Inhalte beeinflussen.",
        "types_label": "Quellentypen",
        "types_body": "Akzeptierte Quellkategorien umfassen staatliche Tourismusstatistiken, veröffentlichte akademische Studien zum Reiseverhalten, zertifizierte Betreiberspezifikationen und unabhängig verifizierte Reisendenerfahrungen. Unbeprüfbare anekdotische Quellen werden ausgeschlossen.",
        "see_also_label": "Siehe auch",
        "ln_methodology": "Methodik",
        "ln_editorial_standards": "Redaktionelle Standards",
    },
    "zh": {
        "title": "信息来源政策",
        "lead": "TourVsTravel 如何筛选、评估和引用旅行体验比较中使用的信息。",
        "standards_label": "来源标准",
        "standards_body": "比较中使用的所有事实性声明均来自主要来源：官方旅游局数据、经同行评审的学术研究以及公开记录的运营商规格。我们不接受影响内容的赞助植入或联盟安排。",
        "types_label": "来源类型",
        "types_body": "可接受的来源类别包括：政府旅游统计数据、已发表的旅行行为学术研究、经认证的运营商规格，以及经独立核实的旅行者记录。不可核实的轶事性来源将被排除在外。",
        "see_also_label": "另见",
        "ln_methodology": "方法论",
        "ln_editorial_standards": "编辑标准",
    },
    "ja": {
        "title": "情報源ポリシー",
        "lead": "TourVsTravel が旅行体験比較に使用する情報をどのように選択・評価・引用するかについて。",
        "standards_label": "情報源の基準",
        "standards_body": "比較に使用されるすべての事実的な主張は、一次情報源に基づいています：公式観光局データ、査読済み学術研究、および公開されたオペレーター仕様。コンテンツに影響を与えるスポンサードプレースメントやアフィリエイト契約は受け付けておりません。",
        "types_label": "情報源の種類",
        "types_body": "受け入れられる情報源のカテゴリには、政府の観光統計、旅行行動に関する学術論文、認定オペレーターの仕様書、および独立して検証された旅行者の記録が含まれます。検証不可能な逸話的情報源は除外されます。",
        "see_also_label": "関連情報",
        "ln_methodology": "方法論",
        "ln_editorial_standards": "編集基準",
    },
}


class GenerateSourcePolicyError(Exception):
    pass


def _ensure_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise GenerateSourcePolicyError(f"{label} must be a mapping/object.")
    return value


def _ensure_string(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise GenerateSourcePolicyError(f"{label} must be a string.")
    text = value.strip()
    if not text:
        raise GenerateSourcePolicyError(f"{label} must not be empty.")
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
        raise GenerateSourcePolicyError(f"{label} must start with /static/: {path}")
    asset_path = (ROOT_DIR / path.lstrip("/")).resolve()
    try:
        asset_path.relative_to(STATIC_DIR.resolve())
    except ValueError as exc:
        raise GenerateSourcePolicyError(f"{label} escapes static directory: {path}") from exc
    if not asset_path.is_file():
        raise GenerateSourcePolicyError(f"Missing static asset for {label}: {path}")
    return path


def _resolve_logo_path(site_config: Mapping[str, Any]) -> str:
    logo = _get_nested(site_config, ("branding", "logo_path"), "/static/img/brand/logo-icon.webp")
    return _ensure_string(logo, "branding.logo_path")


def _resolve_manifest_url() -> str:
    candidate = ROOT_DIR / "static" / "site.webmanifest"
    return "/static/site.webmanifest" if candidate.is_file() else ""


def _create_jinja_env() -> Environment:
    if not TEMPLATES_DIR.exists():
        raise GenerateSourcePolicyError(f"Missing templates directory: {TEMPLATES_DIR}")
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
        raise GenerateSourcePolicyError(f"Unable to write {path}: {exc}") from exc


def _ensure_safe_output_dir(output_dir: Path) -> Path:
    resolved = output_dir.resolve()
    if str(resolved) == resolved.anchor:
        raise GenerateSourcePolicyError(f"Refusing filesystem root as output directory: {resolved}")
    if resolved.exists() and resolved.is_symlink():
        raise GenerateSourcePolicyError(f"Refusing symlink output directory: {resolved}")
    return resolved


def _build_urls_by_lang(site_config: Mapping[str, Any], languages: Sequence[str]) -> Dict[str, str]:
    urls: Dict[str, str] = {}
    site = _ensure_mapping(site_config.get("site"), "site_config.site")
    raw_base = site.get("base_url", "https://tourvstravel.com")
    base = _ensure_string(raw_base, "site.base_url").rstrip("/")
    for code in languages:
        rel = build_source_policy_path(site_config, code, absolute=False)
        urls[code] = f"{base}{rel}" if rel.startswith("/") else f"{base}/{rel}"
    return urls


def _build_context(
    *,
    site_config: Mapping[str, Any],
    lang: str,
    languages: Sequence[str],
) -> Dict[str, Any]:
    copy = get_trust_page_copy("source_policy", lang)
    base_url = _ensure_string(
        _get_nested(site_config, ("site", "base_url"), "https://tourvstravel.com").strip().rstrip("/"),
        "site.base_url",
    )
    site_name = _extract_site_name(site_config, lang)
    logo_url = _resolve_logo_path(site_config)
    canonical_url = build_source_policy_path(site_config, lang, absolute=True)
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
    return {
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
        "body_class": "page-source-policy",
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
            "url_methodology": build_methodology_path(site_config, lang, absolute=False),
            "url_editorial_standards": build_editorial_standards_path(site_config, lang, absolute=False),
            "url_about": build_about_path(site_config, lang, absolute=False),
            "url_contact": build_contact_path(site_config, lang, absolute=False),
        },
    }


def render_source_policy_page(
    *,
    site_config: Mapping[str, Any],
    lang: str,
    languages: Sequence[str],
) -> str:
    env = _create_jinja_env()
    try:
        template = env.get_template(TEMPLATE_NAME)
    except TemplateError as exc:
        raise GenerateSourcePolicyError(f"Unable to load template {TEMPLATE_NAME}: {exc}") from exc
    context = _build_context(site_config=site_config, lang=lang, languages=languages)
    try:
        html_out = template.render(**context)
    except TemplateError as exc:
        raise GenerateSourcePolicyError(f"Unable to render source policy page [{lang}]: {exc}") from exc
    if not html_out.strip():
        raise GenerateSourcePolicyError(f"Rendered source policy page is empty for language {lang!r}.")
    return html_out


def generate_source_policy_pages(
    *,
    requested_lang: Optional[str] = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> List[Path]:
    safe_output_dir = _ensure_safe_output_dir(output_dir)
    site_config = load_site_config()
    if not isinstance(site_config, Mapping):
        raise GenerateSourcePolicyError("load_site_config() must return a mapping/object.")
    if requested_lang is not None:
        lang = requested_lang.strip()
        if lang not in SUPPORTED_LANGUAGES:
            raise GenerateSourcePolicyError(f"Unsupported language requested: {requested_lang!r}")
        languages = [lang]
    else:
        languages = _extract_enabled_languages(site_config)
    if not languages:
        raise GenerateSourcePolicyError("No enabled languages available for source policy generation.")
    written: List[Path] = []
    for lang in languages:
        html_output = render_source_policy_page(site_config=site_config, lang=lang, languages=languages)
        output_path = safe_output_dir / lang / "methodology" / "source-policy" / "index.html"
        _atomic_write_text(output_path, html_output)
        written.append(output_path)
        log.info("Generated source policy page [%s] -> %s", lang, output_path)
    return written


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate TourVsTravel source policy pages.")
    parser.add_argument("--lang", type=str, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    args = parse_args(argv)
    try:
        generate_source_policy_pages(requested_lang=args.lang, output_dir=args.output_dir)
    except GenerateSourcePolicyError as exc:
        log.error(str(exc))
        return 1
    except Exception as exc:
        log.exception("Unexpected source policy generation failure: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
