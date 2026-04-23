#!/usr/bin/env python3
"""
TourVsTravel — Experience Type Pages Generator
==============================================

Purpose
-------
Generate multilingual experience type pages into:

    output/{lang}/styles/{slug}/index.html

Data policy
-----------
- experience types MUST be loaded via scripts.loaders.load_experience_types()
- no direct YAML reads in this generator
- fail closed on missing template, missing assets, or invalid context
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
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from scripts.i18n import (
    build_language_registry,
    get_enabled_languages,
    get_language_config,
    translate_string,
)
from scripts.loaders import load_experience_types, load_site_config
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
    render_meta_template,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("generate_experience_types")


ROOT_DIR = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = ROOT_DIR / "templates"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "output"


AXIS_LABELS: Dict[str, Dict[str, str]] = {
    "structure_intensity": {"en": "Structure intensity", "ar": "شدة البنية"},
    "autonomy_level": {"en": "Autonomy level", "ar": "مستوى الاستقلالية"},
    "support_level": {"en": "Support level", "ar": "مستوى الدعم"},
    "pace_profile": {"en": "Pace profile", "ar": "نمط الوتيرة"},
    "immersion_profile": {"en": "Immersion profile", "ar": "نمط الانغماس"},
    "predictability_profile": {"en": "Predictability profile", "ar": "نمط التنبؤ"},
}

VALUE_LABELS: Dict[str, Dict[str, str]] = {
    "low": {"en": "Low", "ar": "منخفض"},
    "medium": {"en": "Medium", "ar": "متوسط"},
    "high": {"en": "High", "ar": "مرتفع"},
    "fixed": {"en": "Fixed", "ar": "ثابت"},
    "balanced": {"en": "Balanced", "ar": "متوازن"},
    "flexible": {"en": "Flexible", "ar": "مرن"},
    "surface": {"en": "Surface", "ar": "سطحي"},
    "deep": {"en": "Deep", "ar": "عميق"},
}

BASELINE_LABELS: Dict[str, Dict[str, str]] = {
    "constraint_fit": {"en": "Constraint fit", "ar": "ملاءمة القيود"},
    "operational_complexity": {"en": "Operational complexity", "ar": "التعقيد التشغيلي"},
    "control_vs_support": {"en": "Control vs support", "ar": "التحكم مقابل الدعم"},
    "depth_of_experience": {"en": "Depth of experience", "ar": "عمق التجربة"},
    "predictability": {"en": "Predictability", "ar": "قابلية التنبؤ"},
    "traveler_type_fit": {"en": "Traveler type fit", "ar": "الملاءمة حسب نوع المسافر"},
}

PROFILE_LABELS: Dict[str, Dict[str, str]] = {
    "independent_planner": {"en": "Independent planner", "ar": "المخطط المستقل"},
    "family_coordinator": {"en": "Family coordinator", "ar": "منسق العائلة"},
    "first_time_traveler": {"en": "First-time traveler", "ar": "المسافر لأول مرة"},
    "cost_sensitive_explorer": {"en": "Cost-sensitive explorer", "ar": "المستكشف الحساس للتكلفة"},
    "comfort_priority_traveler": {"en": "Comfort-priority traveler", "ar": "المسافر الباحث عن الراحة"},
    "logistics_averse_traveler": {"en": "Logistics-averse traveler", "ar": "المسافر المتجنب للتعقيد اللوجستي"},
}

DIRECTION_LABELS: Dict[str, Dict[str, str]] = {
    "higher_is_better": {"en": "Higher is stronger", "ar": "الدرجة الأعلى أقوى"},
    "lower_is_better": {"en": "Lower burden is stronger", "ar": "العبء الأقل أقوى"},
}

LEVEL_LABELS: Dict[str, Dict[str, str]] = {
    "low": {"en": "Low affinity", "ar": "ملاءمة منخفضة"},
    "medium": {"en": "Moderate affinity", "ar": "ملاءمة متوسطة"},
    "high": {"en": "High affinity", "ar": "ملاءمة عالية"},
}


class GenerateExperienceTypesError(Exception):
    """Base generator exception."""


class ConfigError(GenerateExperienceTypesError):
    """Raised when configuration is missing or invalid."""


class RenderError(GenerateExperienceTypesError):
    """Raised when template rendering fails."""


@dataclass(frozen=True)
class PreloadAsset:
    href: str
    as_value: str
    type_value: Optional[str] = None
    crossorigin: Optional[str] = None

    def as_template_dict(self) -> Dict[str, str]:
        payload: Dict[str, str] = {"href": self.href, "as": self.as_value}
        if self.type_value:
            payload["type"] = self.type_value
        if self.crossorigin:
            payload["crossorigin"] = self.crossorigin
        return payload


def _ensure_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise GenerateExperienceTypesError(f"{label} must be a mapping/object.")
    return value


def _ensure_list(value: Any, label: str) -> List[Any]:
    if not isinstance(value, list):
        raise GenerateExperienceTypesError(f"{label} must be a list.")
    return value


def _ensure_string(value: Any, label: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise GenerateExperienceTypesError(f"{label} must be a string.")
    text = value.strip()
    if not allow_empty and not text:
        raise GenerateExperienceTypesError(f"{label} must not be empty.")
    return text


def _localized_label(mapping: Mapping[str, Dict[str, str]], key: str, lang: str) -> str:
    candidate = mapping.get(key, {})
    if lang in candidate and candidate[lang].strip():
        return candidate[lang]
    if "en" in candidate and candidate["en"].strip():
        return candidate["en"]
    return key.replace("_", " ").strip().title()


def _get_nested(mapping: Mapping[str, Any], path: Sequence[str], default: Any = None) -> Any:
    current: Any = mapping
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return default
        current = current[key]
    return current


def _normalize_https_base_url(value: str) -> str:
    text = _ensure_string(value, "site_config.site.base_url")
    parsed = urlparse(text)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ConfigError("site_config.site.base_url must be absolute HTTPS URL.")
    if parsed.username is not None or parsed.password is not None:
        raise ConfigError("site_config.site.base_url must not contain credentials.")
    if parsed.query or parsed.fragment:
        raise ConfigError("site_config.site.base_url must not contain query/fragment.")
    if (parsed.path or "") not in ("", "/"):
        raise ConfigError("site_config.site.base_url must not include a path.")
    return f"https://{parsed.netloc.rstrip('/')}"


def _translate_multilingual(
    value: Any,
    *,
    lang: str,
    site_config: Mapping[str, Any],
    registry: Mapping[str, Any],
    field_name: str,
) -> str:
    return translate_string(
        value,
        lang,
        site_config=site_config,
        registry=registry,
        field_name=field_name,
    )


def _build_jinja_env() -> Environment:
    if not TEMPLATES_DIR.exists():
        raise RenderError(f"Templates directory missing: {TEMPLATES_DIR}")
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
            raise GenerateExperienceTypesError(f"Failed creating temp file for {path}")
        tmp_path.replace(path)
    except Exception:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise


def _resolve_core_asset_urls() -> Dict[str, Any]:
    main_css_url = "/static/css/main.css"
    main_js_url = "/static/js/main.js"
    favicon_url = "/static/img/brand/logo-icon.jpg"
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
        "favicon_type": "image/jpeg",
        "apple_touch_icon_url": favicon_url,
        "manifest_url": "/site.webmanifest",
        "preload_assets": preload_assets,
    }


def _build_structural_axes_display(
    axes: Mapping[str, Any],
    *,
    lang: str,
) -> List[Dict[str, str]]:
    order = [
        "structure_intensity",
        "autonomy_level",
        "support_level",
        "pace_profile",
        "immersion_profile",
        "predictability_profile",
    ]
    output: List[Dict[str, str]] = []
    for key in order:
        raw = _ensure_string(axes.get(key), f"experience.structural_axes.{key}")
        output.append(
            {
                "key": key,
                "label": _localized_label(AXIS_LABELS, key, lang),
                "value": _localized_label(VALUE_LABELS, raw, lang),
            }
        )
    return output


def _build_baseline_scores_display(
    scores: Mapping[str, Any],
    *,
    lang: str,
) -> List[Dict[str, Any]]:
    direction_by_key = {
        "operational_complexity": "lower_is_better",
        "constraint_fit": "higher_is_better",
        "control_vs_support": "higher_is_better",
        "depth_of_experience": "higher_is_better",
        "predictability": "higher_is_better",
        "traveler_type_fit": "higher_is_better",
    }
    ordered_keys = [
        "constraint_fit",
        "operational_complexity",
        "control_vs_support",
        "depth_of_experience",
        "predictability",
        "traveler_type_fit",
    ]
    output: List[Dict[str, Any]] = []
    for key in ordered_keys:
        score = int(scores.get(key))
        if score <= 2:
            band_key = "low"
        elif score == 3:
            band_key = "medium"
        else:
            band_key = "high"
        direction = direction_by_key[key]
        output.append(
            {
                "id": key,
                "name": _localized_label(BASELINE_LABELS, key, lang),
                "score": score,
                "band_label": _localized_label(LEVEL_LABELS, band_key, lang),
                "direction": direction,
                "direction_label": _localized_label(DIRECTION_LABELS, direction, lang),
                "description": "",
            }
        )
    return output


def _build_profile_affinity_display(
    affinity: Mapping[str, Any],
    *,
    lang: str,
) -> List[Dict[str, str]]:
    ordered_keys = [
        "independent_planner",
        "family_coordinator",
        "first_time_traveler",
        "cost_sensitive_explorer",
        "comfort_priority_traveler",
        "logistics_averse_traveler",
    ]
    output: List[Dict[str, str]] = []
    for key in ordered_keys:
        level = _ensure_string(affinity.get(key), f"experience.profile_affinity.{key}")
        output.append(
            {
                "id": key,
                "label": _localized_label(PROFILE_LABELS, key, lang),
                "level": level,
                "level_label": _localized_label(LEVEL_LABELS, level, lang),
            }
        )
    return output


def _build_experience_model(
    exp: Mapping[str, Any],
    *,
    lang: str,
    site_config: Mapping[str, Any],
    registry: Mapping[str, Any],
    families_by_id: Mapping[str, Mapping[str, Any]],
    experience_by_id: Mapping[str, Mapping[str, Any]],
) -> Dict[str, Any]:
    exp_id = _ensure_string(exp.get("id"), "experience.id")
    family_id = _ensure_string(exp.get("family"), f"experience[{exp_id}].family")
    family = _ensure_mapping(families_by_id.get(family_id), f"families_by_id[{family_id}]")
    slug = _ensure_string(exp.get("slug"), f"experience[{exp_id}].slug")

    adjacent_types_display: List[Dict[str, str]] = []
    for adjacent_id in _ensure_list(exp.get("adjacent_types"), f"experience[{exp_id}].adjacent_types"):
        adjacent_id_str = _ensure_string(adjacent_id, f"experience[{exp_id}].adjacent_types[]")
        adjacent = _ensure_mapping(
            experience_by_id.get(adjacent_id_str),
            f"experience_types_by_id[{adjacent_id_str}]",
        )
        adjacent_label = _translate_multilingual(
            adjacent.get("label"),
            lang=lang,
            site_config=site_config,
            registry=registry,
            field_name=f"experience[{adjacent_id_str}].label",
        )
        adjacent_slug = _ensure_string(adjacent.get("slug"), f"experience[{adjacent_id_str}].slug")
        adjacent_types_display.append(
            {
                "id": adjacent_id_str,
                "label": adjacent_label,
                "url": build_experience_type_path(
                    site_config,
                    lang,
                    adjacent_slug,
                    absolute=False,
                    registry=registry,
                ),
            }
        )

    model: Dict[str, Any] = {
        "id": exp_id,
        "slug": slug,
        "label": _translate_multilingual(
            exp.get("label"),
            lang=lang,
            site_config=site_config,
            registry=registry,
            field_name=f"experience[{exp_id}].label",
        ),
        "short_label": (
            _translate_multilingual(
                exp.get("short_label"),
                lang=lang,
                site_config=site_config,
                registry=registry,
                field_name=f"experience[{exp_id}].short_label",
            )
            if "short_label" in exp
            else ""
        ),
        "summary": _translate_multilingual(
            exp.get("summary"),
            lang=lang,
            site_config=site_config,
            registry=registry,
            field_name=f"experience[{exp_id}].summary",
        ),
        "formal_definition": _ensure_string(exp.get("formal_definition"), f"experience[{exp_id}].formal_definition"),
        "family_label": _translate_multilingual(
            family.get("label"),
            lang=lang,
            site_config=site_config,
            registry=registry,
            field_name=f"families[{family_id}].label",
        ),
        "tradeoff_signature": _ensure_string(exp.get("tradeoff_signature"), f"experience[{exp_id}].tradeoff_signature"),
        "inclusion_scope": [str(x) for x in _ensure_list(exp.get("inclusion_scope"), f"experience[{exp_id}].inclusion_scope")],
        "exclusion_scope": [str(x) for x in _ensure_list(exp.get("exclusion_scope"), f"experience[{exp_id}].exclusion_scope")],
        "strengths": [str(x) for x in _ensure_list(exp.get("strengths"), f"experience[{exp_id}].strengths")],
        "weaknesses": [str(x) for x in _ensure_list(exp.get("weaknesses"), f"experience[{exp_id}].weaknesses")],
        "best_for": [str(x) for x in _ensure_list(exp.get("best_for"), f"experience[{exp_id}].best_for")],
        "poor_fit_for": [str(x) for x in _ensure_list(exp.get("poor_fit_for"), f"experience[{exp_id}].poor_fit_for")],
        "structural_axes_display": _build_structural_axes_display(
            _ensure_mapping(exp.get("structural_axes"), f"experience[{exp_id}].structural_axes"),
            lang=lang,
        ),
        "baseline_scores_display": _build_baseline_scores_display(
            _ensure_mapping(exp.get("baseline_scores"), f"experience[{exp_id}].baseline_scores"),
            lang=lang,
        ),
        "profile_affinity_display": _build_profile_affinity_display(
            _ensure_mapping(exp.get("profile_affinity"), f"experience[{exp_id}].profile_affinity"),
            lang=lang,
        ),
        "adjacent_types_display": adjacent_types_display,
    }
    return model


def _build_experience_seo(
    site_config: Mapping[str, Any],
    registry: Mapping[str, Any],
    lang: str,
    exp: Mapping[str, Any],
    exp_model: Mapping[str, Any],
    site_name: str,
) -> Dict[str, Any]:
    slug = _ensure_string(exp.get("slug"), "experience.slug")
    canonical_url = build_experience_type_path(
        site_config,
        lang,
        slug,
        absolute=True,
        registry=registry,
    )
    slug_by_lang = {
        _ensure_string(item.get("code"), "site_config.languages[].code"): slug
        for item in get_enabled_languages(site_config, registry=registry)
    }
    urls_by_lang = build_experience_type_language_url_map(
        site_config,
        slug_by_lang,
        registry=registry,
    )

    seo_block = _ensure_mapping(exp.get("seo"), "experience.seo")
    title_tpl_multilang = seo_block.get("title_template")
    title_template = _translate_multilingual(
        title_tpl_multilang,
        lang=lang,
        site_config=site_config,
        registry=registry,
        field_name="experience.seo.title_template",
    )
    title = render_meta_template(
        title_template,
        {
            "label": _ensure_string(exp_model.get("label"), "experience_model.label"),
            "site_name": site_name,
            "slug": slug,
            "experience_id": _ensure_string(exp.get("id"), "experience.id"),
        },
        label="experience.seo.title_template",
    )
    description = _ensure_string(exp_model.get("summary"), "experience_model.summary")

    organization_jsonld = build_organization_jsonld(site_config, logo_url="/static/img/brand/logo-icon.jpg")
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
        jsonld_payloads=[organization_jsonld, website_jsonld, webpage_jsonld],
    )
    return seo_payload


def _resolve_site_name(site_config: Mapping[str, Any], registry: Mapping[str, Any], lang: str) -> str:
    site = _ensure_mapping(site_config.get("site"), "site_config.site")
    return _translate_multilingual(
        site.get("name"),
        lang=lang,
        site_config=site_config,
        registry=registry,
        field_name="site_config.site.name",
    )


def build_experience_type_context(
    site_config: Mapping[str, Any],
    experience_config: Mapping[str, Any],
    registry: Mapping[str, Any],
    lang: str,
    exp: Mapping[str, Any],
) -> Dict[str, Any]:
    site_section = _ensure_mapping(site_config.get("site"), "site_config.site")
    base_url = _normalize_https_base_url(_ensure_string(site_section.get("base_url"), "site_config.site.base_url"))
    lang_conf = _ensure_mapping(get_language_config(site_config, lang, registry=registry), f"language_config[{lang}]")

    families_by_id = _ensure_mapping(experience_config.get("families_by_id"), "experience_config.families_by_id")
    experience_by_id = _ensure_mapping(
        experience_config.get("experience_types_by_id"),
        "experience_config.experience_types_by_id",
    )
    experience_model = _build_experience_model(
        exp,
        lang=lang,
        site_config=site_config,
        registry=registry,
        families_by_id=families_by_id,
        experience_by_id=experience_by_id,
    )
    site_name = _resolve_site_name(site_config, registry, lang)
    seo_payload = _build_experience_seo(
        site_config,
        registry,
        lang,
        exp,
        experience_model,
        site_name,
    )
    assets = _resolve_core_asset_urls()

    context: Dict[str, Any] = {
        "base_url": base_url,
        "lang": lang,
        "is_rtl": _ensure_string(lang_conf.get("dir", "ltr"), f"language[{lang}].dir") == "rtl",
        "seo": seo_payload,
        "canonical_url": seo_payload.get("canonical_url"),
        "hreflang": seo_payload.get("hreflang", []),
        "meta_desc": seo_payload.get("description", ""),
        "robots_directive": seo_payload.get("robots_directive", ""),
        "body_class": "page-experience-type",
        "current_year": datetime.now(timezone.utc).year,
        "site_name": site_name,
        "site_tagline": "",
        "footer_note": "",
        "theme_color": "#0f172a",
        "referrer_policy": "strict-origin-when-cross-origin",
        "csp_meta_policy": None,
        "main_css_url": assets["main_css_url"],
        "main_js_url": assets["main_js_url"],
        "favicon_url": assets["favicon_url"],
        "favicon_type": assets["favicon_type"],
        "apple_touch_icon_url": assets["apple_touch_icon_url"],
        "manifest_url": assets["manifest_url"],
        "preload_assets": assets["preload_assets"],
        "page_css_assets": [],
        "page_js_assets": [],
        "active_nav": "",
        "home_url": build_home_path(site_config, lang, absolute=False, registry=registry),
        "compare_url": build_compare_index_path(site_config, lang, absolute=False, registry=registry),
        "destinations_url": build_destinations_index_path(site_config, lang, absolute=False, registry=registry),
        "tools_url": build_tools_index_path(site_config, lang, absolute=False, registry=registry),
        "methodology_url": build_methodology_path(site_config, lang, absolute=False, registry=registry),
        "acquire_url": build_acquire_path(site_config, lang, absolute=False, registry=registry),
        "nav_home": "Home",
        "nav_compare": "Compare",
        "nav_destinations": "Destinations",
        "nav_tools": "Tools",
        "nav_methodology": "Methodology",
        "nav_report": "Report",
        "footer_about": "About",
        "footer_contact": "Contact",
        "footer_privacy": "Privacy",
        "footer_terms": "Terms",
        "footer_acquire": "Acquire Domain",
        "ui_skip_to_content_label": "Skip to content",
        "experience_type": experience_model,
        "experience_type_count": len(
            _ensure_list(experience_config.get("experience_types"), "experience_config.experience_types")
        ),
        "methodology_url": build_methodology_path(site_config, lang, absolute=False, registry=registry),
        "compare_url": build_compare_index_path(site_config, lang, absolute=False, registry=registry),
        "destinations_url": build_destinations_index_path(site_config, lang, absolute=False, registry=registry),
    }
    return context


def _load_template(env: Environment):
    try:
        return env.get_template("pages/experience_type.html")
    except Exception as exc:
        raise RenderError(f"Unable to load template 'pages/experience_type.html': {exc}") from exc


def render_experience_type_html(
    site_config: Mapping[str, Any],
    experience_config: Mapping[str, Any],
    registry: Mapping[str, Any],
    lang: str,
    exp: Mapping[str, Any],
    *,
    env: Environment,
) -> str:
    template = _load_template(env)
    context = build_experience_type_context(site_config, experience_config, registry, lang, exp)
    try:
        html = template.render(**context)
    except Exception as exc:
        exp_id = _ensure_string(exp.get("id"), "experience.id")
        raise RenderError(f"Failed rendering experience type {exp_id!r} for {lang!r}: {exc}") from exc
    if not isinstance(html, str) or not html.strip():
        raise RenderError("Rendered experience type page is empty.")
    return html


def _resolve_target_languages(
    site_config: Mapping[str, Any],
    registry: Mapping[str, Any],
    requested_lang: Optional[str],
) -> List[str]:
    enabled_codes = [
        _ensure_string(item.get("code"), "site_config.languages[].code")
        for item in get_enabled_languages(site_config, registry=registry)
    ]
    if requested_lang:
        lang = _ensure_string(requested_lang, "--lang")
        if lang not in enabled_codes:
            raise GenerateExperienceTypesError(
                f"Requested language {lang!r} is not enabled. Enabled: {', '.join(enabled_codes)}"
            )
        return [lang]
    return enabled_codes


def _resolve_target_experience_types(
    experience_config: Mapping[str, Any],
    requested_experience_id: Optional[str],
) -> List[Mapping[str, Any]]:
    items = [
        _ensure_mapping(item, "experience_config.experience_types[]")
        for item in _ensure_list(
            experience_config.get("experience_types"),
            "experience_config.experience_types",
        )
    ]
    if not requested_experience_id:
        return items

    target_id = _ensure_string(requested_experience_id, "--experience-id")
    filtered = [item for item in items if _ensure_string(item.get("id"), "experience.id") == target_id]
    if not filtered:
        raise GenerateExperienceTypesError(f"Unknown experience id: {target_id!r}")
    return filtered


def generate_experience_type_pages(
    *,
    requested_lang: Optional[str] = None,
    requested_experience_id: Optional[str] = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> List[Path]:
    site_config = load_site_config()
    experience_config = load_experience_types()
    registry = build_language_registry(site_config)
    env = _build_jinja_env()

    target_languages = _resolve_target_languages(site_config, registry, requested_lang)
    target_experiences = _resolve_target_experience_types(experience_config, requested_experience_id)

    rendered: List[tuple[str, str, str]] = []
    for lang in target_languages:
        for exp in target_experiences:
            slug = _ensure_string(exp.get("slug"), "experience.slug")
            html = render_experience_type_html(
                site_config,
                experience_config,
                registry,
                lang,
                exp,
                env=env,
            )
            rendered.append((lang, slug, html))

    written_paths: List[Path] = []
    for lang, slug, html in rendered:
        out_path = output_dir / lang / "styles" / slug / "index.html"
        _atomic_write_text(out_path, html)
        written_paths.append(out_path)
        log.info("Generated experience type page [%s/%s] -> %s", lang, slug, out_path)

    return written_paths


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate multilingual experience type pages."
    )
    parser.add_argument(
        "--lang",
        type=str,
        default=None,
        help="Generate only one enabled language code.",
    )
    parser.add_argument(
        "--experience-id",
        type=str,
        default=None,
        help="Generate only one experience type by id.",
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
        written = generate_experience_type_pages(
            requested_lang=args.lang,
            requested_experience_id=args.experience_id,
            output_dir=args.output_dir.resolve(),
        )
    except GenerateExperienceTypesError as exc:
        log.error(str(exc))
        return 1
    except Exception as exc:
        log.exception("Unexpected experience type generator failure: %s", exc)
        return 1
    log.info("Experience type generation completed. Files written: %d", len(written))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
