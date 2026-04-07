#!/usr/bin/env python3
"""
TourVsTravel — Strict Internationalization Utilities
===================================================

Purpose:
- Provide a single, strict i18n layer for multilingual content resolution
- Prevent ad hoc `.get(lang)` usage across generators and templates
- Validate site language usage against enabled site_config languages
- Build localized routes, absolute URLs, hreflang maps, and language switchers

Design principles:
- fail closed, not fail open
- explicit fallback chains only
- no silent language drift
- no invalid URLs
- no unsupported language access
"""

from __future__ import annotations

from string import Formatter
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence
from urllib.parse import quote, urlparse


# ============================================================================
# Exceptions
# ============================================================================

class I18nError(Exception):
    """Base i18n exception."""


class UnsupportedLanguageError(I18nError):
    """Raised when a requested language is not enabled in site_config."""


class MissingTranslationError(I18nError):
    """Raised when a translation is missing and cannot be resolved."""


class RouteFormatError(I18nError):
    """Raised when a route template cannot be safely formatted."""


# ============================================================================
# Internal helpers
# ============================================================================

def _ensure_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise I18nError(f"{label} must be a mapping/object.")
    return value


def _ensure_string(value: Any, label: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise I18nError(f"{label} must be a string.")
    if not allow_empty and not value.strip():
        raise I18nError(f"{label} must not be empty.")
    return value


def _ensure_list(value: Any, label: str) -> List[Any]:
    if not isinstance(value, list):
        raise I18nError(f"{label} must be a list.")
    return value


def _is_absolute_https_url(value: str) -> bool:
    parsed = urlparse(value)
    return (
        parsed.scheme == "https"
        and bool(parsed.netloc)
        and parsed.username is None
        and parsed.password is None
    )


def _dedupe_preserve_order(values: Iterable[str]) -> List[str]:
    seen = set()
    output: List[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            output.append(value)
    return output


def _get_site_mapping(site_config: Mapping[str, Any]) -> Mapping[str, Any]:
    return _ensure_mapping(site_config, "site_config")


# ============================================================================
# Language registry
# ============================================================================

def build_language_registry(site_config: Mapping[str, Any]) -> Dict[str, Any]:
    """
    Build and validate a normalized registry of enabled site languages.

    Returns:
        {
            "enabled_languages": [...],
            "enabled_codes": [...],
            "by_code": {...},
            "by_hreflang": {...},
            "default_lang": "en",
        }

    This function is intentionally strict:
    - duplicate enabled codes are rejected
    - duplicate enabled hreflang values are rejected
    - invalid dir values are rejected
    - x_default_lang must be enabled if include_x_default=true
    """
    root = _get_site_mapping(site_config)
    languages = _ensure_list(root.get("languages"), "site_config.languages")
    if not languages:
        raise I18nError("site_config.languages must contain at least one language record.")

    enabled_languages: List[Dict[str, Any]] = []
    by_code: Dict[str, Dict[str, Any]] = {}
    by_hreflang: Dict[str, Dict[str, Any]] = {}

    required_keys = {"code", "hreflang", "locale", "dir", "native_name", "label", "enabled"}

    for idx, item in enumerate(languages):
        lang = _ensure_mapping(item, f"site_config.languages[{idx}]")

        missing = required_keys - set(lang.keys())
        if missing:
            raise I18nError(
                f"site_config.languages[{idx}] is missing required key(s): {', '.join(sorted(missing))}"
            )

        code = _ensure_string(lang.get("code"), f"site_config.languages[{idx}].code")
        hreflang = _ensure_string(lang.get("hreflang"), f"site_config.languages[{idx}].hreflang")
        locale = _ensure_string(lang.get("locale"), f"site_config.languages[{idx}].locale")
        direction = _ensure_string(lang.get("dir"), f"site_config.languages[{idx}].dir")
        native_name = _ensure_string(lang.get("native_name"), f"site_config.languages[{idx}].native_name")
        label = _ensure_string(lang.get("label"), f"site_config.languages[{idx}].label")
        enabled = lang.get("enabled")

        if not isinstance(enabled, bool):
            raise I18nError(f"site_config.languages[{idx}].enabled must be a boolean.")
        if direction not in {"ltr", "rtl"}:
            raise I18nError(f"site_config.languages[{idx}].dir must be 'ltr' or 'rtl'.")

        normalized = {
            "code": code,
            "hreflang": hreflang,
            "locale": locale,
            "dir": direction,
            "native_name": native_name,
            "label": label,
            "enabled": enabled,
        }

        if enabled:
            if code in by_code:
                raise I18nError(f"Duplicate enabled language code detected: {code}")
            if hreflang in by_hreflang:
                raise I18nError(f"Duplicate enabled hreflang detected: {hreflang}")

            by_code[code] = normalized
            by_hreflang[hreflang] = normalized
            enabled_languages.append(normalized)

    if not enabled_languages:
        raise I18nError("site_config must contain at least one enabled language.")

    enabled_codes = [item["code"] for item in enabled_languages]

    seo = _ensure_mapping(root.get("seo"), "site_config.seo")
    hreflang_cfg = _ensure_mapping(seo.get("hreflang"), "site_config.seo.hreflang")

    include_x_default = hreflang_cfg.get("include_x_default")
    if not isinstance(include_x_default, bool):
        raise I18nError("site_config.seo.hreflang.include_x_default must be a boolean.")

    if include_x_default:
        x_default_lang = _ensure_string(
            hreflang_cfg.get("x_default_lang"),
            "site_config.seo.hreflang.x_default_lang",
        )
        if x_default_lang not in enabled_codes:
            raise I18nError(
                f"x_default_lang '{x_default_lang}' is not an enabled language."
            )
        default_lang = x_default_lang
    else:
        default_lang = enabled_codes[0]

    return {
        "enabled_languages": enabled_languages,
        "enabled_codes": enabled_codes,
        "by_code": by_code,
        "by_hreflang": by_hreflang,
        "default_lang": default_lang,
    }


# ============================================================================
# Language access
# ============================================================================

def get_enabled_languages(
    site_config: Mapping[str, Any],
    *,
    registry: Optional[Mapping[str, Any]] = None,
) -> List[Dict[str, Any]]:
    active_registry = registry or build_language_registry(site_config)
    return list(_ensure_list(active_registry.get("enabled_languages"), "language_registry.enabled_languages"))


def get_enabled_language_codes(
    site_config: Mapping[str, Any],
    *,
    registry: Optional[Mapping[str, Any]] = None,
) -> List[str]:
    active_registry = registry or build_language_registry(site_config)
    codes = _ensure_list(active_registry.get("enabled_codes"), "language_registry.enabled_codes")
    return [_ensure_string(code, "language_registry.enabled_codes[]") for code in codes]


def get_language_config(
    site_config: Mapping[str, Any],
    lang: str,
    *,
    registry: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    lang_code = _ensure_string(lang, "lang")
    active_registry = registry or build_language_registry(site_config)
    by_code = _ensure_mapping(active_registry.get("by_code"), "language_registry.by_code")

    if lang_code not in by_code:
        raise UnsupportedLanguageError(f"Unsupported or disabled language: {lang_code}")

    return dict(_ensure_mapping(by_code[lang_code], f"language_registry.by_code[{lang_code}]"))


def require_supported_language(
    site_config: Mapping[str, Any],
    lang: str,
    *,
    registry: Optional[Mapping[str, Any]] = None,
) -> str:
    get_language_config(site_config, lang, registry=registry)
    return lang


def get_default_language(
    site_config: Mapping[str, Any],
    *,
    registry: Optional[Mapping[str, Any]] = None,
) -> str:
    active_registry = registry or build_language_registry(site_config)
    return _ensure_string(active_registry.get("default_lang"), "language_registry.default_lang")


def is_rtl_language(
    site_config: Mapping[str, Any],
    lang: str,
    *,
    registry: Optional[Mapping[str, Any]] = None,
) -> bool:
    lang_conf = get_language_config(site_config, lang, registry=registry)
    direction = _ensure_string(lang_conf.get("dir"), f"language[{lang}].dir")
    if direction not in {"ltr", "rtl"}:
        raise I18nError(f"Invalid direction for language '{lang}': {direction}")
    return direction == "rtl"


# ============================================================================
# Translation resolution
# ============================================================================

def build_fallback_chain(
    site_config: Mapping[str, Any],
    lang: str,
    fallback_langs: Optional[Sequence[str]] = None,
    *,
    include_default: bool = True,
    registry: Optional[Mapping[str, Any]] = None,
) -> List[str]:
    """
    Build an explicit fallback chain.

    Order:
    - requested lang
    - explicit fallback_langs
    - default language (optional)

    No arbitrary languages are added silently.
    """
    active_registry = registry or build_language_registry(site_config)
    require_supported_language(site_config, lang, registry=active_registry)

    user_fallbacks = list(fallback_langs or [])
    validated_fallbacks: List[str] = []
    for idx, code in enumerate(user_fallbacks):
        lang_code = _ensure_string(code, f"fallback_langs[{idx}]")
        require_supported_language(site_config, lang_code, registry=active_registry)
        validated_fallbacks.append(lang_code)

    chain = [lang, *validated_fallbacks]
    if include_default:
        chain.append(get_default_language(site_config, registry=active_registry))

    return _dedupe_preserve_order(chain)


def translate(
    value: Any,
    lang: str,
    *,
    site_config: Optional[Mapping[str, Any]] = None,
    fallback_langs: Optional[Sequence[str]] = None,
    allow_literal: bool = True,
    include_default_fallback: bool = True,
    field_name: str = "value",
    registry: Optional[Mapping[str, Any]] = None,
) -> Any:
    """
    Resolve a localized value.

    Rules:
    - If value is not a mapping:
        - return as-is if allow_literal=True
        - otherwise raise
    - If value is a mapping:
        - resolve only through the explicit fallback chain
        - do not silently drift to arbitrary languages
    """
    _ensure_string(lang, "lang")

    if not isinstance(value, Mapping):
        if allow_literal:
            return value
        raise MissingTranslationError(f"{field_name} is not a multilingual mapping.")

    lang_map = _ensure_mapping(value, field_name)

    if site_config is not None:
        active_registry = registry or build_language_registry(site_config)
        chain = build_fallback_chain(
            site_config,
            lang,
            fallback_langs,
            include_default=include_default_fallback,
            registry=active_registry,
        )
    else:
        chain = _dedupe_preserve_order([lang, *(fallback_langs or [])])

    for code in chain:
        if code not in lang_map:
            continue

        candidate = lang_map[code]

        if candidate is None:
            continue
        if isinstance(candidate, str) and not candidate.strip():
            continue

        return candidate

    tried = ", ".join(chain)
    raise MissingTranslationError(
        f"Missing translation for {field_name}. Requested/fallback languages tried: {tried}"
    )


def translate_string(
    value: Any,
    lang: str,
    *,
    site_config: Optional[Mapping[str, Any]] = None,
    fallback_langs: Optional[Sequence[str]] = None,
    allow_literal: bool = True,
    include_default_fallback: bool = True,
    field_name: str = "value",
    allow_empty: bool = False,
    registry: Optional[Mapping[str, Any]] = None,
) -> str:
    resolved = translate(
        value,
        lang,
        site_config=site_config,
        fallback_langs=fallback_langs,
        allow_literal=allow_literal,
        include_default_fallback=include_default_fallback,
        field_name=field_name,
        registry=registry,
    )
    return _ensure_string(resolved, field_name, allow_empty=allow_empty)


def translate_list(
    value: Any,
    lang: str,
    *,
    site_config: Optional[Mapping[str, Any]] = None,
    fallback_langs: Optional[Sequence[str]] = None,
    allow_literal: bool = True,
    include_default_fallback: bool = True,
    field_name: str = "value",
    registry: Optional[Mapping[str, Any]] = None,
) -> List[Any]:
    resolved = translate(
        value,
        lang,
        site_config=site_config,
        fallback_langs=fallback_langs,
        allow_literal=allow_literal,
        include_default_fallback=include_default_fallback,
        field_name=field_name,
        registry=registry,
    )
    return _ensure_list(resolved, field_name)


def translate_from_path(
    root: Mapping[str, Any],
    path: Sequence[str],
    lang: str,
    *,
    site_config: Optional[Mapping[str, Any]] = None,
    fallback_langs: Optional[Sequence[str]] = None,
    allow_literal: bool = False,
    include_default_fallback: bool = True,
    field_name: Optional[str] = None,
    registry: Optional[Mapping[str, Any]] = None,
) -> Any:
    current: Any = root
    for key in path:
        mapping = _ensure_mapping(current, field_name or ".".join(path))
        if key not in mapping:
            raise MissingTranslationError(f"Missing key in path: {'.'.join(path)}")
        current = mapping[key]

    return translate(
        current,
        lang,
        site_config=site_config,
        fallback_langs=fallback_langs,
        allow_literal=allow_literal,
        include_default_fallback=include_default_fallback,
        field_name=field_name or ".".join(path),
        registry=registry,
    )


# ============================================================================
# URL / route building
# ============================================================================

def build_absolute_url(site_config: Mapping[str, Any], path_or_url: str) -> str:
    """
    Normalize a root-relative path or validate an absolute HTTPS URL.
    """
    value = _ensure_string(path_or_url, "path_or_url")
    if _is_absolute_https_url(value):
        return value

    if not value.startswith("/"):
        raise RouteFormatError(
            "Expected a root-relative path starting with '/' or an absolute HTTPS URL."
        )

    site = _ensure_mapping(_get_site_mapping(site_config).get("site"), "site_config.site")
    base_url = _ensure_string(site.get("base_url"), "site_config.site.base_url")

    if not _is_absolute_https_url(base_url):
        raise RouteFormatError("site_config.site.base_url must be an absolute HTTPS URL.")

    return f"{base_url.rstrip('/')}{value}"


def _extract_format_fields(template: str) -> List[str]:
    fields: List[str] = []
    for _, field_name, _, _ in Formatter().parse(template):
        if field_name:
            fields.append(field_name)
    return fields


def format_route_template(
    template: str,
    *,
    params: Mapping[str, Any],
) -> str:
    """
    Safely format a route template with URL-encoded values.

    Rules:
    - all required fields must be present
    - no extra fields are allowed
    - placeholder values are encoded as route-safe segments
    """
    route_template = _ensure_string(template, "route template")
    param_map = _ensure_mapping(params, "route params")

    fields = _extract_format_fields(route_template)
    field_set = set(fields)
    param_set = set(param_map.keys())

    missing = sorted(field_set - param_set)
    if missing:
        raise RouteFormatError(
            f"Missing route parameter(s) for template '{route_template}': {', '.join(missing)}"
        )

    extra = sorted(param_set - field_set)
    if extra:
        raise RouteFormatError(
            f"Unexpected route parameter(s) for template '{route_template}': {', '.join(extra)}"
        )

    safe_params: Dict[str, str] = {}
    for key in fields:
        raw_value = param_map[key]
        if raw_value is None:
            raise RouteFormatError(f"Route parameter '{key}' must not be None.")
        raw_text = str(raw_value).strip()
        if not raw_text:
            raise RouteFormatError(f"Route parameter '{key}' must not be empty.")
        safe_params[key] = quote(raw_text, safe="-._~")

    try:
        rendered = route_template.format(**safe_params)
    except KeyError as exc:
        raise RouteFormatError(f"Missing route parameter during format: {exc}") from exc
    except Exception as exc:
        raise RouteFormatError(f"Failed to format route template '{route_template}': {exc}") from exc

    if not rendered.startswith("/"):
        raise RouteFormatError("Formatted route must start with '/'.")

    return rendered


def build_route(
    site_config: Mapping[str, Any],
    route_key: str,
    lang: str,
    *,
    absolute: bool = False,
    registry: Optional[Mapping[str, Any]] = None,
    **params: Any,
) -> str:
    """
    Build a localized route from site_config.routes[route_key].
    """
    active_registry = registry or build_language_registry(site_config)
    require_supported_language(site_config, lang, registry=active_registry)

    routes = _ensure_mapping(_get_site_mapping(site_config).get("routes"), "site_config.routes")
    if route_key not in routes:
        raise RouteFormatError(f"Unknown route key: {route_key}")

    template = _ensure_string(routes[route_key], f"site_config.routes.{route_key}")
    rendered = format_route_template(template, params={"lang": lang, **params})

    if absolute:
        return build_absolute_url(site_config, rendered)
    return rendered


def build_tool_route(
    site_config: Mapping[str, Any],
    tool_config: Mapping[str, Any],
    lang: str,
    *,
    absolute: bool = False,
    registry: Optional[Mapping[str, Any]] = None,
) -> str:
    """
    Build a localized route using tool.routing.path_template.
    """
    active_registry = registry or build_language_registry(site_config)
    require_supported_language(site_config, lang, registry=active_registry)

    tool = _ensure_mapping(tool_config, "tool_config")
    routing = _ensure_mapping(tool.get("routing"), "tool_config.routing")
    template = _ensure_string(routing.get("path_template"), "tool_config.routing.path_template")

    rendered = format_route_template(template, params={"lang": lang})

    if absolute:
        return build_absolute_url(site_config, rendered)
    return rendered


# ============================================================================
# hreflang / language switcher
# ============================================================================

def build_hreflang_map(
    site_config: Mapping[str, Any],
    urls_by_lang: Mapping[str, str],
    *,
    include_x_default: Optional[bool] = None,
    registry: Optional[Mapping[str, Any]] = None,
) -> Dict[str, str]:
    """
    Build a validated hreflang map.

    Requirements:
    - urls_by_lang must include every enabled language
    - urls_by_lang must not include unknown extra languages
    - each URL must be root-relative or absolute HTTPS
    - hreflang values must already be unique in the registry
    """
    active_registry = registry or build_language_registry(site_config)
    enabled_languages = get_enabled_languages(site_config, registry=active_registry)
    enabled_codes = set(get_enabled_language_codes(site_config, registry=active_registry))

    incoming = _ensure_mapping(urls_by_lang, "urls_by_lang")
    incoming_codes = set(incoming.keys())

    missing = sorted(enabled_codes - incoming_codes)
    if missing:
        raise I18nError(f"urls_by_lang is missing enabled language(s): {', '.join(missing)}")

    extra = sorted(incoming_codes - enabled_codes)
    if extra:
        raise I18nError(f"urls_by_lang contains unsupported language(s): {', '.join(extra)}")

    normalized: Dict[str, str] = {}
    for code in sorted(enabled_codes):
        normalized[code] = build_absolute_url(
            site_config,
            _ensure_string(incoming[code], f"urls_by_lang.{code}"),
        )

    seo = _ensure_mapping(_get_site_mapping(site_config).get("seo"), "site_config.seo")
    hreflang_cfg = _ensure_mapping(seo.get("hreflang"), "site_config.seo.hreflang")

    use_x_default = include_x_default
    if use_x_default is None:
        raw_flag = hreflang_cfg.get("include_x_default")
        if not isinstance(raw_flag, bool):
            raise I18nError("site_config.seo.hreflang.include_x_default must be a boolean.")
        use_x_default = raw_flag

    result: Dict[str, str] = {}
    for lang_item in enabled_languages:
        hreflang_code = _ensure_string(
            lang_item.get("hreflang"),
            f"language[{lang_item['code']}].hreflang",
        )
        if hreflang_code in result:
            raise I18nError(f"Duplicate hreflang encountered during map build: {hreflang_code}")
        result[hreflang_code] = normalized[lang_item["code"]]

    if use_x_default:
        x_default_lang = get_default_language(site_config, registry=active_registry)
        result["x-default"] = normalized[x_default_lang]

    return result


def build_language_switcher(
    site_config: Mapping[str, Any],
    current_lang: str,
    urls_by_lang: Mapping[str, str],
    *,
    registry: Optional[Mapping[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Build normalized language switcher entries for templates.
    """
    active_registry = registry or build_language_registry(site_config)
    require_supported_language(site_config, current_lang, registry=active_registry)

    incoming = _ensure_mapping(urls_by_lang, "urls_by_lang")
    enabled_languages = get_enabled_languages(site_config, registry=active_registry)
    enabled_codes = set(get_enabled_language_codes(site_config, registry=active_registry))
    incoming_codes = set(incoming.keys())

    missing = sorted(enabled_codes - incoming_codes)
    if missing:
        raise I18nError(
            f"urls_by_lang is missing enabled language(s) for switcher: {', '.join(missing)}"
        )

    extra = sorted(incoming_codes - enabled_codes)
    if extra:
        raise I18nError(
            f"urls_by_lang contains unsupported language(s) for switcher: {', '.join(extra)}"
        )

    entries: List[Dict[str, Any]] = []
    for lang_item in enabled_languages:
        code = lang_item["code"]
        direction = _ensure_string(lang_item.get("dir"), f"language[{code}].dir")
        if direction not in {"ltr", "rtl"}:
            raise I18nError(f"Invalid dir value for language '{code}': {direction}")

        entries.append(
            {
                "code": code,
                "label": _ensure_string(lang_item.get("label"), f"language[{code}].label"),
                "native_name": _ensure_string(lang_item.get("native_name"), f"language[{code}].native_name"),
                "dir": direction,
                "url": build_absolute_url(
                    site_config,
                    _ensure_string(incoming[code], f"urls_by_lang.{code}"),
                ),
                "is_current": code == current_lang,
            }
        )

    return entries


# ============================================================================
# Common template context
# ============================================================================

def build_language_meta(
    site_config: Mapping[str, Any],
    lang: str,
    *,
    registry: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build minimal language context for templates and generators.
    """
    active_registry = registry or build_language_registry(site_config)
    lang_conf = get_language_config(site_config, lang, registry=active_registry)
    direction = _ensure_string(lang_conf.get("dir"), f"language[{lang}].dir")
    if direction not in {"ltr", "rtl"}:
        raise I18nError(f"Invalid direction for language '{lang}': {direction}")

    return {
        "lang": lang,
        "locale": _ensure_string(lang_conf.get("locale"), f"language[{lang}].locale"),
        "dir": direction,
        "is_rtl": direction == "rtl",
        "default_lang": get_default_language(site_config, registry=active_registry),
    }
