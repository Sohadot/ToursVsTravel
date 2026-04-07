#!/usr/bin/env python3
"""
TourVsTravel — Home Page Generator
=================================

Purpose
-------
Generate the multilingual home page into:
    output/{lang}/index.html

This generator is intentionally strict:
- fails early on missing config, templates, or static assets
- does not handcraft SEO in templates
- does not concatenate asset URLs inside Jinja
- does not emit partial or broken output silently
- does not mutate sys.path
- requires module execution from repository root:
      python -m scripts.generate_home

Architectural role
------------------
This is the first real generator in the system.
It binds together:
- scripts/i18n.py
- scripts/routes.py
- scripts/seo.py
- templates/pages/home.html
- templates/layouts/base.html + partials

Output contract
---------------
For each enabled language:
- build home route
- build canonical + hreflang map
- build SEO payload
- build template context
- render pages/home.html
- write output/{lang}/index.html atomically

Notes
-----
- Static assets are validated physically before rendering so the homepage
  cannot ship with broken core references.
- The generator renders ALL target languages first, and only then writes output.
  This prevents partial output caused by render-time failures in later languages.
"""

from __future__ import annotations

import argparse
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, List, Mapping, Optional, Sequence

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from scripts.i18n import (
    build_language_registry,
    get_enabled_languages,
    get_language_config,
    translate_string,
)
from scripts.routes import (
    build_acquire_path,
    build_compare_index_path,
    build_destinations_index_path,
    build_home_path,
    build_methodology_path,
    build_static_language_url_map,
    build_tools_index_path,
)
from scripts.seo import (
    build_organization_jsonld,
    build_page_seo,
    build_webpage_jsonld,
    build_website_jsonld,
)


# ============================================================================
# Logging
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("generate_home")


# ============================================================================
# Paths
# ============================================================================

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
TEMPLATES_DIR = ROOT_DIR / "templates"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "output"


# ============================================================================
# Exceptions
# ============================================================================

class GenerateHomeError(Exception):
    """Base generator error."""


class ConfigError(GenerateHomeError):
    """Raised when site configuration is missing or invalid."""


class AssetError(GenerateHomeError):
    """Raised when required static assets are missing or invalid."""


class RenderError(GenerateHomeError):
    """Raised when template rendering fails."""


# ============================================================================
# Data model
# ============================================================================

@dataclass(frozen=True)
class PreloadAsset:
    """Validated preload asset descriptor passed to templates."""
    href: str
    as_value: str
    type_value: Optional[str] = None
    crossorigin: Optional[str] = None

    def as_template_dict(self) -> Dict[str, str]:
        payload: Dict[str, str] = {
            "href": self.href,
            "as": self.as_value,
        }
        if self.type_value:
            payload["type"] = self.type_value
        if self.crossorigin:
            payload["crossorigin"] = self.crossorigin
        return payload


# ============================================================================
# UI fallbacks (localized, minimal, non-promotional)
# ============================================================================

DEFAULT_UI_TEXT: Dict[str, Dict[str, str]] = {
    "en": {
        "skip_to_content": "Skip to content",
        "nav_home": "Home",
        "nav_compare": "Compare",
        "nav_destinations": "Destinations",
        "nav_tools": "Tools",
        "nav_methodology": "Methodology",
        "nav_acquire": "Acquire",
        "footer_about": "About",
        "footer_contact": "Contact",
        "footer_privacy": "Privacy",
        "footer_terms": "Terms",
        "footer_acquire": "Acquire Domain",
    },
    "ar": {
        "skip_to_content": "انتقل إلى المحتوى",
        "nav_home": "الرئيسية",
        "nav_compare": "قارن",
        "nav_destinations": "الوجهات",
        "nav_tools": "الأدوات",
        "nav_methodology": "المنهجية",
        "nav_acquire": "الاستحواذ",
        "footer_about": "حول",
        "footer_contact": "اتصل",
        "footer_privacy": "الخصوصية",
        "footer_terms": "الشروط",
        "footer_acquire": "امتلاك النطاق",
    },
    "fr": {
        "skip_to_content": "Aller au contenu",
        "nav_home": "Accueil",
        "nav_compare": "Comparer",
        "nav_destinations": "Destinations",
        "nav_tools": "Outils",
        "nav_methodology": "Méthodologie",
        "nav_acquire": "Acquérir",
        "footer_about": "À propos",
        "footer_contact": "Contact",
        "footer_privacy": "Confidentialité",
        "footer_terms": "Conditions",
        "footer_acquire": "Acquérir le domaine",
    },
    "es": {
        "skip_to_content": "Ir al contenido",
        "nav_home": "Inicio",
        "nav_compare": "Comparar",
        "nav_destinations": "Destinos",
        "nav_tools": "Herramientas",
        "nav_methodology": "Metodología",
        "nav_acquire": "Adquirir",
        "footer_about": "Acerca de",
        "footer_contact": "Contacto",
        "footer_privacy": "Privacidad",
        "footer_terms": "Términos",
        "footer_acquire": "Adquirir dominio",
    },
    "de": {
        "skip_to_content": "Zum Inhalt springen",
        "nav_home": "Start",
        "nav_compare": "Vergleichen",
        "nav_destinations": "Reiseziele",
        "nav_tools": "Werkzeuge",
        "nav_methodology": "Methodik",
        "nav_acquire": "Erwerben",
        "footer_about": "Über uns",
        "footer_contact": "Kontakt",
        "footer_privacy": "Datenschutz",
        "footer_terms": "Bedingungen",
        "footer_acquire": "Domain erwerben",
    },
    "zh": {
        "skip_to_content": "跳转到内容",
        "nav_home": "首页",
        "nav_compare": "比较",
        "nav_destinations": "目的地",
        "nav_tools": "工具",
        "nav_methodology": "方法论",
        "nav_acquire": "获取",
        "footer_about": "关于",
        "footer_contact": "联系",
        "footer_privacy": "隐私",
        "footer_terms": "条款",
        "footer_acquire": "获取域名",
    },
    "ja": {
        "skip_to_content": "コンテンツへ移動",
        "nav_home": "ホーム",
        "nav_compare": "比較",
        "nav_destinations": "目的地",
        "nav_tools": "ツール",
        "nav_methodology": "方法論",
        "nav_acquire": "取得",
        "footer_about": "概要",
        "footer_contact": "連絡先",
        "footer_privacy": "プライバシー",
        "footer_terms": "利用規約",
        "footer_acquire": "ドメイン取得",
    },
}


# ============================================================================
# YAML loading
# ============================================================================

def _load_yaml_file(path: Path) -> Any:
    if not path.exists():
        raise ConfigError(f"Missing required YAML file: {path}")
    if not path.is_file():
        raise ConfigError(f"YAML path is not a file: {path}")

    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {path}: {exc}") from exc

    if data is None:
        raise ConfigError(f"YAML file is empty: {path}")

    return data


def load_site_config() -> Mapping[str, Any]:
    """Load site_config.yaml strictly."""
    path = DATA_DIR / "site_config.yaml"
    config = _load_yaml_file(path)

    if not isinstance(config, Mapping):
        raise ConfigError("data/site_config.yaml must contain a top-level mapping/object.")
    if "site" not in config:
        raise ConfigError("site_config.yaml must contain top-level key 'site'.")
    if "languages" not in config:
        raise ConfigError("site_config.yaml must contain top-level key 'languages'.")
    if "seo" not in config:
        raise ConfigError("site_config.yaml must contain top-level key 'seo'.")

    return config


# ============================================================================
# General helpers
# ============================================================================

def _ensure_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise GenerateHomeError(f"{label} must be a mapping/object.")
    return value


def _ensure_string(value: Any, label: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise GenerateHomeError(f"{label} must be a string.")
    text = value.strip()
    if not allow_empty and not text:
        raise GenerateHomeError(f"{label} must not be empty.")
    return text


def _get_nested(mapping: Mapping[str, Any], path: Sequence[str], default: Any = None) -> Any:
    current: Any = mapping
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return default
        current = current[key]
    return current


def _translate_node(
    site_config: Mapping[str, Any],
    registry: Mapping[str, Any],
    lang: str,
    node: Any,
    field_name: str,
    default: str = "",
) -> str:
    if node is None:
        return default
    if isinstance(node, str):
        return node.strip()
    if isinstance(node, Mapping):
        return translate_string(
            node,
            lang,
            site_config=site_config,
            field_name=field_name,
            registry=registry,
        )
    raise GenerateHomeError(f"{field_name} must be either a string or multilingual mapping.")


def _resolve_multilingual_text(
    site_config: Mapping[str, Any],
    registry: Mapping[str, Any],
    lang: str,
    candidate_paths: Sequence[Sequence[str]],
    *,
    default: str = "",
    label: str,
) -> str:
    for path in candidate_paths:
        node = _get_nested(site_config, path, default=None)
        if node is not None:
            return _translate_node(site_config, registry, lang, node, ".".join(path), default=default)
    return default


def _validate_root_relative_url(value: str, label: str) -> str:
    """
    Allow only strict root-relative URLs for template asset fields in this phase.

    Allowed examples:
        /static/css/main.css
        /static/js/main.js
        /site.webmanifest

    Rejected:
        http://...
        https://...
        //cdn...
        static/css/main.css
        /../x
        /static//x
        /static\\x
    """
    text = _ensure_string(value, label)

    if not text.startswith("/"):
        raise AssetError(f"{label} must be root-relative. Got: {text!r}")
    if text.startswith("//"):
        raise AssetError(f"{label} must not be protocol-relative. Got: {text!r}")
    if "://" in text:
        raise AssetError(f"{label} must not be absolute in this phase. Got: {text!r}")
    if ".." in text:
        raise AssetError(f"{label} must not contain path traversal. Got: {text!r}")
    if "\\" in text:
        raise AssetError(f"{label} must not contain backslashes. Got: {text!r}")
    if "//" in text[1:]:
        raise AssetError(f"{label} must not contain duplicate slashes. Got: {text!r}")
    if any(ch.isspace() for ch in text):
        raise AssetError(f"{label} must not contain whitespace. Got: {text!r}")

    return text


def _physical_path_from_root_relative(root_relative_url: str) -> Path:
    validated = _validate_root_relative_url(root_relative_url, "asset url")
    return ROOT_DIR / validated.lstrip("/")


def _require_existing_asset(root_relative_url: str, label: str) -> str:
    validated = _validate_root_relative_url(root_relative_url, label)
    physical = _physical_path_from_root_relative(validated)

    if not physical.exists():
        raise AssetError(f"{label} points to a missing file: {validated} -> {physical}")
    if not physical.is_file():
        raise AssetError(f"{label} is not a file: {validated} -> {physical}")

    return validated


def _infer_mime_type_from_path(root_relative_url: str) -> str:
    suffix = Path(root_relative_url).suffix.lower()

    mime_map = {
        ".css": "text/css",
        ".js": "text/javascript",
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".ico": "image/x-icon",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }

    if suffix not in mime_map:
        raise AssetError(f"Unsupported asset extension for MIME inference: {root_relative_url}")

    return mime_map[suffix]


def _validate_csp_meta_policy(value: str) -> str:
    text = _ensure_string(value, "csp_meta_policy")
    forbidden = ['"', "<", ">", "\n", "\r", "\x00"]
    if any(token in text for token in forbidden):
        raise ConfigError("csp_meta_policy contains forbidden characters.")
    return text


def _build_jinja_env() -> Environment:
    if not TEMPLATES_DIR.exists():
        raise RenderError(f"Templates directory is missing: {TEMPLATES_DIR}")

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
            "w",
            encoding="utf-8",
            dir=str(path.parent),
            delete=False,
            suffix=".tmp",
        ) as tmp:
            tmp.write(content)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_path = Path(tmp.name)

        if tmp_path is None:
            raise GenerateHomeError(f"Failed to create temporary file for {path}")

        tmp_path.replace(path)

    except Exception:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise


# ============================================================================
# Context resolution
# ============================================================================

def _resolve_site_name(
    site_config: Mapping[str, Any],
    registry: Mapping[str, Any],
    lang: str,
) -> str:
    node = _get_nested(site_config, ("site", "name"))
    if node is None:
        raise ConfigError("site_config.site.name is missing.")
    return _translate_node(site_config, registry, lang, node, "site_config.site.name")


def _resolve_site_tagline(
    site_config: Mapping[str, Any],
    registry: Mapping[str, Any],
    lang: str,
) -> str:
    node = _get_nested(site_config, ("site", "tagline"))
    if node is None:
        return ""
    return _translate_node(site_config, registry, lang, node, "site_config.site.tagline", default="")


def _resolve_site_summary(
    site_config: Mapping[str, Any],
    registry: Mapping[str, Any],
    lang: str,
) -> str:
    return _resolve_multilingual_text(
        site_config,
        registry,
        lang,
        candidate_paths=[
            ("site", "summary"),
            ("seo", "default_description"),
        ],
        default="",
        label="site_summary",
    )


def _resolve_ui_label(
    site_config: Mapping[str, Any],
    registry: Mapping[str, Any],
    lang: str,
    key: str,
    default_key: str,
) -> str:
    resolved = _resolve_multilingual_text(
        site_config,
        registry,
        lang,
        candidate_paths=[
            ("ui", "labels", key),
            ("ui", key),
        ],
        default="",
        label=f"ui.{key}",
    )
    if resolved:
        return resolved

    fallback_lang = DEFAULT_UI_TEXT.get(lang) or DEFAULT_UI_TEXT["en"]
    return fallback_lang[default_key]


def _resolve_nav_label(
    site_config: Mapping[str, Any],
    registry: Mapping[str, Any],
    lang: str,
    key: str,
    fallback_key: str,
) -> str:
    resolved = _resolve_multilingual_text(
        site_config,
        registry,
        lang,
        candidate_paths=[
            ("ui", "nav", key),
            ("nav", key),
        ],
        default="",
        label=f"nav.{key}",
    )
    if resolved:
        return resolved

    fallback_lang = DEFAULT_UI_TEXT.get(lang) or DEFAULT_UI_TEXT["en"]
    return fallback_lang[fallback_key]


def _resolve_footer_label(
    site_config: Mapping[str, Any],
    registry: Mapping[str, Any],
    lang: str,
    key: str,
    fallback_key: str,
) -> str:
    resolved = _resolve_multilingual_text(
        site_config,
        registry,
        lang,
        candidate_paths=[
            ("ui", "footer", key),
            ("footer", key),
        ],
        default="",
        label=f"footer.{key}",
    )
    if resolved:
        return resolved

    fallback_lang = DEFAULT_UI_TEXT.get(lang) or DEFAULT_UI_TEXT["en"]
    return fallback_lang[fallback_key]


def _resolve_theme_color(site_config: Mapping[str, Any]) -> str:
    for path in [
        ("brand", "theme_color"),
        ("brand", "colors", "theme"),
        ("seo", "theme_color"),
        ("site", "theme_color"),
    ]:
        value = _get_nested(site_config, path)
        if value is not None:
            return _ensure_string(value, ".".join(path))
    return "#0f172a"


def _resolve_referrer_policy(site_config: Mapping[str, Any]) -> str:
    for path in [
        ("seo", "referrer_policy"),
        ("security", "referrer_policy"),
    ]:
        value = _get_nested(site_config, path)
        if value is not None:
            return _ensure_string(value, ".".join(path))
    return "strict-origin-when-cross-origin"


def _resolve_csp_meta_policy(site_config: Mapping[str, Any]) -> Optional[str]:
    for path in [
        ("security", "csp_meta_policy"),
        ("seo", "csp_meta_policy"),
    ]:
        value = _get_nested(site_config, path)
        if value is not None:
            return _validate_csp_meta_policy(value)
    return None


def _resolve_manifest_url(site_config: Mapping[str, Any]) -> Optional[str]:
    for path in [
        ("site", "manifest_url"),
        ("seo", "manifest_url"),
    ]:
        value = _get_nested(site_config, path)
        if value is not None:
            return _require_existing_asset(_ensure_string(value, ".".join(path)), ".".join(path))

    default_manifest = "/site.webmanifest"
    physical = ROOT_DIR / default_manifest.lstrip("/")
    if physical.exists() and physical.is_file():
        return default_manifest

    return None


def _resolve_brand_asset_urls(site_config: Mapping[str, Any]) -> Dict[str, Optional[str]]:
    brand_logo = _get_nested(site_config, ("brand", "logo"), default={})
    brand_logo = _ensure_mapping(brand_logo, "site_config.brand.logo") if brand_logo else {}

    icon_path = brand_logo.get("icon_path", "/static/img/brand/logo-icon.jpg")
    icon_url = _require_existing_asset(
        _ensure_string(icon_path, "site_config.brand.logo.icon_path"),
        "brand.logo.icon_path",
    )

    lockup_url: Optional[str] = None
    wordmark_url: Optional[str] = None

    if "lockup_path" in brand_logo:
        lockup_url = _require_existing_asset(
            _ensure_string(brand_logo["lockup_path"], "site_config.brand.logo.lockup_path"),
            "brand.logo.lockup_path",
        )

    if "wordmark_path" in brand_logo:
        wordmark_url = _require_existing_asset(
            _ensure_string(brand_logo["wordmark_path"], "site_config.brand.logo.wordmark_path"),
            "brand.logo.wordmark_path",
        )

    return {
        "icon_url": icon_url,
        "lockup_url": lockup_url,
        "wordmark_url": wordmark_url,
    }


def _resolve_core_asset_urls(site_config: Mapping[str, Any]) -> Dict[str, Any]:
    main_css_url = _require_existing_asset("/static/css/main.css", "main_css_url")
    main_js_url = _require_existing_asset("/static/js/main.js", "main_js_url")

    brand_assets = _resolve_brand_asset_urls(site_config)
    favicon_url = brand_assets["icon_url"]
    favicon_type = _infer_mime_type_from_path(favicon_url)

    manifest_url = _resolve_manifest_url(site_config)

    preload_assets = [
        PreloadAsset(
            href=main_css_url,
            as_value="style",
            type_value="text/css",
        ).as_template_dict()
    ]

    return {
        "main_css_url": main_css_url,
        "main_js_url": main_js_url,
        "favicon_url": favicon_url,
        "favicon_type": favicon_type,
        "apple_touch_icon_url": favicon_url,
        "manifest_url": manifest_url,
        "preload_assets": preload_assets,
        "brand_logo_icon_url": brand_assets["icon_url"],
        "brand_logo_lockup_url": brand_assets["lockup_url"],
        "brand_logo_wordmark_url": brand_assets["wordmark_url"],
    }


def _resolve_home_title(
    site_config: Mapping[str, Any],
    registry: Mapping[str, Any],
    lang: str,
    site_name: str,
    site_tagline: str,
) -> str:
    title = _resolve_multilingual_text(
        site_config,
        registry,
        lang,
        candidate_paths=[
            ("seo", "home_title"),
            ("seo", "pages", "home", "title"),
            ("seo", "home", "title"),
        ],
        default="",
        label="home_title",
    )
    if title:
        return title

    if site_tagline:
        return f"{site_name} | {site_tagline}"
    return site_name


def _resolve_home_description(
    site_config: Mapping[str, Any],
    registry: Mapping[str, Any],
    lang: str,
    site_name: str,
    site_tagline: str,
) -> str:
    description = _resolve_multilingual_text(
        site_config,
        registry,
        lang,
        candidate_paths=[
            ("seo", "home_description"),
            ("seo", "pages", "home", "description"),
            ("seo", "home", "description"),
            ("site", "summary"),
            ("seo", "default_description"),
        ],
        default="",
        label="home_description",
    )
    if description:
        return description

    if site_tagline:
        return site_tagline

    raise ConfigError(
        f"No multilingual home description could be resolved for language {lang!r}. "
        "Define one of: seo.home_description, seo.pages.home.description, site.summary, or seo.default_description."
    )


def _build_language_switcher(
    site_config: Mapping[str, Any],
    registry: Mapping[str, Any],
    lang: str,
    url_map: Mapping[str, str],
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []

    for language in get_enabled_languages(site_config, registry=registry):
        item = _ensure_mapping(language, "site_config.languages[]")
        code = _ensure_string(item.get("code"), "site_config.languages[].code")
        url = url_map.get(code)
        if url is None:
            raise GenerateHomeError(f"Missing URL in language URL map for language: {code!r}")

        label_value = item.get("label") or item.get("name") or code.upper()

        items.append(
            {
                "code": code,
                "label": _ensure_string(label_value, f"language[{code}].label"),
                "url": _ensure_string(url, f"language_switcher.url[{code}]"),
                "dir": _ensure_string(item.get("dir", "ltr"), f"language[{code}].dir"),
                "is_current": code == lang,
            }
        )

    return items


def _build_home_seo(
    site_config: Mapping[str, Any],
    registry: Mapping[str, Any],
    lang: str,
    title: str,
    description: str,
    logo_url: str,
) -> Dict[str, Any]:
    canonical_url = build_home_path(site_config, lang, absolute=True, registry=registry)
    urls_by_lang = build_static_language_url_map(site_config, "home", registry=registry)

    organization_jsonld = build_organization_jsonld(
        site_config,
        logo_url=logo_url,
    )
    website_jsonld = build_website_jsonld(
        site_config,
        lang,
        home_url=canonical_url,
    )
    webpage_jsonld = build_webpage_jsonld(
        name=title,
        description=description,
        url=canonical_url,
        lang=lang,
        is_part_of_url=canonical_url,
    )

    seo_payload = build_page_seo(
        site_config,
        lang,
        page_title=title,
        page_description=description,
        canonical_url=canonical_url,
        urls_by_lang=urls_by_lang,
        page_type="website",
        jsonld_payloads=[
            organization_jsonld,
            website_jsonld,
            webpage_jsonld,
        ],
    )

    lang_conf = _ensure_mapping(
        get_language_config(site_config, lang, registry=registry),
        f"language_config[{lang}]",
    )
    locale = lang_conf.get("locale")
    if isinstance(locale, str) and locale.strip():
        seo_payload["og_locale"] = locale.strip()

    alternate_locales: List[str] = []
    for item in get_enabled_languages(site_config, registry=registry):
        mapping = _ensure_mapping(item, "site_config.languages[]")
        code = _ensure_string(mapping.get("code"), "site_config.languages[].code")
        if code == lang:
            continue
        candidate = mapping.get("locale")
        if isinstance(candidate, str) and candidate.strip():
            alternate_locales.append(candidate.strip())

    if alternate_locales:
        seo_payload["og_locale_alternates"] = alternate_locales

    return seo_payload


def build_home_context(
    site_config: Mapping[str, Any],
    registry: Mapping[str, Any],
    lang: str,
) -> Dict[str, Any]:
    lang_conf = _ensure_mapping(
        get_language_config(site_config, lang, registry=registry),
        f"language_config[{lang}]",
    )

    site_name = _resolve_site_name(site_config, registry, lang)
    site_tagline = _resolve_site_tagline(site_config, registry, lang)
    assets = _resolve_core_asset_urls(site_config)

    title = _resolve_home_title(site_config, registry, lang, site_name, site_tagline)
    description = _resolve_home_description(site_config, registry, lang, site_name, site_tagline)
    seo_payload = _build_home_seo(
        site_config,
        registry,
        lang,
        title,
        description,
        assets["favicon_url"],
    )

    home_urls_by_lang = build_static_language_url_map(site_config, "home", registry=registry)

    context: Dict[str, Any] = {
        # Core runtime
        "lang": lang,
        "is_rtl": _ensure_string(lang_conf.get("dir", "ltr"), f"language[{lang}].dir") == "rtl",
        "seo": seo_payload,
        "body_class": "page-home",
        "current_year": datetime.now(timezone.utc).year,

        # Brand / site
        "site_name": site_name,
        "site_tagline": site_tagline,
        "site_summary": _resolve_site_summary(site_config, registry, lang),
        "theme_color": _resolve_theme_color(site_config),
        "referrer_policy": _resolve_referrer_policy(site_config),
        "csp_meta_policy": _resolve_csp_meta_policy(site_config),

        # Assets
        "main_css_url": assets["main_css_url"],
        "main_js_url": assets["main_js_url"],
        "favicon_url": assets["favicon_url"],
        "favicon_type": assets["favicon_type"],
        "apple_touch_icon_url": assets["apple_touch_icon_url"],
        "manifest_url": assets["manifest_url"],
        "preload_assets": assets["preload_assets"],
        "page_css_assets": [],
        "page_js_assets": [],
        "brand_logo_icon_url": assets["brand_logo_icon_url"],
        "brand_logo_lockup_url": assets["brand_logo_lockup_url"],
        "brand_logo_wordmark_url": assets["brand_logo_wordmark_url"],

        # Navigation state
        "active_nav": "home",
        "home_url": build_home_path(site_config, lang, absolute=False, registry=registry),
        "compare_url": build_compare_index_path(site_config, lang, absolute=False, registry=registry),
        "destinations_url": build_destinations_index_path(site_config, lang, absolute=False, registry=registry),
        "tools_url": build_tools_index_path(site_config, lang, absolute=False, registry=registry),
        "methodology_url": build_methodology_path(site_config, lang, absolute=False, registry=registry),
        "acquire_url": build_acquire_path(site_config, lang, absolute=False, registry=registry),

        # Nav labels
        "nav_home": _resolve_nav_label(site_config, registry, lang, "home", "nav_home"),
        "nav_compare": _resolve_nav_label(site_config, registry, lang, "compare", "nav_compare"),
        "nav_destinations": _resolve_nav_label(site_config, registry, lang, "destinations", "nav_destinations"),
        "nav_tools": _resolve_nav_label(site_config, registry, lang, "tools", "nav_tools"),
        "nav_methodology": _resolve_nav_label(site_config, registry, lang, "methodology", "nav_methodology"),
        "nav_acquire": _resolve_nav_label(site_config, registry, lang, "acquire", "nav_acquire"),

        # Footer labels
        "footer_about": _resolve_footer_label(site_config, registry, lang, "about", "footer_about"),
        "footer_contact": _resolve_footer_label(site_config, registry, lang, "contact", "footer_contact"),
        "footer_privacy": _resolve_footer_label(site_config, registry, lang, "privacy", "footer_privacy"),
        "footer_terms": _resolve_footer_label(site_config, registry, lang, "terms", "footer_terms"),
        "footer_acquire": _resolve_footer_label(site_config, registry, lang, "acquire", "footer_acquire"),

        # Accessibility / language switching
        "ui_skip_to_content_label": _resolve_ui_label(
            site_config, registry, lang, "skip_to_content", "skip_to_content"
        ),
        "home_urls_by_lang": home_urls_by_lang,
        "language_switcher": _build_language_switcher(site_config, registry, lang, home_urls_by_lang),

        # Helpful generic aliases for templates
        "page_lang_urls": home_urls_by_lang,
    }

    return context


# ============================================================================
# Rendering
# ============================================================================

def _load_home_template(env: Environment):
    try:
        return env.get_template("pages/home.html")
    except Exception as exc:
        raise RenderError(f"Unable to load template 'pages/home.html': {exc}") from exc


def render_home_html(
    site_config: Mapping[str, Any],
    registry: Mapping[str, Any],
    lang: str,
    *,
    env: Environment,
) -> str:
    template = _load_home_template(env)
    context = build_home_context(site_config, registry, lang)

    try:
        html = template.render(**context)
    except Exception as exc:
        raise RenderError(f"Failed to render home page for language {lang!r}: {exc}") from exc

    if not isinstance(html, str) or not html.strip():
        raise RenderError(f"Rendered home page is empty for language {lang!r}.")

    return html


# ============================================================================
# CLI / orchestration
# ============================================================================

def _resolve_target_languages(
    site_config: Mapping[str, Any],
    registry: Mapping[str, Any],
    requested_lang: Optional[str],
) -> List[str]:
    enabled_codes: List[str] = []

    for item in get_enabled_languages(site_config, registry=registry):
        mapping = _ensure_mapping(item, "site_config.languages[]")
        enabled_codes.append(_ensure_string(mapping.get("code"), "site_config.languages[].code"))

    if requested_lang:
        requested = _ensure_string(requested_lang, "--lang")
        if requested not in enabled_codes:
            raise GenerateHomeError(
                f"Requested language {requested!r} is not enabled. Enabled: {', '.join(enabled_codes)}"
            )
        return [requested]

    return enabled_codes


def generate_home_pages(
    *,
    requested_lang: Optional[str] = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> List[Path]:
    site_config = load_site_config()
    registry = build_language_registry(site_config)
    env = _build_jinja_env()

    target_languages = _resolve_target_languages(site_config, registry, requested_lang)

    rendered_by_lang: Dict[str, str] = {}
    for lang in target_languages:
        rendered_by_lang[lang] = render_home_html(
            site_config,
            registry,
            lang,
            env=env,
        )

    written_paths: List[Path] = []
    try:
        for lang, html in rendered_by_lang.items():
            output_path = output_dir / lang / "index.html"
            _atomic_write_text(output_path, html)
            written_paths.append(output_path)
            log.info("Generated home page [%s] -> %s", lang, output_path)
    except Exception as exc:
        raise GenerateHomeError(f"Failed while writing generated home page output: {exc}") from exc

    return written_paths


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the multilingual TourVsTravel home page."
    )
    parser.add_argument(
        "--lang",
        type=str,
        default=None,
        help="Generate only one enabled language code (e.g. en, ar, fr).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Output directory root. Default: ./output",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)

    try:
        written = generate_home_pages(
            requested_lang=args.lang,
            output_dir=args.output_dir.resolve(),
        )
    except GenerateHomeError as exc:
        log.error(str(exc))
        return 1
    except Exception as exc:
        log.exception("Unexpected generator failure: %s", exc)
        return 1

    log.info("Home generation completed successfully. Files written: %d", len(written))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
