#!/usr/bin/env python3
"""
TourVsTravel — Experience Type Page Generator
=============================================

Purpose
-------
Generate multilingual experience-type reference pages into:

    output/{lang}/styles/{slug}/index.html

Design principles
-----------------
- fail closed on missing config, template, or required assets
- deterministic output
- strict template context
- no partial writes
- multilingual-safe
- route-authoritative (paths come from scripts.routes)
- no direct raw reads of experience_types.yaml outside loaders.py
- official public API:
      generate_experience_type_pages(...)

Execution
---------
Run from repository root:

    python -m scripts.generate_experience_types
    python -m scripts.generate_experience_types --lang en
    python -m scripts.generate_experience_types --type-id guided_group_tour
"""

from __future__ import annotations

import argparse
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import urlparse

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from scripts.i18n import (
    build_language_registry,
    get_enabled_languages,
    get_language_config,
    translate_string,
)
from scripts.loaders import load_experience_types, load_yaml
from scripts.routes import (
    build_acquire_path,
    build_compare_index_path,
    build_destinations_index_path,
    build_experience_type_language_url_map,
    build_experience_type_path,
    build_home_path,
    build_methodology_path,
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

log = logging.getLogger("generate_experience_types")


def configure_logging() -> None:
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S",
        )


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

class GenerateExperienceTypesError(Exception):
    """Base experience-type generator error."""


class ConfigError(GenerateExperienceTypesError):
    """Raised when site configuration or data is missing/invalid."""


class AssetError(GenerateExperienceTypesError):
    """Raised when required static assets are missing or invalid."""


class RenderError(GenerateExperienceTypesError):
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
# UI fallbacks
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

AXIS_LABELS: Dict[str, Dict[str, str]] = {
    "structure_intensity": {
        "en": "Structure Intensity",
        "ar": "شدة البنية",
        "fr": "Intensité de structure",
        "es": "Intensidad estructural",
        "de": "Strukturintensität",
        "zh": "结构强度",
        "ja": "構造強度",
    },
    "autonomy_level": {
        "en": "Autonomy Level",
        "ar": "مستوى الاستقلالية",
        "fr": "Niveau d'autonomie",
        "es": "Nivel de autonomía",
        "de": "Autonomieniveau",
        "zh": "自主程度",
        "ja": "自律性レベル",
    },
    "support_level": {
        "en": "Support Level",
        "ar": "مستوى الدعم",
        "fr": "Niveau d'accompagnement",
        "es": "Nivel de apoyo",
        "de": "Unterstützungsniveau",
        "zh": "支持程度",
        "ja": "支援レベル",
    },
    "pace_profile": {
        "en": "Pace Profile",
        "ar": "ملف الوتيرة",
        "fr": "Profil de rythme",
        "es": "Perfil de ritmo",
        "de": "Tempoprofil",
        "zh": "节奏画像",
        "ja": "ペース特性",
    },
    "immersion_profile": {
        "en": "Immersion Profile",
        "ar": "ملف الانغماس",
        "fr": "Profil d'immersion",
        "es": "Perfil de inmersión",
        "de": "Immersionsprofil",
        "zh": "沉浸画像",
        "ja": "没入特性",
    },
    "predictability_profile": {
        "en": "Predictability Profile",
        "ar": "ملف قابلية التنبؤ",
        "fr": "Profil de prévisibilité",
        "es": "Perfil de previsibilidad",
        "de": "Vorhersehbarkeitsprofil",
        "zh": "可预测画像",
        "ja": "予測可能性特性",
    },
}

AXIS_VALUE_LABELS: Dict[str, Dict[str, Dict[str, str]]] = {
    "structure_intensity": {
        "low": {"en": "Low", "ar": "منخفض", "fr": "Faible", "es": "Baja", "de": "Niedrig", "zh": "低", "ja": "低い"},
        "medium": {"en": "Medium", "ar": "متوسط", "fr": "Moyen", "es": "Media", "de": "Mittel", "zh": "中", "ja": "中"},
        "high": {"en": "High", "ar": "عالٍ", "fr": "Élevé", "es": "Alta", "de": "Hoch", "zh": "高", "ja": "高い"},
    },
    "autonomy_level": {
        "low": {"en": "Low", "ar": "منخفض", "fr": "Faible", "es": "Bajo", "de": "Niedrig", "zh": "低", "ja": "低い"},
        "medium": {"en": "Medium", "ar": "متوسط", "fr": "Moyen", "es": "Medio", "de": "Mittel", "zh": "中", "ja": "中"},
        "high": {"en": "High", "ar": "عالٍ", "fr": "Élevé", "es": "Alto", "de": "Hoch", "zh": "高", "ja": "高い"},
    },
    "support_level": {
        "low": {"en": "Low", "ar": "منخفض", "fr": "Faible", "es": "Bajo", "de": "Niedrig", "zh": "低", "ja": "低い"},
        "medium": {"en": "Medium", "ar": "متوسط", "fr": "Moyen", "es": "Medio", "de": "Mittel", "zh": "中", "ja": "中"},
        "high": {"en": "High", "ar": "عالٍ", "fr": "Élevé", "es": "Alto", "de": "Hoch", "zh": "高", "ja": "高い"},
    },
    "pace_profile": {
        "fixed": {"en": "Fixed", "ar": "ثابت", "fr": "Fixe", "es": "Fijo", "de": "Fix", "zh": "固定", "ja": "固定"},
        "balanced": {"en": "Balanced", "ar": "متوازن", "fr": "Équilibré", "es": "Equilibrado", "de": "Ausgewogen", "zh": "均衡", "ja": "均衡"},
        "flexible": {"en": "Flexible", "ar": "مرن", "fr": "Flexible", "es": "Flexible", "de": "Flexibel", "zh": "灵活", "ja": "柔軟"},
    },
    "immersion_profile": {
        "surface": {"en": "Surface", "ar": "سطحي", "fr": "Surface", "es": "Superficial", "de": "Oberflächlich", "zh": "表层", "ja": "表層"},
        "balanced": {"en": "Balanced", "ar": "متوازن", "fr": "Équilibré", "es": "Equilibrado", "de": "Ausgewogen", "zh": "均衡", "ja": "均衡"},
        "deep": {"en": "Deep", "ar": "عميق", "fr": "Profond", "es": "Profundo", "de": "Tief", "zh": "深", "ja": "深い"},
    },
    "predictability_profile": {
        "low": {"en": "Low", "ar": "منخفض", "fr": "Faible", "es": "Baja", "de": "Niedrig", "zh": "低", "ja": "低い"},
        "medium": {"en": "Medium", "ar": "متوسط", "fr": "Moyen", "es": "Media", "de": "Mittel", "zh": "中", "ja": "中"},
        "high": {"en": "High", "ar": "عالٍ", "fr": "Élevé", "es": "Alta", "de": "Hoch", "zh": "高", "ja": "高い"},
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
# Helpers
# ============================================================================

def _ensure_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise GenerateExperienceTypesError(f"{label} must be a mapping/object.")
    return value


def _ensure_string(value: Any, label: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise GenerateExperienceTypesError(f"{label} must be a string.")
    text = value.strip()
    if not allow_empty and not text:
        raise GenerateExperienceTypesError(f"{label} must not be empty.")
    return text


def _ensure_list(value: Any, label: str) -> List[Any]:
    if not isinstance(value, list):
        raise GenerateExperienceTypesError(f"{label} must be a list.")
    return value


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
    raise GenerateExperienceTypesError(f"{field_name} must be either a string or multilingual mapping.")


def _resolve_multilingual_text(
    site_config: Mapping[str, Any],
    registry: Mapping[str, Any],
    lang: str,
    candidate_paths: Sequence[Sequence[str]],
    *,
    default: str = "",
) -> str:
    for path in candidate_paths:
        node = _get_nested(site_config, path, default=None)
        if node is not None:
            return _translate_node(site_config, registry, lang, node, ".".join(path), default=default)
    return default


def _validate_root_relative_url(value: str, label: str) -> str:
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


def _normalize_https_base_url(value: str) -> str:
    text = _ensure_string(value, "site_config.site.base_url")
    parsed = urlparse(text)

    if parsed.scheme != "https":
        raise ConfigError(f"site_config.site.base_url must use https scheme. Got: {text!r}")
    if not parsed.netloc:
        raise ConfigError(f"site_config.site.base_url must be an absolute HTTPS URL. Got: {text!r}")
    if parsed.username is not None or parsed.password is not None:
        raise ConfigError("site_config.site.base_url must not contain embedded credentials.")
    if parsed.query or parsed.fragment:
        raise ConfigError("site_config.site.base_url must not contain query parameters or fragments.")
    if (parsed.path or "") not in ("", "/"):
        raise ConfigError(f"site_config.site.base_url must not contain a path. Got: {text!r}")

    return f"https://{parsed.netloc.rstrip('/')}"


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
            raise GenerateExperienceTypesError(f"Failed to create temporary file for {path}")

        tmp_path.replace(path)

    except Exception:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise


def _route_path_to_output_file(output_dir: Path, route_path: str) -> Path:
    path = _validate_root_relative_url(route_path, "experience_type.route_path")
    stripped = path.strip("/")

    if not stripped:
        return output_dir / "index.html"

    parts = stripped.split("/")
    if path.endswith("/"):
        return output_dir.joinpath(*parts, "index.html")
    return output_dir.joinpath(*parts)


# ============================================================================
# Comparison criteria display layer
# ============================================================================

def _load_comparison_criteria_display_data() -> Dict[str, Any]:
    try:
        root = load_yaml("comparison_criteria.yaml")
    except Exception as exc:
        raise ConfigError(f"Failed to load comparison_criteria.yaml through loaders.py: {exc}") from exc

    root = _ensure_mapping(root, "comparison_criteria.yaml")
    criteria_raw = _ensure_list(root.get("criteria"), "comparison_criteria.yaml.criteria")
    bands_raw = _ensure_list(root.get("rating_bands"), "comparison_criteria.yaml.rating_bands")
    profiles_raw = _ensure_list(root.get("traveler_profiles"), "comparison_criteria.yaml.traveler_profiles")

    criteria_by_id: Dict[str, Dict[str, Any]] = {}
    for idx, item in enumerate(criteria_raw):
        crit = _ensure_mapping(item, f"comparison_criteria.criteria[{idx}]")
        crit_id = _ensure_string(crit.get("id"), f"comparison_criteria.criteria[{idx}].id")
        copy = _ensure_mapping(crit.get("copy"), f"comparison_criteria.criteria[{idx}].copy")
        criteria_by_id[crit_id] = {
            "id": crit_id,
            "ranking_direction": _ensure_string(
                crit.get("ranking_direction"),
                f"comparison_criteria.criteria[{idx}].ranking_direction",
            ),
            "copy": copy,
        }

    bands: List[Dict[str, Any]] = []
    for idx, item in enumerate(bands_raw):
        band = _ensure_mapping(item, f"comparison_criteria.rating_bands[{idx}]")
        label = _ensure_mapping(band.get("label"), f"comparison_criteria.rating_bands[{idx}].label")
        bands.append({
            "id": _ensure_string(band.get("id"), f"comparison_criteria.rating_bands[{idx}].id"),
            "min": float(band.get("min")),
            "max": float(band.get("max")),
            "label": label,
        })

    traveler_profiles: List[Dict[str, Any]] = []
    for idx, item in enumerate(profiles_raw):
        profile = _ensure_mapping(item, f"comparison_criteria.traveler_profiles[{idx}]")
        traveler_profiles.append({
            "id": _ensure_string(profile.get("id"), f"comparison_criteria.traveler_profiles[{idx}].id"),
            "label": _ensure_mapping(
                profile.get("label"),
                f"comparison_criteria.traveler_profiles[{idx}].label",
            ),
        })

    return {
        "criteria_by_id": criteria_by_id,
        "rating_bands": bands,
        "traveler_profiles": traveler_profiles,
    }


def _find_rating_band_label(score: int, lang: str, rating_bands: Sequence[Mapping[str, Any]]) -> str:
    numeric_score = float(score)
    for band in rating_bands:
        minimum = float(band["min"])
        maximum = float(band["max"])
        if minimum <= numeric_score <= maximum:
            label = _ensure_mapping(band.get("label"), "rating_band.label")
            return _ensure_string(label.get(lang) or label.get("en"), f"rating_band.label[{lang}]")
    raise GenerateExperienceTypesError(f"No rating band found for score {score!r}.")


# ============================================================================
# Context resolution
# ============================================================================

def _resolve_site_name(site_config: Mapping[str, Any], registry: Mapping[str, Any], lang: str) -> str:
    node = _get_nested(site_config, ("site", "name"))
    if node is None:
        raise ConfigError("site_config.site.name is missing.")
    return _translate_node(site_config, registry, lang, node, "site_config.site.name")


def _resolve_base_url(site_config: Mapping[str, Any]) -> str:
    site_section = _ensure_mapping(site_config.get("site"), "site_config.site")
    raw = site_section.get("base_url")
    if raw is None:
        raise ConfigError("site_config.site.base_url is missing.")
    return _normalize_https_base_url(_ensure_string(raw, "site_config.site.base_url"))


def _resolve_site_tagline(site_config: Mapping[str, Any], registry: Mapping[str, Any], lang: str) -> str:
    node = _get_nested(site_config, ("site", "tagline"))
    if node is None:
        return ""
    return _translate_node(site_config, registry, lang, node, "site_config.site.tagline", default="")


def _resolve_site_summary(site_config: Mapping[str, Any], registry: Mapping[str, Any], lang: str) -> str:
    return _resolve_multilingual_text(
        site_config,
        registry,
        lang,
        candidate_paths=[
            ("site", "summary"),
            ("seo", "default_description"),
        ],
        default="",
    )


def _resolve_ui_label(site_config: Mapping[str, Any], registry: Mapping[str, Any], lang: str, key: str, default_key: str) -> str:
    resolved = _resolve_multilingual_text(
        site_config,
        registry,
        lang,
        candidate_paths=[
            ("ui", "labels", key),
            ("ui", key),
        ],
        default="",
    )
    if resolved:
        return resolved

    fallback_lang = DEFAULT_UI_TEXT.get(lang) or DEFAULT_UI_TEXT["en"]
    return fallback_lang[default_key]


def _resolve_nav_label(site_config: Mapping[str, Any], registry: Mapping[str, Any], lang: str, key: str, fallback_key: str) -> str:
    resolved = _resolve_multilingual_text(
        site_config,
        registry,
        lang,
        candidate_paths=[
            ("ui", "nav", key),
            ("nav", key),
        ],
        default="",
    )
    if resolved:
        return resolved

    fallback_lang = DEFAULT_UI_TEXT.get(lang) or DEFAULT_UI_TEXT["en"]
    return fallback_lang[fallback_key]


def _resolve_footer_label(site_config: Mapping[str, Any], registry: Mapping[str, Any], lang: str, key: str, fallback_key: str) -> str:
    resolved = _resolve_multilingual_text(
        site_config,
        registry,
        lang,
        candidate_paths=[
            ("ui", "footer", key),
            ("footer", key),
        ],
        default="",
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


def _resolve_experience_type_title(
    site_config: Mapping[str, Any],
    registry: Mapping[str, Any],
    lang: str,
    experience_item: Mapping[str, Any],
    site_name: str,
) -> str:
    seo = _ensure_mapping(experience_item.get("seo"), "experience_item.seo")
    title_template = seo.get("title_template")
    if title_template is not None:
        return _translate_node(
            site_config,
            registry,
            lang,
            title_template,
            "experience_item.seo.title_template",
        )
    label = _translate_node(site_config, registry, lang, experience_item.get("label"), "experience_item.label")
    return f"{label} | {site_name}"


def _resolve_experience_type_description(
    site_config: Mapping[str, Any],
    registry: Mapping[str, Any],
    lang: str,
    experience_item: Mapping[str, Any],
) -> str:
    summary = _translate_node(site_config, registry, lang, experience_item.get("summary"), "experience_item.summary")
    if summary:
        return summary

    label = _translate_node(site_config, registry, lang, experience_item.get("label"), "experience_item.label")
    fallback_map = {
        "en": f"Reference profile for {label}, including structural fit, tradeoffs, baseline scores, and traveler-profile affinity.",
        "ar": f"ملف مرجعي لـ {label} يشمل الملاءمة البنيوية والمفاضلات والدرجات الأساسية وملاءمة أنماط المسافرين.",
        "fr": f"Profil de référence pour {label}, incluant adéquation structurelle, arbitrages, scores de base et affinité par profil de voyageur.",
        "es": f"Perfil de referencia para {label}, incluyendo ajuste estructural, compensaciones, puntuaciones base y afinidad por perfil de viajero.",
        "de": f"Referenzprofil für {label} mit struktureller Passung, Trade-offs, Basiswerten und Affinität nach Reisendenprofil.",
        "zh": f"{label} 的参考画像，包含结构适配、权衡关系、基础分数与旅行者类型适配。",
        "ja": f"{label} の参照プロフィール。構造適合、トレードオフ、基礎スコア、旅行者タイプ適合性を含む。",
    }
    return fallback_map.get(lang, fallback_map["en"])


def _translate_multilingual_block(
    site_config: Mapping[str, Any],
    registry: Mapping[str, Any],
    lang: str,
    block: Any,
    field_name: str,
) -> str:
    return _translate_node(site_config, registry, lang, block, field_name, default="")


def _build_structural_axes_display(lang: str, axes: Mapping[str, Any]) -> List[Dict[str, str]]:
    output: List[Dict[str, str]] = []
    ordered_keys = [
        "structure_intensity",
        "autonomy_level",
        "support_level",
        "pace_profile",
        "immersion_profile",
        "predictability_profile",
    ]
    for key in ordered_keys:
        raw_value = _ensure_string(axes.get(key), f"experience_type.structural_axes.{key}")
        label_map = AXIS_LABELS.get(key, {})
        value_map = AXIS_VALUE_LABELS.get(key, {})
        value_labels = value_map.get(raw_value, {})

        output.append({
            "key": key,
            "label": label_map.get(lang) or label_map.get("en") or key,
            "value": value_labels.get(lang) or value_labels.get("en") or raw_value,
        })
    return output


def _build_baseline_scores_display(
    site_config: Mapping[str, Any],
    registry: Mapping[str, Any],
    lang: str,
    baseline_scores: Mapping[str, Any],
    criteria_display_data: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    criteria_by_id = _ensure_mapping(criteria_display_data.get("criteria_by_id"), "criteria_display_data.criteria_by_id")
    rating_bands = _ensure_list(criteria_display_data.get("rating_bands"), "criteria_display_data.rating_bands")

    ordered_keys = [
        "constraint_fit",
        "operational_complexity",
        "control_vs_support",
        "depth_of_experience",
        "predictability",
        "traveler_type_fit",
    ]

    output: List[Dict[str, Any]] = []
    for criterion_id in ordered_keys:
        score = int(baseline_scores[criterion_id])
        criterion_meta = _ensure_mapping(criteria_by_id.get(criterion_id), f"criteria_by_id[{criterion_id}]")
        copy = _ensure_mapping(criterion_meta.get("copy"), f"criteria_by_id[{criterion_id}].copy")
        description = copy.get("description")
        output.append({
            "id": criterion_id,
            "name": _translate_multilingual_block(
                site_config, registry, lang, copy.get("name"), f"criteria.{criterion_id}.copy.name"
            ),
            "score": score,
            "band_label": _find_rating_band_label(score, lang, rating_bands),
            "direction": _ensure_string(
                criterion_meta.get("ranking_direction"),
                f"criteria_by_id[{criterion_id}].ranking_direction",
            ),
            "direction_label": "",
            "description": _translate_multilingual_block(
                site_config, registry, lang, description, f"criteria.{criterion_id}.copy.description"
            ) if description is not None else "",
        })
    return output


def _build_profile_affinity_display(
    site_config: Mapping[str, Any],
    registry: Mapping[str, Any],
    lang: str,
    profile_affinity: Mapping[str, Any],
    criteria_display_data: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    traveler_profiles = _ensure_list(criteria_display_data.get("traveler_profiles"), "criteria_display_data.traveler_profiles")
    ordered: List[Dict[str, Any]] = []

    for item in traveler_profiles:
        profile = _ensure_mapping(item, "traveler_profile")
        profile_id = _ensure_string(profile.get("id"), "traveler_profile.id")
        label_block = profile.get("label")
        level = _ensure_string(profile_affinity.get(profile_id), f"profile_affinity.{profile_id}")
        ordered.append({
            "id": profile_id,
            "label": _translate_multilingual_block(
                site_config, registry, lang, label_block, f"traveler_profiles.{profile_id}.label"
            ),
            "level": level,
            "level_label": "",
        })

    return ordered


def _build_adjacent_types_display(
    site_config: Mapping[str, Any],
    registry: Mapping[str, Any],
    lang: str,
    adjacent_ids: Sequence[str],
    experience_config: Mapping[str, Any],
) -> List[Dict[str, str]]:
    by_id = _ensure_mapping(experience_config.get("experience_types_by_id"), "experience_config.experience_types_by_id")
    output: List[Dict[str, str]] = []

    for adjacent_id in adjacent_ids:
        item = _ensure_mapping(by_id.get(adjacent_id), f"experience_types_by_id[{adjacent_id}]")
        slug = _ensure_string(item.get("slug"), f"experience_types_by_id[{adjacent_id}].slug")
        output.append({
            "id": adjacent_id,
            "label": _translate_multilingual_block(
                site_config, registry, lang, item.get("label"), f"experience_types_by_id[{adjacent_id}].label"
            ),
            "url": build_experience_type_path(site_config, lang, slug, absolute=False, registry=registry),
        })

    return output


def _build_experience_lang_url_map(
    site_config: Mapping[str, Any],
    registry: Mapping[str, Any],
    experience_item: Mapping[str, Any],
) -> Dict[str, str]:
    enabled_codes: List[str] = []
    for item in get_enabled_languages(site_config, registry=registry):
        mapping = _ensure_mapping(item, "site_config.languages[]")
        enabled_codes.append(_ensure_string(mapping.get("code"), "site_config.languages[].code"))

    slug = _ensure_string(experience_item.get("slug"), "experience_item.slug")
    slug_by_lang = {code: slug for code in enabled_codes}

    return build_experience_type_language_url_map(
        site_config,
        slug_by_lang,
        registry=registry,
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
            raise GenerateExperienceTypesError(f"Missing URL in language URL map for language: {code!r}")

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


def _build_experience_type_seo(
    site_config: Mapping[str, Any],
    registry: Mapping[str, Any],
    lang: str,
    title: str,
    description: str,
    logo_url: str,
    experience_item: Mapping[str, Any],
) -> Dict[str, Any]:
    slug = _ensure_string(experience_item.get("slug"), "experience_item.slug")
    canonical_url = build_experience_type_path(site_config, lang, slug, absolute=True, registry=registry)
    urls_by_lang = _build_experience_lang_url_map(site_config, registry, experience_item)

    organization_jsonld = build_organization_jsonld(
        site_config,
        logo_url=logo_url,
    )
    website_jsonld = build_website_jsonld(
        site_config,
        lang,
        home_url=build_home_path(site_config, lang, absolute=True, registry=registry),
    )
    webpage_jsonld = build_webpage_jsonld(
        name=title,
        description=description,
        url=canonical_url,
        lang=lang,
        is_part_of_url=build_home_path(site_config, lang, absolute=True, registry=registry),
    )

    seo_payload = build_page_seo(
        site_config,
        lang,
        page_title=title,
        page_description=description,
        canonical_url=canonical_url,
        urls_by_lang=urls_by_lang,
        page_type="article",
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


def build_experience_type_context(
    site_config: Mapping[str, Any],
    registry: Mapping[str, Any],
    lang: str,
    experience_item: Mapping[str, Any],
    experience_config: Mapping[str, Any],
    criteria_display_data: Mapping[str, Any],
) -> Dict[str, Any]:
    lang_conf = _ensure_mapping(
        get_language_config(site_config, lang, registry=registry),
        f"language_config[{lang}]",
    )

    base_url = _resolve_base_url(site_config)
    site_name = _resolve_site_name(site_config, registry, lang)
    site_tagline = _resolve_site_tagline(site_config, registry, lang)
    assets = _resolve_core_asset_urls(site_config)
    title = _resolve_experience_type_title(site_config, registry, lang, experience_item, site_name)
    description = _resolve_experience_type_description(site_config, registry, lang, experience_item)

    seo_payload = _build_experience_type_seo(
        site_config,
        registry,
        lang,
        title,
        description,
        assets["favicon_url"],
        experience_item,
    )

    families_by_id = _ensure_mapping(experience_config.get("families_by_id"), "experience_config.families_by_id")
    family_item = _ensure_mapping(
        families_by_id.get(_ensure_string(experience_item.get("family"), "experience_item.family")),
        "families_by_id.family_item",
    )

    page_lang_urls = _build_experience_lang_url_map(site_config, registry, experience_item)

    experience_data: Dict[str, Any] = {
        "id": _ensure_string(experience_item.get("id"), "experience_item.id"),
        "slug": _ensure_string(experience_item.get("slug"), "experience_item.slug"),
        "label": _translate_multilingual_block(
            site_config, registry, lang, experience_item.get("label"), "experience_item.label"
        ),
        "summary": _translate_multilingual_block(
            site_config, registry, lang, experience_item.get("summary"), "experience_item.summary"
        ),
        "formal_definition": _ensure_string(
            experience_item.get("formal_definition"),
            "experience_item.formal_definition",
        ),
        "family_label": _translate_multilingual_block(
            site_config, registry, lang, family_item.get("label"), "family_item.label"
        ),
        "tradeoff_signature": _ensure_string(
            experience_item.get("tradeoff_signature"),
            "experience_item.tradeoff_signature",
        ),
        "inclusion_scope": _ensure_list(experience_item.get("inclusion_scope"), "experience_item.inclusion_scope"),
        "exclusion_scope": _ensure_list(experience_item.get("exclusion_scope"), "experience_item.exclusion_scope"),
        "strengths": _ensure_list(experience_item.get("strengths"), "experience_item.strengths"),
        "weaknesses": _ensure_list(experience_item.get("weaknesses"), "experience_item.weaknesses"),
        "best_for": _ensure_list(experience_item.get("best_for"), "experience_item.best_for"),
        "poor_fit_for": _ensure_list(experience_item.get("poor_fit_for"), "experience_item.poor_fit_for"),
        "structural_axes_display": _build_structural_axes_display(
            lang,
            _ensure_mapping(experience_item.get("structural_axes"), "experience_item.structural_axes"),
        ),
        "baseline_scores_display": _build_baseline_scores_display(
            site_config,
            registry,
            lang,
            _ensure_mapping(experience_item.get("baseline_scores"), "experience_item.baseline_scores"),
            criteria_display_data,
        ),
        "profile_affinity_display": _build_profile_affinity_display(
            site_config,
            registry,
            lang,
            _ensure_mapping(experience_item.get("profile_affinity"), "experience_item.profile_affinity"),
            criteria_display_data,
        ),
        "adjacent_types_display": _build_adjacent_types_display(
            site_config,
            registry,
            lang,
            _ensure_list(experience_item.get("adjacent_types"), "experience_item.adjacent_types"),
            experience_config,
        ),
    }

    short_label = experience_item.get("short_label")
    if short_label is not None:
        experience_data["short_label"] = _translate_multilingual_block(
            site_config, registry, lang, short_label, "experience_item.short_label"
        )

    context: Dict[str, Any] = {
        # Core runtime
        "base_url": base_url,
        "lang": lang,
        "is_rtl": _ensure_string(lang_conf.get("dir", "ltr"), f"language[{lang}].dir") == "rtl",
        "seo": seo_payload,
        "body_class": "page-experience-type",
        "current_year": datetime.now(timezone.utc).year,

        # Site
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

        # Navigation
        "active_nav": "",
        "home_url": build_home_path(site_config, lang, absolute=False, registry=registry),
        "compare_url": build_compare_index_path(site_config, lang, absolute=False, registry=registry),
        "destinations_url": build_destinations_index_path(site_config, lang, absolute=False, registry=registry),
        "tools_url": build_tools_index_path(site_config, lang, absolute=False, registry=registry),
        "methodology_url": build_methodology_path(site_config, lang, absolute=False, registry=registry),
        "acquire_url": build_acquire_path(site_config, lang, absolute=False, registry=registry),

        # Labels
        "nav_home": _resolve_nav_label(site_config, registry, lang, "home", "nav_home"),
        "nav_compare": _resolve_nav_label(site_config, registry, lang, "compare", "nav_compare"),
        "nav_destinations": _resolve_nav_label(site_config, registry, lang, "destinations", "nav_destinations"),
        "nav_tools": _resolve_nav_label(site_config, registry, lang, "tools", "nav_tools"),
        "nav_methodology": _resolve_nav_label(site_config, registry, lang, "methodology", "nav_methodology"),
        "nav_acquire": _resolve_nav_label(site_config, registry, lang, "acquire", "nav_acquire"),
        "footer_about": _resolve_footer_label(site_config, registry, lang, "about", "footer_about"),
        "footer_contact": _resolve_footer_label(site_config, registry, lang, "contact", "footer_contact"),
        "footer_privacy": _resolve_footer_label(site_config, registry, lang, "privacy", "footer_privacy"),
        "footer_terms": _resolve_footer_label(site_config, registry, lang, "terms", "footer_terms"),
        "footer_acquire": _resolve_footer_label(site_config, registry, lang, "acquire", "footer_acquire"),

        # Accessibility / language switcher
        "ui_skip_to_content_label": _resolve_ui_label(
            site_config, registry, lang, "skip_to_content", "skip_to_content"
        ),
        "language_switcher": _build_language_switcher(site_config, registry, lang, page_lang_urls),
        "page_lang_urls": page_lang_urls,

        # Page-specific
        "experience_type": experience_data,
        "experience_type_count": len(_ensure_list(experience_config.get("active_experience_types"), "experience_config.active_experience_types")),
    }

    return context


# ============================================================================
# Rendering
# ============================================================================

def _load_experience_type_template(env: Environment):
    try:
        return env.get_template("pages/experience_type.html")
    except Exception as exc:
        raise RenderError(f"Unable to load template 'pages/experience_type.html': {exc}") from exc


def render_experience_type_html(
    site_config: Mapping[str, Any],
    registry: Mapping[str, Any],
    lang: str,
    experience_item: Mapping[str, Any],
    experience_config: Mapping[str, Any],
    criteria_display_data: Mapping[str, Any],
    *,
    env: Environment,
) -> str:
    template = _load_experience_type_template(env)
    context = build_experience_type_context(
        site_config,
        registry,
        lang,
        experience_item,
        experience_config,
        criteria_display_data,
    )

    try:
        html = template.render(**context)
    except Exception as exc:
        exp_id = _ensure_string(experience_item.get("id"), "experience_item.id")
        raise RenderError(
            f"Failed to render experience type page for language {lang!r} and type {exp_id!r}: {exc}"
        ) from exc

    if not isinstance(html, str) or not html.strip():
        exp_id = _ensure_string(experience_item.get("id"), "experience_item.id")
        raise RenderError(f"Rendered experience type page is empty for language {lang!r} and type {exp_id!r}.")

    return html


# ============================================================================
# Target resolution
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
            raise GenerateExperienceTypesError(
                f"Requested language {requested!r} is not enabled. Enabled: {', '.join(enabled_codes)}"
            )
        return [requested]

    return enabled_codes


def _resolve_target_experience_types(
    experience_config: Mapping[str, Any],
    requested_type_id: Optional[str],
) -> List[Mapping[str, Any]]:
    items = _ensure_list(experience_config.get("active_experience_types"), "experience_config.active_experience_types")

    if requested_type_id is None:
        return [_ensure_mapping(item, "active_experience_type") for item in items]

    requested = _ensure_string(requested_type_id, "--type-id")
    by_id = _ensure_mapping(experience_config.get("active_experience_types_by_id"), "experience_config.active_experience_types_by_id")
    if requested not in by_id:
        raise GenerateExperienceTypesError(
            f"Requested type id {requested!r} does not exist in active experience types."
        )
    return [_ensure_mapping(by_id[requested], f"active_experience_types_by_id[{requested}]")]


# ============================================================================
# Public API
# ============================================================================

def generate_experience_type_pages(
    *,
    requested_lang: Optional[str] = None,
    requested_type_id: Optional[str] = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> List[Path]:
    site_config = load_site_config()
    registry = build_language_registry(site_config)

    try:
        experience_config = load_experience_types()
    except Exception as exc:
        raise ConfigError(f"Failed to load experience types through loaders.py: {exc}") from exc

    criteria_display_data = _load_comparison_criteria_display_data()
    env = _build_jinja_env()

    target_languages = _resolve_target_languages(site_config, registry, requested_lang)
    target_types = _resolve_target_experience_types(experience_config, requested_type_id)

    rendered_payloads: List[Tuple[Path, str, str, str]] = []

    for experience_item in target_types:
        exp_id = _ensure_string(experience_item.get("id"), "experience_item.id")
        slug = _ensure_string(experience_item.get("slug"), "experience_item.slug")

        for lang in target_languages:
            html = render_experience_type_html(
                site_config,
                registry,
                lang,
                experience_item,
                experience_config,
                criteria_display_data,
                env=env,
            )
            route_path = build_experience_type_path(
                site_config,
                lang,
                slug,
                absolute=False,
                registry=registry,
            )
            output_path = _route_path_to_output_file(output_dir, route_path)
            rendered_payloads.append((output_path, html, lang, exp_id))

    written_paths: List[Path] = []
    try:
        for output_path, html, lang, exp_id in rendered_payloads:
            _atomic_write_text(output_path, html)
            written_paths.append(output_path)
            log.info("Generated experience type page [%s | %s] -> %s", lang, exp_id, output_path)
    except Exception as exc:
        raise GenerateExperienceTypesError(
            f"Failed while writing generated experience type page output: {exc}"
        ) from exc

    return written_paths


# ============================================================================
# CLI
# ============================================================================

def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate multilingual TourVsTravel experience-type reference pages."
    )
    parser.add_argument(
        "--lang",
        type=str,
        default=None,
        help="Generate only one enabled language code (e.g. en, ar, fr).",
    )
    parser.add_argument(
        "--type-id",
        type=str,
        default=None,
        help="Generate only one experience type id (e.g. guided_group_tour).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Output directory root. Default: ./output",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    configure_logging()
    args = parse_args(argv)

    try:
        written = generate_experience_type_pages(
            requested_lang=args.lang,
            requested_type_id=args.type_id,
            output_dir=args.output_dir.resolve(),
        )
    except GenerateExperienceTypesError as exc:
        log.error(str(exc))
        return 1
    except Exception as exc:
        log.exception("Unexpected experience-type generator failure: %s", exc)
        return 1

    log.info("Experience type generation completed successfully. Files written: %d", len(written))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
