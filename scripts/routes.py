#!/usr/bin/env python3
"""
TourVsTravel — Central Route System
==================================

Purpose:
- Centralize all public path and URL construction
- Eliminate route logic drift across generators
- Provide canonical, sitemap-ready, multilingual-safe routes
- Enforce strict path-template behavior

Design principles:
- one routing layer for the whole project
- fail closed, not fail open
- no generator should handcraft public URLs
- absolute URLs must always be HTTPS and canonical
- generated route keys are immutable and cannot be overridden by site_config
- sitemap entries are always validated before insertion
- comparison pairs: both A-vs-B and B-vs-A are generated (distinct SEO intent)
- reserved structural substrings are blocked at the routing layer as defense-in-depth
"""

from __future__ import annotations

from typing import (
    Any,
    Callable,
    Dict,
    FrozenSet,
    List,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
    TypedDict,
)
from urllib.parse import urlparse

from scripts.i18n import (
    I18nError,
    RouteFormatError,
    build_absolute_url,
    build_language_registry,
    build_tool_route,
    format_route_template,
    get_enabled_language_codes,
    require_supported_language,
    translate_string,
)


# ============================================================================
# Exports
# ============================================================================

__all__ = [
    # Exceptions
    "RoutesError",
    "RouteDefinitionError",
    "SitemapBuildError",
    # Constants
    "SYSTEM_ROUTE_TEMPLATES",
    "STATIC_ROUTE_KEYS",
    "GENERATED_ROUTE_KEYS",
    "SLUG_RESERVED_SUBSTRINGS",
    # Core builders
    "get_route_template",
    "resolve_route_segment",
    "build_path_from_template",
    "build_absolute_route",
    # Static route builders
    "build_home_path",
    "build_compare_index_path",
    "build_destinations_index_path",
    "build_tools_index_path",
    "build_methodology_path",
    "build_acquire_path",
    # Generated route builders
    "build_destination_path",
    "build_experience_type_path",
    "build_report_path",
    "build_comparison_path",
    "build_tool_path",
    "build_tool_path_by_id",
    # URL maps
    "build_language_url_map",
    "build_static_language_url_map",
    "build_destination_language_url_map",
    "build_experience_type_language_url_map",
    "build_comparison_language_url_map",
    "build_tool_language_url_map",
    # Sitemap
    "SitemapEntry",
    "build_comparison_pairs",
    "build_static_sitemap_entries",
    "build_tool_sitemap_entries",
    "build_destination_sitemap_entries",
    "build_experience_type_sitemap_entries",
    "build_comparison_sitemap_entries",
]


# ============================================================================
# Exceptions
# ============================================================================

class RoutesError(Exception):
    """Base routes exception."""


class RouteDefinitionError(RoutesError):
    """Raised when a route template or key is invalid."""


class SitemapBuildError(RoutesError):
    """Raised when sitemap entry generation fails."""


# ============================================================================
# Canonical system route templates
# ============================================================================

SYSTEM_ROUTE_TEMPLATES: Dict[str, str] = {
    # Static / index-like routes (overridable via site_config.routes)
    "home": "/{lang}/",
    "compare": "/{lang}/compare/",
    "destinations": "/{lang}/destinations/",
    "tools": "/{lang}/tools/",
    "methodology": "/{lang}/methodology/",
    "acquire": "/{lang}/acquire/",

    # Generated page families (immutable — cannot be overridden by site_config)
    "destination": "/{lang}/destinations/{destination_id}/",
    "experience_type": "/{lang}/styles/{experience_slug}/",
    "comparison": "/{lang}/{destination_id}/{exp_a_slug}--vs--{exp_b_slug}/",
    "report": "/{lang}/reports/{report_slug}/",
}

STATIC_ROUTE_KEYS: FrozenSet[str] = frozenset({
    "home",
    "compare",
    "destinations",
    "tools",
    "methodology",
    "acquire",
})

GENERATED_ROUTE_KEYS: FrozenSet[str] = frozenset({
    "destination",
    "experience_type",
    "comparison",
    "report",
})


# ============================================================================
# Constitutional slug constraints
# ============================================================================

SLUG_RESERVED_SUBSTRINGS: FrozenSet[str] = frozenset({
    "--vs--",
})


# ============================================================================
# Typed output
# ============================================================================

class SitemapEntry(TypedDict):
    """A single validated sitemap entry."""
    url: str
    lang: str
    kind: str
    identifier: str


# ============================================================================
# Internal helpers
# ============================================================================

def _ensure_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RoutesError(f"{label} must be a mapping/object.")
    return value


def _ensure_string(value: Any, label: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise RoutesError(f"{label} must be a string.")
    if not allow_empty and not value.strip():
        raise RoutesError(f"{label} must not be empty.")
    return value


def _ensure_list(value: Any, label: str) -> List[Any]:
    if not isinstance(value, list):
        raise RoutesError(f"{label} must be a list.")
    return value


def _is_absolute_https_url(value: str) -> bool:
    """
    Validate that a string is an absolute HTTPS URL with no credentials.
    """
    try:
        parsed = urlparse(value)
        return (
            parsed.scheme == "https"
            and bool(parsed.netloc)
            and parsed.username is None
            and parsed.password is None
        )
    except Exception:
        return False


def _require_absolute_https_url(value: str, label: str) -> str:
    if not _is_absolute_https_url(value):
        raise RouteDefinitionError(
            f"{label} must be an absolute HTTPS URL (no credentials). Got: {value!r}"
        )
    return value


def _validate_path_segment(
    value: str,
    label: str,
    *,
    check_reserved_substrings: bool = False,
) -> str:
    """
    Defense-in-depth validation for any public path segment.

    Rejects:
    - empty strings
    - path separators
    - traversal-like substrings
    - reserved structural substrings when enabled
    """
    segment = _ensure_string(value, label)

    if "/" in segment or "\\" in segment:
        raise RouteDefinitionError(
            f"{label} must be a single path segment and must not contain '/' or '\\\\'. Got: {segment!r}"
        )

    if ".." in segment:
        raise RouteDefinitionError(
            f"{label} must not contain '..'. Got: {segment!r}"
        )

    if check_reserved_substrings:
        for forbidden in SLUG_RESERVED_SUBSTRINGS:
            if forbidden in segment:
                raise RouteDefinitionError(
                    f"{label} contains reserved substring {forbidden!r}: {segment!r}"
                )

    return segment


def _get_site_routes(site_config: Mapping[str, Any]) -> Mapping[str, Any]:
    """
    Return site_config.routes if present, or an empty mapping.

    Raises RoutesError if the key exists but is not a mapping.
    """
    site = _ensure_mapping(site_config, "site_config")
    routes = site.get("routes")
    if routes is None:
        return {}
    return _ensure_mapping(routes, "site_config.routes")


def _build_tools_index_by_id(tools_config: Mapping[str, Any]) -> Dict[str, Mapping[str, Any]]:
    """
    Build a strict tools_by_id index from tools_config.tools if a prebuilt index
    is not available.

    This prevents a hidden dependency on loader-added fields.
    """
    config = _ensure_mapping(tools_config, "tools_config")

    prebuilt = config.get("tools_by_id")
    if prebuilt is not None:
        index = _ensure_mapping(prebuilt, "tools_config.tools_by_id")
        return {
            _ensure_string(tool_id, "tools_config.tools_by_id key"): _ensure_mapping(tool, f"tools_by_id[{tool_id}]")
            for tool_id, tool in index.items()
        }

    raw_tools = _ensure_list(config.get("tools"), "tools_config.tools")
    output: Dict[str, Mapping[str, Any]] = {}

    for idx, tool in enumerate(raw_tools):
        tool_mapping = _ensure_mapping(tool, f"tools[{idx}]")
        tool_id = _ensure_string(tool_mapping.get("id"), f"tools[{idx}].id")
        if tool_id in output:
            raise RouteDefinitionError(f"Duplicate tool id while building tools index: {tool_id!r}")
        output[tool_id] = tool_mapping

    return output


def _get_active_public_tools(tools_config: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    """
    Return active public tools from:
    - prebuilt tools_config.active_public_tools if present
    - otherwise derive them from tools_config.tools

    This removes the hidden dependency on loader normalization while keeping
    behavior deterministic.
    """
    config = _ensure_mapping(tools_config, "tools_config")

    prebuilt = config.get("active_public_tools")
    if prebuilt is not None:
        raw = _ensure_list(prebuilt, "tools_config.active_public_tools")
        return [_ensure_mapping(tool, f"active_public_tools[{idx}]") for idx, tool in enumerate(raw)]

    raw_tools = _ensure_list(config.get("tools"), "tools_config.tools")
    output: List[Mapping[str, Any]] = []

    for idx, tool in enumerate(raw_tools):
        tool_mapping = _ensure_mapping(tool, f"tools[{idx}]")
        publication = _ensure_mapping(tool_mapping.get("publication"), f"tools[{idx}].publication")

        status = _ensure_string(publication.get("status"), f"tools[{idx}].publication.status")
        build_visibility = _ensure_string(
            publication.get("build_visibility"),
            f"tools[{idx}].publication.build_visibility",
        )

        if status == "active" and build_visibility == "public":
            output.append(tool_mapping)

    return output


def _build_experience_slug_cache(
    site_config: Mapping[str, Any],
    experience_types: Sequence[Mapping[str, Any]],
    *,
    slug_field: str,
    registry: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Dict[str, str]]:
    """
    Pre-resolve multilingual slugs for experience types once per build phase.

    Returns:
        {
            "<experience_id>": {
                "en": "guided-group-tour",
                "ar": "...",
                ...
            },
            ...
        }
    """
    active_registry = registry or build_language_registry(site_config)
    lang_codes = get_enabled_language_codes(site_config, registry=active_registry)

    cache: Dict[str, Dict[str, str]] = {}

    for idx, experience in enumerate(experience_types):
        item = _ensure_mapping(experience, f"experience_types[{idx}]")
        exp_id = _ensure_string(item.get("id"), f"experience_types[{idx}].id")

        if slug_field not in item:
            raise SitemapBuildError(
                f"experience_types[{idx}] is missing required slug field {slug_field!r}."
            )

        if exp_id in cache:
            raise SitemapBuildError(f"Duplicate experience id while building slug cache: {exp_id!r}")

        cache[exp_id] = {}

        for lang in lang_codes:
            resolved = resolve_route_segment(
                item[slug_field],
                lang,
                site_config,
                field_name=f"experience_types[{idx}].{slug_field}",
                registry=active_registry,
            )
            cache[exp_id][lang] = _validate_path_segment(
                resolved,
                f"experience_types[{idx}].{slug_field}[{lang}]",
                check_reserved_substrings=True,
            )

    return cache


# ============================================================================
# Core route resolution
# ============================================================================

def get_route_template(
    site_config: Mapping[str, Any],
    route_key: str,
) -> str:
    """
    Resolve the authoritative template for a route key.

    STATIC routes:
      1) site_config.routes[route_key] if present and valid
      2) SYSTEM_ROUTE_TEMPLATES[route_key]

    GENERATED routes:
      - immutable
      - any override attempt in site_config.routes is a hard error
    """
    key = _ensure_string(route_key, "route_key")
    site_routes = _get_site_routes(site_config)

    if key in GENERATED_ROUTE_KEYS:
        if key in site_routes:
            raise RouteDefinitionError(
                f"Generated route key {key!r} must not be overridden in site_config.routes. "
                f"Remove routes.{key} from site_config."
            )
        return SYSTEM_ROUTE_TEMPLATES[key]

    if key in site_routes:
        return _ensure_string(site_routes[key], f"site_config.routes.{key}")

    if key in SYSTEM_ROUTE_TEMPLATES:
        return SYSTEM_ROUTE_TEMPLATES[key]

    raise RouteDefinitionError(f"Unknown route key: {key!r}")


def resolve_route_segment(
    value: Any,
    lang: str,
    site_config: Mapping[str, Any],
    *,
    field_name: str = "route_segment",
    registry: Optional[Mapping[str, Any]] = None,
) -> str:
    """
    Resolve a route segment from either:
    - a plain string
    - a multilingual mapping
    """
    if isinstance(value, Mapping):
        return translate_string(
            value,
            lang,
            site_config=site_config,
            field_name=field_name,
            registry=registry,
        )
    return _ensure_string(value, field_name)


def build_path_from_template(
    site_config: Mapping[str, Any],
    route_key: str,
    lang: str,
    *,
    registry: Optional[Mapping[str, Any]] = None,
    **params: Any,
) -> str:
    """
    Build a relative path from a route key + params.
    """
    active_registry = registry or build_language_registry(site_config)
    require_supported_language(site_config, lang, registry=active_registry)

    template = get_route_template(site_config, route_key)
    try:
        return format_route_template(template, params={"lang": lang, **params})
    except RouteFormatError as exc:
        raise RouteDefinitionError(
            f"Failed to build path for route {route_key!r} in language {lang!r}: {exc}"
        ) from exc


def build_absolute_route(
    site_config: Mapping[str, Any],
    route_key: str,
    lang: str,
    *,
    registry: Optional[Mapping[str, Any]] = None,
    **params: Any,
) -> str:
    """
    Build a canonical absolute HTTPS URL from a route key + params.
    """
    path = build_path_from_template(
        site_config,
        route_key,
        lang,
        registry=registry,
        **params,
    )
    return build_absolute_url(site_config, path)


# ============================================================================
# Static / index routes
# ============================================================================

def build_home_path(
    site_config: Mapping[str, Any],
    lang: str,
    *,
    absolute: bool = False,
    registry: Optional[Mapping[str, Any]] = None,
) -> str:
    if absolute:
        return build_absolute_route(site_config, "home", lang, registry=registry)
    return build_path_from_template(site_config, "home", lang, registry=registry)


def build_compare_index_path(
    site_config: Mapping[str, Any],
    lang: str,
    *,
    absolute: bool = False,
    registry: Optional[Mapping[str, Any]] = None,
) -> str:
    if absolute:
        return build_absolute_route(site_config, "compare", lang, registry=registry)
    return build_path_from_template(site_config, "compare", lang, registry=registry)


def build_destinations_index_path(
    site_config: Mapping[str, Any],
    lang: str,
    *,
    absolute: bool = False,
    registry: Optional[Mapping[str, Any]] = None,
) -> str:
    if absolute:
        return build_absolute_route(site_config, "destinations", lang, registry=registry)
    return build_path_from_template(site_config, "destinations", lang, registry=registry)


def build_tools_index_path(
    site_config: Mapping[str, Any],
    lang: str,
    *,
    absolute: bool = False,
    registry: Optional[Mapping[str, Any]] = None,
) -> str:
    if absolute:
        return build_absolute_route(site_config, "tools", lang, registry=registry)
    return build_path_from_template(site_config, "tools", lang, registry=registry)


def build_methodology_path(
    site_config: Mapping[str, Any],
    lang: str,
    *,
    absolute: bool = False,
    registry: Optional[Mapping[str, Any]] = None,
) -> str:
    if absolute:
        return build_absolute_route(site_config, "methodology", lang, registry=registry)
    return build_path_from_template(site_config, "methodology", lang, registry=registry)


def build_acquire_path(
    site_config: Mapping[str, Any],
    lang: str,
    *,
    absolute: bool = False,
    registry: Optional[Mapping[str, Any]] = None,
) -> str:
    if absolute:
        return build_absolute_route(site_config, "acquire", lang, registry=registry)
    return build_path_from_template(site_config, "acquire", lang, registry=registry)


# ============================================================================
# Generated content routes
# ============================================================================

def build_destination_path(
    site_config: Mapping[str, Any],
    lang: str,
    destination_id: str,
    *,
    absolute: bool = False,
    registry: Optional[Mapping[str, Any]] = None,
) -> str:
    destination_key = _validate_path_segment(
        destination_id,
        "destination_id",
        check_reserved_substrings=True,
    )

    if absolute:
        return build_absolute_route(
            site_config,
            "destination",
            lang,
            registry=registry,
            destination_id=destination_key,
        )

    return build_path_from_template(
        site_config,
        "destination",
        lang,
        registry=registry,
        destination_id=destination_key,
    )


def build_experience_type_path(
    site_config: Mapping[str, Any],
    lang: str,
    experience_slug: str,
    *,
    absolute: bool = False,
    registry: Optional[Mapping[str, Any]] = None,
) -> str:
    slug = _validate_path_segment(
        experience_slug,
        "experience_slug",
        check_reserved_substrings=True,
    )

    if absolute:
        return build_absolute_route(
            site_config,
            "experience_type",
            lang,
            registry=registry,
            experience_slug=slug,
        )

    return build_path_from_template(
        site_config,
        "experience_type",
        lang,
        registry=registry,
        experience_slug=slug,
    )


def build_report_path(
    site_config: Mapping[str, Any],
    lang: str,
    report_slug: str,
    *,
    absolute: bool = False,
    registry: Optional[Mapping[str, Any]] = None,
) -> str:
    slug = _validate_path_segment(
        report_slug,
        "report_slug",
        check_reserved_substrings=True,
    )

    if absolute:
        return build_absolute_route(
            site_config,
            "report",
            lang,
            registry=registry,
            report_slug=slug,
        )

    return build_path_from_template(
        site_config,
        "report",
        lang,
        registry=registry,
        report_slug=slug,
    )


def build_comparison_path(
    site_config: Mapping[str, Any],
    lang: str,
    destination_id: str,
    exp_a_slug: str,
    exp_b_slug: str,
    *,
    absolute: bool = False,
    registry: Optional[Mapping[str, Any]] = None,
) -> str:
    """
    Build a directional comparison path.

    Product intent:
    - A-vs-B and B-vs-A are distinct public URLs and distinct pages.
    - Callers must preserve semantic order.
    """
    destination_key = _validate_path_segment(
        destination_id,
        "destination_id",
        check_reserved_substrings=True,
    )
    left_slug = _validate_path_segment(
        exp_a_slug,
        "exp_a_slug",
        check_reserved_substrings=True,
    )
    right_slug = _validate_path_segment(
        exp_b_slug,
        "exp_b_slug",
        check_reserved_substrings=True,
    )

    if absolute:
        return build_absolute_route(
            site_config,
            "comparison",
            lang,
            registry=registry,
            destination_id=destination_key,
            exp_a_slug=left_slug,
            exp_b_slug=right_slug,
        )

    return build_path_from_template(
        site_config,
        "comparison",
        lang,
        registry=registry,
        destination_id=destination_key,
        exp_a_slug=left_slug,
        exp_b_slug=right_slug,
    )


def build_tool_path(
    site_config: Mapping[str, Any],
    tool_config: Mapping[str, Any],
    lang: str,
    *,
    absolute: bool = False,
    registry: Optional[Mapping[str, Any]] = None,
) -> str:
    try:
        return build_tool_route(
            site_config,
            tool_config,
            lang,
            absolute=absolute,
            registry=registry,
        )
    except (I18nError, RouteFormatError) as exc:
        raise RouteDefinitionError(
            f"Failed to build tool route for language {lang!r}: {exc}"
        ) from exc


def build_tool_path_by_id(
    site_config: Mapping[str, Any],
    tools_config: Mapping[str, Any],
    tool_id: str,
    lang: str,
    *,
    absolute: bool = False,
    registry: Optional[Mapping[str, Any]] = None,
) -> str:
    """
    Build a localized path for a tool identified by its string ID.

    Works with:
    - normalized tools_config including tools_by_id
    - raw tools_config containing only tools
    """
    index = _build_tools_index_by_id(tools_config)
    key = _ensure_string(tool_id, "tool_id")

    if key not in index:
        raise RouteDefinitionError(f"Unknown tool id: {key!r}")

    return build_tool_path(
        site_config,
        index[key],
        lang,
        absolute=absolute,
        registry=registry,
    )


# ============================================================================
# Canonical / alternate URL maps
# ============================================================================

def build_language_url_map(
    site_config: Mapping[str, Any],
    relative_path_builder: Callable[[str], str],
    *,
    registry: Optional[Mapping[str, Any]] = None,
) -> Dict[str, str]:
    """
    Build a map of {lang_code: absolute_url} using a callable that returns
    a relative path for each language code.
    """
    active_registry = registry or build_language_registry(site_config)
    urls: Dict[str, str] = {}

    for code in get_enabled_language_codes(site_config, registry=active_registry):
        relative_path = _ensure_string(
            relative_path_builder(code),
            f"relative_path_builder({code!r})",
        )
        urls[code] = build_absolute_url(site_config, relative_path)

    return urls


def build_static_language_url_map(
    site_config: Mapping[str, Any],
    route_key: str,
    *,
    registry: Optional[Mapping[str, Any]] = None,
) -> Dict[str, str]:
    key = _ensure_string(route_key, "route_key")
    if key not in STATIC_ROUTE_KEYS:
        raise RouteDefinitionError(f"Route key {key!r} is not a static route key.")

    active_registry = registry or build_language_registry(site_config)
    return build_language_url_map(
        site_config,
        lambda lang: build_path_from_template(site_config, key, lang, registry=active_registry),
        registry=active_registry,
    )


def build_destination_language_url_map(
    site_config: Mapping[str, Any],
    destination_id: str,
    *,
    registry: Optional[Mapping[str, Any]] = None,
) -> Dict[str, str]:
    active_registry = registry or build_language_registry(site_config)
    return build_language_url_map(
        site_config,
        lambda lang: build_destination_path(
            site_config,
            lang,
            destination_id,
            absolute=False,
            registry=active_registry,
        ),
        registry=active_registry,
    )


def build_experience_type_language_url_map(
    site_config: Mapping[str, Any],
    slug_by_lang: Mapping[str, str],
    *,
    registry: Optional[Mapping[str, Any]] = None,
) -> Dict[str, str]:
    slug_map = _ensure_mapping(slug_by_lang, "slug_by_lang")
    active_registry = registry or build_language_registry(site_config)

    return build_language_url_map(
        site_config,
        lambda lang: build_experience_type_path(
            site_config,
            lang,
            _ensure_string(slug_map.get(lang), f"slug_by_lang.{lang}"),
            absolute=False,
            registry=active_registry,
        ),
        registry=active_registry,
    )


def build_comparison_language_url_map(
    site_config: Mapping[str, Any],
    destination_id: str,
    exp_a_slug_by_lang: Mapping[str, str],
    exp_b_slug_by_lang: Mapping[str, str],
    *,
    registry: Optional[Mapping[str, Any]] = None,
) -> Dict[str, str]:
    left_map = _ensure_mapping(exp_a_slug_by_lang, "exp_a_slug_by_lang")
    right_map = _ensure_mapping(exp_b_slug_by_lang, "exp_b_slug_by_lang")
    active_registry = registry or build_language_registry(site_config)

    return build_language_url_map(
        site_config,
        lambda lang: build_comparison_path(
            site_config,
            lang,
            destination_id,
            _ensure_string(left_map.get(lang), f"exp_a_slug_by_lang.{lang}"),
            _ensure_string(right_map.get(lang), f"exp_b_slug_by_lang.{lang}"),
            absolute=False,
            registry=active_registry,
        ),
        registry=active_registry,
    )


def build_tool_language_url_map(
    site_config: Mapping[str, Any],
    tool_config: Mapping[str, Any],
    *,
    registry: Optional[Mapping[str, Any]] = None,
) -> Dict[str, str]:
    active_registry = registry or build_language_registry(site_config)

    return build_language_url_map(
        site_config,
        lambda lang: build_tool_path(
            site_config,
            tool_config,
            lang,
            absolute=False,
            registry=active_registry,
        ),
        registry=active_registry,
    )


# ============================================================================
# Sitemap entry builders
# ============================================================================

def _make_sitemap_entry(
    url: str,
    lang: str,
    kind: str,
    identifier: str,
) -> SitemapEntry:
    """
    Build a validated sitemap entry.
    """
    try:
        validated_url = _require_absolute_https_url(url, "sitemap_entry.url")
    except RouteDefinitionError as exc:
        raise SitemapBuildError(str(exc)) from exc

    return SitemapEntry(
        url=validated_url,
        lang=_ensure_string(lang, "sitemap_entry.lang"),
        kind=_ensure_string(kind, "sitemap_entry.kind"),
        identifier=_ensure_string(identifier, "sitemap_entry.identifier"),
    )


def build_static_sitemap_entries(
    site_config: Mapping[str, Any],
    route_keys: Sequence[str],
    *,
    registry: Optional[Mapping[str, Any]] = None,
) -> List[SitemapEntry]:
    """
    Build sitemap-ready entries for a set of static/index route keys.
    """
    keys = [_ensure_string(key, "route_keys[]") for key in route_keys]

    invalid = [k for k in keys if k not in STATIC_ROUTE_KEYS]
    if invalid:
        raise SitemapBuildError(
            f"Invalid static route key(s): {', '.join(sorted(invalid))}. "
            f"Valid keys: {', '.join(sorted(STATIC_ROUTE_KEYS))}"
        )

    active_registry = registry or build_language_registry(site_config)
    entries: List[SitemapEntry] = []

    for key in keys:
        for lang in get_enabled_language_codes(site_config, registry=active_registry):
            url = build_absolute_route(site_config, key, lang, registry=active_registry)
            entries.append(_make_sitemap_entry(url, lang, "static", key))

    return entries


def build_tool_sitemap_entries(
    site_config: Mapping[str, Any],
    tools_config: Mapping[str, Any],
    *,
    registry: Optional[Mapping[str, Any]] = None,
    public_only: bool = True,
) -> List[SitemapEntry]:
    """
    Build sitemap-ready entries for tools.

    Works with:
    - normalized tools_config containing active_public_tools
    - raw tools_config containing only tools
    """
    active_registry = registry or build_language_registry(site_config)

    if public_only:
        tools = _get_active_public_tools(tools_config)
    else:
        config = _ensure_mapping(tools_config, "tools_config")
        raw_tools = _ensure_list(config.get("tools"), "tools_config.tools")
        tools = [_ensure_mapping(tool, f"tools[{idx}]") for idx, tool in enumerate(raw_tools)]

    entries: List[SitemapEntry] = []

    for idx, tool in enumerate(tools):
        tool_mapping = _ensure_mapping(tool, f"tools[{idx}]")
        tool_id = _ensure_string(tool_mapping.get("id"), f"tools[{idx}].id")

        for lang in get_enabled_language_codes(site_config, registry=active_registry):
            url = build_tool_path(
                site_config,
                tool_mapping,
                lang,
                absolute=True,
                registry=active_registry,
            )
            entries.append(_make_sitemap_entry(url, lang, "tool", tool_id))

    return entries


def build_destination_sitemap_entries(
    site_config: Mapping[str, Any],
    destinations: Sequence[Mapping[str, Any]],
    *,
    registry: Optional[Mapping[str, Any]] = None,
) -> List[SitemapEntry]:
    """
    Build sitemap-ready entries for all destinations across all languages.
    """
    active_registry = registry or build_language_registry(site_config)
    entries: List[SitemapEntry] = []
    seen_destination_ids: Set[str] = set()

    for idx, destination in enumerate(destinations):
        item = _ensure_mapping(destination, f"destinations[{idx}]")
        destination_id = _validate_path_segment(
            _ensure_string(item.get("id"), f"destinations[{idx}].id"),
            f"destinations[{idx}].id",
            check_reserved_substrings=True,
        )

        if destination_id in seen_destination_ids:
            raise SitemapBuildError(f"Duplicate destination id detected: {destination_id!r}")
        seen_destination_ids.add(destination_id)

        for lang in get_enabled_language_codes(site_config, registry=active_registry):
            url = build_destination_path(
                site_config,
                lang,
                destination_id,
                absolute=True,
                registry=active_registry,
            )
            entries.append(_make_sitemap_entry(url, lang, "destination", destination_id))

    return entries


def build_experience_type_sitemap_entries(
    site_config: Mapping[str, Any],
    experience_types: Sequence[Mapping[str, Any]],
    *,
    registry: Optional[Mapping[str, Any]] = None,
    slug_field: str = "slug",
) -> List[SitemapEntry]:
    """
    Build sitemap-ready entries for all experience types across all languages.
    """
    active_registry = registry or build_language_registry(site_config)
    slug_cache = _build_experience_slug_cache(
        site_config,
        experience_types,
        slug_field=slug_field,
        registry=active_registry,
    )
    entries: List[SitemapEntry] = []

    for idx, experience in enumerate(experience_types):
        item = _ensure_mapping(experience, f"experience_types[{idx}]")
        experience_id = _ensure_string(item.get("id"), f"experience_types[{idx}].id")

        for lang in get_enabled_language_codes(site_config, registry=active_registry):
            slug = slug_cache[experience_id][lang]
            url = build_experience_type_path(
                site_config,
                lang,
                slug,
                absolute=True,
                registry=active_registry,
            )
            entries.append(_make_sitemap_entry(url, lang, "experience_type", experience_id))

    return entries


# ============================================================================
# Comparison pair extraction (directional, reusable, testable)
# ============================================================================

def build_comparison_pairs(
    experience_types: Sequence[Mapping[str, Any]],
    *,
    slug_field: str = "slug",
    exclusion_pairs: Optional[Set[Tuple[str, str]]] = None,
) -> List[Tuple[Mapping[str, Any], Mapping[str, Any]]]:
    """
    Extract all ordered comparison pairs from a list of experience types.

    Product design intent:
    - A-vs-B and B-vs-A are TWO distinct pages
    - same-ID pairs are excluded
    - exclusions are directional, not canonicalized
    """
    exclusions: Set[Tuple[str, str]] = exclusion_pairs or set()
    validated: List[Mapping[str, Any]] = []
    seen_ids: Set[str] = set()

    for idx, item in enumerate(experience_types):
        exp = _ensure_mapping(item, f"experience_types[{idx}]")
        exp_id = _ensure_string(exp.get("id"), f"experience_types[{idx}].id")

        if exp_id in seen_ids:
            raise SitemapBuildError(f"Duplicate experience id detected: {exp_id!r}")
        seen_ids.add(exp_id)

        if slug_field not in exp:
            raise SitemapBuildError(
                f"experience_types[{idx}] is missing required slug field {slug_field!r}."
            )

        validated.append(exp)

    pairs: List[Tuple[Mapping[str, Any], Mapping[str, Any]]] = []

    for exp_a in validated:
        exp_a_id = exp_a["id"]

        for exp_b in validated:
            exp_b_id = exp_b["id"]

            if exp_a_id == exp_b_id:
                continue

            if (exp_a_id, exp_b_id) in exclusions:
                continue

            pairs.append((exp_a, exp_b))

    return pairs


def build_comparison_sitemap_entries(
    site_config: Mapping[str, Any],
    destinations: Sequence[Mapping[str, Any]],
    experience_types: Sequence[Mapping[str, Any]],
    *,
    registry: Optional[Mapping[str, Any]] = None,
    slug_field: str = "slug",
    exclusion_pairs: Optional[Set[Tuple[str, str]]] = None,
) -> List[SitemapEntry]:
    """
    Build sitemap-ready entries for every ordered comparison pair.

    Directional design:
    - A-vs-B and B-vs-A are both generated intentionally
    - same-ID pairs are skipped
    - exclusions are directional
    """
    active_registry = registry or build_language_registry(site_config)
    lang_codes = get_enabled_language_codes(site_config, registry=active_registry)

    ordered_pairs = build_comparison_pairs(
        experience_types,
        slug_field=slug_field,
        exclusion_pairs=exclusion_pairs,
    )

    slug_cache = _build_experience_slug_cache(
        site_config,
        experience_types,
        slug_field=slug_field,
        registry=active_registry,
    )

    dest_items: List[Tuple[str, Mapping[str, Any]]] = []
    seen_destination_ids: Set[str] = set()

    for idx, destination in enumerate(destinations):
        item = _ensure_mapping(destination, f"destinations[{idx}]")
        dest_id = _validate_path_segment(
            _ensure_string(item.get("id"), f"destinations[{idx}].id"),
            f"destinations[{idx}].id",
            check_reserved_substrings=True,
        )

        if dest_id in seen_destination_ids:
            raise SitemapBuildError(f"Duplicate destination id detected: {dest_id!r}")
        seen_destination_ids.add(dest_id)

        dest_items.append((dest_id, item))

    entries: List[SitemapEntry] = []

    for destination_id, _dest in dest_items:
        for exp_a, exp_b in ordered_pairs:
            exp_a_id = _ensure_string(exp_a.get("id"), "exp_a.id")
            exp_b_id = _ensure_string(exp_b.get("id"), "exp_b.id")
            comparison_identifier = f"{destination_id}:{exp_a_id}:{exp_b_id}"

            for lang in lang_codes:
                exp_a_slug = slug_cache[exp_a_id][lang]
                exp_b_slug = slug_cache[exp_b_id][lang]

                url = build_comparison_path(
                    site_config,
                    lang,
                    destination_id,
                    exp_a_slug,
                    exp_b_slug,
                    absolute=True,
                    registry=active_registry,
                )
                entries.append(
                    _make_sitemap_entry(url, lang, "comparison", comparison_identifier)
                )

    return entries
