#!/usr/bin/env python3
"""
TourVsTravel — Central SEO System
=================================

Purpose:
- Centralize all metadata generation for the entire site
- Enforce strict validation for canonical, hreflang, OG, Twitter, and JSON-LD
- Remove SEO logic drift across generators and templates
- Fail early on invalid or incomplete metadata inputs

Design principles:
- one SEO layer for the whole project
- fail closed, not fail open
- no generator should handcraft metadata ad hoc
- canonical URLs must be absolute HTTPS and belong to the configured site
- hreflang maps must be complete for all enabled languages
- OG/Twitter metadata must be internally consistent
- structured data must be valid JSON-LD objects, not loose fragments
"""

from __future__ import annotations

import json
from datetime import date, datetime
from string import Formatter
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set
from urllib.parse import urlparse

from scripts.i18n import (
    build_hreflang_map,
    build_language_registry,
    get_language_config,
    translate_string,
)
from scripts.routes import build_home_path


# ============================================================================
# Exports
# ============================================================================

__all__ = [
    # Exceptions
    "SeoError",
    "MetadataBuildError",
    "JsonLdBuildError",
    # Template / metadata helpers
    "render_meta_template",
    "build_page_seo_from_templates",
    "build_page_seo",
    "normalize_meta_title",
    "normalize_meta_description",
    "normalize_canonical_url",
    "normalize_og_image_url",
    "normalize_hreflang_entries",
    # JSON-LD utilities
    "serialize_jsonld_payloads",
    "build_organization_jsonld",
    "build_website_jsonld",
    "build_webpage_jsonld",
    "build_article_jsonld",
    "build_breadcrumb_jsonld",
    "build_faq_jsonld",
]


# ============================================================================
# Exceptions
# ============================================================================

class SeoError(Exception):
    """Base SEO exception."""


class MetadataBuildError(SeoError):
    """Raised when metadata cannot be built safely."""


class JsonLdBuildError(SeoError):
    """Raised when JSON-LD payloads are invalid."""


# ============================================================================
# Internal helpers
# ============================================================================

def _ensure_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SeoError(f"{label} must be a mapping/object.")
    return value


def _ensure_list(
    value: Any,
    label: str,
    *,
    min_length: int = 0,
) -> List[Any]:
    if not isinstance(value, list):
        raise SeoError(f"{label} must be a list.")
    if len(value) < min_length:
        raise SeoError(f"{label} must contain at least {min_length} item(s).")
    return value


def _ensure_string(value: Any, label: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise SeoError(f"{label} must be a string.")
    if not allow_empty and not value.strip():
        raise SeoError(f"{label} must not be empty.")
    return value


def _ensure_bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise SeoError(f"{label} must be a boolean.")
    return value


def _ensure_sequence_strings(
    values: Sequence[Any],
    label: str,
    *,
    min_length: int = 0,
) -> List[str]:
    output: List[str] = []
    for idx, item in enumerate(values):
        output.append(_ensure_string(item, f"{label}[{idx}]"))
    if len(output) < min_length:
        raise SeoError(f"{label} must contain at least {min_length} string item(s).")
    return output


def _dedupe_preserve_order(values: Iterable[str]) -> List[str]:
    seen: Set[str] = set()
    output: List[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            output.append(value)
    return output


def _get_site_mapping(site_config: Mapping[str, Any]) -> Mapping[str, Any]:
    return _ensure_mapping(site_config, "site_config")


def _get_site_section(site_config: Mapping[str, Any]) -> Mapping[str, Any]:
    root = _get_site_mapping(site_config)
    if "site" not in root:
        raise SeoError("site_config.site is missing.")
    return _ensure_mapping(root["site"], "site_config.site")


def _get_seo_section(site_config: Mapping[str, Any]) -> Mapping[str, Any]:
    root = _get_site_mapping(site_config)
    if "seo" not in root:
        raise SeoError("site_config.seo is missing.")
    return _ensure_mapping(root["seo"], "site_config.seo")


def _is_absolute_https_url(value: str) -> bool:
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


def _require_absolute_https_url(value: Any, label: str) -> str:
    url = _ensure_string(value, label)
    if not _is_absolute_https_url(url):
        raise MetadataBuildError(
            f"{label} must be an absolute HTTPS URL with no credentials. Got: {url!r}"
        )
    return url


def _normalized_origin_parts(url: str) -> tuple[str, str, int]:
    parsed = urlparse(url)

    scheme = (parsed.scheme or "").lower()
    hostname = (parsed.hostname or "").lower()

    if scheme == "https":
        port = parsed.port or 443
    elif scheme == "http":
        port = parsed.port or 80
    else:
        port = parsed.port or -1

    return scheme, hostname, port


def _same_origin(url_a: str, url_b: str) -> bool:
    return _normalized_origin_parts(url_a) == _normalized_origin_parts(url_b)


def _require_site_scoped_url(site_config: Mapping[str, Any], url: str, label: str) -> str:
    site = _get_site_section(site_config)

    if "base_url" not in site:
        raise MetadataBuildError("site_config.site.base_url is missing.")

    base_url = _require_absolute_https_url(site["base_url"], "site_config.site.base_url")
    candidate = _require_absolute_https_url(url, label)

    if not _same_origin(base_url, candidate):
        raise MetadataBuildError(
            f"{label} must belong to the configured site origin. "
            f"Expected origin of {base_url!r}, got {candidate!r}"
        )
    return candidate


def _normalize_absolute_or_root_relative_url(
    site_config: Mapping[str, Any],
    value: str,
    label: str,
) -> str:
    """
    Accept either:
    - absolute HTTPS URL
    - root-relative path starting with '/'

    Normalize root-relative paths against site.base_url.
    """
    raw = _ensure_string(value, label)

    if _is_absolute_https_url(raw):
        return raw

    if not raw.startswith("/"):
        raise MetadataBuildError(
            f"{label} must be either an absolute HTTPS URL or a root-relative path. Got: {raw!r}"
        )

    site = _get_site_section(site_config)

    if "base_url" not in site:
        raise MetadataBuildError("site_config.site.base_url is missing.")

    base_url = _require_absolute_https_url(site["base_url"], "site_config.site.base_url")
    return f"{base_url.rstrip('/')}{raw}"


def _normalize_date_value(value: Any, label: str) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise JsonLdBuildError(f"{label} must be timezone-aware when using datetime.")
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        return _ensure_string(value, label)
    raise JsonLdBuildError(f"{label} must be a date, datetime, or ISO date string.")


def _extract_format_fields(template: str) -> List[str]:
    fields: List[str] = []
    for _, field_name, _, _ in Formatter().parse(template):
        if field_name:
            fields.append(field_name)
    return fields


def _compact_json(payload: Mapping[str, Any]) -> str:
    try:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    except Exception as exc:
        raise JsonLdBuildError(f"Failed to serialize JSON-LD payload: {exc}") from exc


# ============================================================================
# Template rendering
# ============================================================================

def render_meta_template(
    template: str,
    context: Mapping[str, Any],
    *,
    label: str,
    allow_extra_context: bool = True,
) -> str:
    """
    Strict formatter for SEO templates.

    Rules:
    - every placeholder must exist in context
    - every referenced value must resolve to a non-empty string after str()
    - extra context is allowed by default, but can be forbidden
    """
    tpl = _ensure_string(template, label)
    ctx = _ensure_mapping(context, f"{label}.context")

    field_names = _extract_format_fields(tpl)
    unique_fields = _dedupe_preserve_order(field_names)

    missing = [field for field in unique_fields if field not in ctx]
    if missing:
        raise MetadataBuildError(
            f"{label} is missing placeholder value(s): {', '.join(missing)}"
        )

    if not allow_extra_context:
        extra = sorted(set(ctx.keys()) - set(unique_fields))
        if extra:
            raise MetadataBuildError(
                f"{label} received unexpected placeholder value(s): {', '.join(extra)}"
            )

    safe_context: Dict[str, str] = {}
    for field in unique_fields:
        raw_value = ctx[field]
        text_value = str(raw_value).strip()
        if not text_value:
            raise MetadataBuildError(
                f"{label} placeholder {field!r} resolved to an empty value."
            )
        safe_context[field] = text_value

    try:
        rendered = tpl.format(**safe_context)
    except KeyError as exc:
        raise MetadataBuildError(f"{label} missing placeholder during format: {exc}") from exc
    except Exception as exc:
        raise MetadataBuildError(f"{label} failed to render: {exc}") from exc

    rendered = rendered.strip()
    if not rendered:
        raise MetadataBuildError(f"{label} rendered to an empty string.")

    return rendered


# ============================================================================
# Normalizers
# ============================================================================

def normalize_meta_title(title: str) -> str:
    text = _ensure_string(title, "meta title")
    if len(text) > 300:
        raise MetadataBuildError(
            f"meta title is unreasonably long ({len(text)} chars). Refusing to emit."
        )
    return text


def normalize_meta_description(description: str) -> str:
    text = _ensure_string(description, "meta description")
    if len(text) > 1000:
        raise MetadataBuildError(
            f"meta description is unreasonably long ({len(text)} chars). Refusing to emit."
        )
    return text


def normalize_canonical_url(site_config: Mapping[str, Any], canonical_url: str) -> str:
    return _require_site_scoped_url(site_config, canonical_url, "canonical_url")


def normalize_og_image_url(site_config: Mapping[str, Any], image_url: str) -> str:
    """
    OG image may be:
    - site-scoped absolute HTTPS
    - external CDN absolute HTTPS
    - root-relative path, normalized against site.base_url
    """
    return _normalize_absolute_or_root_relative_url(site_config, image_url, "og_image_url")


def normalize_hreflang_entries(
    site_config: Mapping[str, Any],
    urls_by_lang: Mapping[str, str],
) -> List[Dict[str, str]]:
    """
    Return hreflang entries as a stable list:
        [{"lang": "en", "url": "https://..."}, ...]
    """
    hreflang_map = build_hreflang_map(site_config, urls_by_lang)

    entries: List[Dict[str, str]] = []
    for hreflang_code, url in hreflang_map.items():
        entries.append(
            {
                "lang": _ensure_string(hreflang_code, "hreflang lang"),
                "url": _require_absolute_https_url(url, f"hreflang[{hreflang_code}]"),
            }
        )

    return entries


# ============================================================================
# Config-driven defaults
# ============================================================================

def _get_site_name(site_config: Mapping[str, Any]) -> str:
    site = _get_site_section(site_config)
    if "name" not in site:
        raise MetadataBuildError("site_config.site.name is missing.")
    return _ensure_string(site["name"], "site_config.site.name")


def _get_site_base_url(site_config: Mapping[str, Any]) -> str:
    site = _get_site_section(site_config)
    if "base_url" not in site:
        raise MetadataBuildError("site_config.site.base_url is missing.")
    return _require_absolute_https_url(site["base_url"], "site_config.site.base_url")


def _get_default_robots_directive(site_config: Mapping[str, Any]) -> str:
    seo = _get_seo_section(site_config)
    if "robots_directive" not in seo:
        raise MetadataBuildError("site_config.seo.robots_directive is missing.")
    return _ensure_string(seo["robots_directive"], "site_config.seo.robots_directive")


def _get_default_twitter_card(site_config: Mapping[str, Any]) -> str:
    seo = _get_seo_section(site_config)
    if "twitter_card" not in seo:
        raise MetadataBuildError("site_config.seo.twitter_card is missing.")
    return _ensure_string(seo["twitter_card"], "site_config.seo.twitter_card")


def _get_default_og_image(site_config: Mapping[str, Any]) -> str:
    seo = _get_seo_section(site_config)
    if "default_og_image" not in seo:
        raise MetadataBuildError("site_config.seo.default_og_image is missing.")
    return normalize_og_image_url(site_config, _ensure_string(seo["default_og_image"], "site_config.seo.default_og_image"))


def _get_title_template(site_config: Mapping[str, Any], lang: str) -> str:
    seo = _get_seo_section(site_config)

    if "title_template" in seo:
        return translate_string(
            seo["title_template"],
            lang,
            site_config=site_config,
            field_name="site_config.seo.title_template",
        )

    if "default_title_template" in seo:
        return translate_string(
            seo["default_title_template"],
            lang,
            site_config=site_config,
            field_name="site_config.seo.default_title_template",
        )

    raise MetadataBuildError(
        "site_config.seo.title_template or site_config.seo.default_title_template is required."
    )


def _get_description_template(site_config: Mapping[str, Any], lang: str) -> str:
    seo = _get_seo_section(site_config)

    if "description_template" in seo:
        return translate_string(
            seo["description_template"],
            lang,
            site_config=site_config,
            field_name="site_config.seo.description_template",
        )

    if "default_description_template" in seo:
        return translate_string(
            seo["default_description_template"],
            lang,
            site_config=site_config,
            field_name="site_config.seo.default_description_template",
        )

    raise MetadataBuildError(
        "site_config.seo.description_template or site_config.seo.default_description_template is required."
    )


# ============================================================================
# Config-template page SEO builder
# ============================================================================

def build_page_seo_from_templates(
    site_config: Mapping[str, Any],
    lang: str,
    *,
    title_context: Mapping[str, Any],
    description_context: Mapping[str, Any],
    canonical_url: str,
    urls_by_lang: Mapping[str, str],
    page_type: str = "website",
    robots_directive: Optional[str] = None,
    og_title: Optional[str] = None,
    og_description: Optional[str] = None,
    og_image_url: Optional[str] = None,
    og_type: str = "website",
    twitter_card: Optional[str] = None,
    twitter_title: Optional[str] = None,
    twitter_description: Optional[str] = None,
    twitter_image_url: Optional[str] = None,
    jsonld_payloads: Optional[Sequence[Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Build page SEO using title/description templates from site_config.seo.
    """
    title_template = _get_title_template(site_config, lang)
    description_template = _get_description_template(site_config, lang)

    title = render_meta_template(
        title_template,
        title_context,
        label="seo.title_template",
    )
    description = render_meta_template(
        description_template,
        description_context,
        label="seo.description_template",
    )

    return build_page_seo(
        site_config,
        lang,
        page_title=title,
        page_description=description,
        canonical_url=canonical_url,
        urls_by_lang=urls_by_lang,
        page_type=page_type,
        robots_directive=robots_directive,
        og_title=og_title,
        og_description=og_description,
        og_image_url=og_image_url,
        og_type=og_type,
        twitter_card=twitter_card,
        twitter_title=twitter_title,
        twitter_description=twitter_description,
        twitter_image_url=twitter_image_url,
        jsonld_payloads=jsonld_payloads,
    )


# ============================================================================
# Core page SEO builder
# ============================================================================

def build_page_seo(
    site_config: Mapping[str, Any],
    lang: str,
    *,
    page_title: str,
    page_description: str,
    canonical_url: str,
    urls_by_lang: Mapping[str, str],
    page_type: str = "website",
    robots_directive: Optional[str] = None,
    og_title: Optional[str] = None,
    og_description: Optional[str] = None,
    og_image_url: Optional[str] = None,
    og_type: str = "website",
    twitter_card: Optional[str] = None,
    twitter_title: Optional[str] = None,
    twitter_description: Optional[str] = None,
    twitter_image_url: Optional[str] = None,
    jsonld_payloads: Optional[Sequence[Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Build the complete SEO payload for a page.

    This is the central handoff object for templates/generators.
    """
    active_registry = build_language_registry(site_config)
    get_language_config(site_config, lang, registry=active_registry)

    title = normalize_meta_title(page_title)
    description = normalize_meta_description(page_description)
    canonical = normalize_canonical_url(site_config, canonical_url)
    hreflang = normalize_hreflang_entries(site_config, urls_by_lang)

    resolved_robots = _ensure_string(
        robots_directive if robots_directive is not None else _get_default_robots_directive(site_config),
        "robots_directive",
    )

    resolved_og_title = normalize_meta_title(og_title or title)
    resolved_og_description = normalize_meta_description(og_description or description)
    resolved_og_image = normalize_og_image_url(
        site_config,
        og_image_url if og_image_url is not None else _get_default_og_image(site_config),
    )
    resolved_og_type = _ensure_string(og_type, "og_type")

    resolved_twitter_card = _ensure_string(
        twitter_card if twitter_card is not None else _get_default_twitter_card(site_config),
        "twitter_card",
    )
    resolved_twitter_title = normalize_meta_title(twitter_title or resolved_og_title)
    resolved_twitter_description = normalize_meta_description(
        twitter_description or resolved_og_description
    )
    resolved_twitter_image = normalize_og_image_url(
        site_config,
        twitter_image_url if twitter_image_url is not None else resolved_og_image,
    )

    serialized_jsonld = serialize_jsonld_payloads(jsonld_payloads or [])

    return {
        "lang": _ensure_string(lang, "lang"),
        "page_type": _ensure_string(page_type, "page_type"),
        "title": title,
        "description": description,
        "canonical_url": canonical,
        "robots_directive": resolved_robots,
        "hreflang": hreflang,
        "og": {
            "title": resolved_og_title,
            "description": resolved_og_description,
            "image": resolved_og_image,
            "type": resolved_og_type,
            "url": canonical,
            "site_name": _get_site_name(site_config),
        },
        "twitter": {
            "card": resolved_twitter_card,
            "title": resolved_twitter_title,
            "description": resolved_twitter_description,
            "image": resolved_twitter_image,
        },
        "jsonld": serialized_jsonld,
    }


# ============================================================================
# JSON-LD serialization
# ============================================================================

def serialize_jsonld_payloads(payloads: Sequence[Mapping[str, Any]]) -> List[str]:
    """
    Validate and serialize JSON-LD payloads to compact JSON strings.

    Rules:
    - every payload must be a mapping
    - every payload must contain @context and @type
    """
    serialized: List[str] = []

    for idx, payload in enumerate(payloads):
        item = _ensure_mapping(payload, f"jsonld_payloads[{idx}]")

        if "@context" not in item:
            raise JsonLdBuildError(f"jsonld_payloads[{idx}] is missing '@context'.")
        if "@type" not in item:
            raise JsonLdBuildError(f"jsonld_payloads[{idx}] is missing '@type'.")

        _ensure_string(item["@context"], f"jsonld_payloads[{idx}].@context")
        _ensure_string(item["@type"], f"jsonld_payloads[{idx}].@type")

        serialized.append(_compact_json(item))

    return serialized


# ============================================================================
# JSON-LD builders
# ============================================================================

def build_organization_jsonld(
    site_config: Mapping[str, Any],
    *,
    logo_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build Organization JSON-LD for the site.
    """
    site_name = _get_site_name(site_config)
    base_url = _get_site_base_url(site_config)

    payload: Dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": site_name,
        "url": base_url,
    }

    if logo_url is not None:
        payload["logo"] = normalize_og_image_url(site_config, logo_url)
    else:
        root = _get_site_mapping(site_config)
        brand = root.get("brand")
        if isinstance(brand, Mapping):
            logo_mapping = brand.get("logo")
            if isinstance(logo_mapping, Mapping) and "icon_path" in logo_mapping:
                payload["logo"] = normalize_og_image_url(
                    site_config,
                    _ensure_string(logo_mapping["icon_path"], "site_config.brand.logo.icon_path"),
                )

    return payload


def build_website_jsonld(
    site_config: Mapping[str, Any],
    lang: str,
    *,
    home_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build WebSite JSON-LD.
    """
    active_registry = build_language_registry(site_config)
    get_language_config(site_config, lang, registry=active_registry)

    url = normalize_canonical_url(
        site_config,
        home_url if home_url is not None else build_home_path(site_config, lang, absolute=True, registry=active_registry),
    )

    return {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": _get_site_name(site_config),
        "url": url,
        "inLanguage": lang,
    }


def build_webpage_jsonld(
    *,
    name: str,
    description: str,
    url: str,
    lang: str,
    is_part_of_url: Optional[str] = None,
    breadcrumb_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build a generic WebPage JSON-LD payload.
    """
    payload: Dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": _ensure_string(name, "webpage.name"),
        "description": _ensure_string(description, "webpage.description"),
        "url": _require_absolute_https_url(url, "webpage.url"),
        "inLanguage": _ensure_string(lang, "webpage.lang"),
    }

    if is_part_of_url is not None:
        payload["isPartOf"] = {
            "@type": "WebSite",
            "url": _require_absolute_https_url(is_part_of_url, "webpage.is_part_of_url"),
        }

    if breadcrumb_id is not None:
        payload["breadcrumb"] = {
            "@id": _require_absolute_https_url(breadcrumb_id, "webpage.breadcrumb_id"),
        }

    return payload


def build_article_jsonld(
    *,
    headline: str,
    description: str,
    url: str,
    lang: str,
    publisher_name: str,
    publisher_url: str,
    date_modified: Any,
    date_published: Optional[Any] = None,
    image_url: Optional[str] = None,
    author_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build Article JSON-LD.
    """
    canonical_url = _require_absolute_https_url(url, "article.url")

    payload: Dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": _ensure_string(headline, "article.headline"),
        "description": _ensure_string(description, "article.description"),
        "url": canonical_url,
        "inLanguage": _ensure_string(lang, "article.lang"),
        "dateModified": _normalize_date_value(date_modified, "article.dateModified"),
        "publisher": {
            "@type": "Organization",
            "name": _ensure_string(publisher_name, "article.publisher_name"),
            "url": _require_absolute_https_url(publisher_url, "article.publisher_url"),
        },
        "mainEntityOfPage": canonical_url,
    }

    if date_published is not None:
        payload["datePublished"] = _normalize_date_value(date_published, "article.datePublished")

    if image_url is not None:
        payload["image"] = _require_absolute_https_url(image_url, "article.image")

    if author_name is not None:
        payload["author"] = {
            "@type": "Person",
            "name": _ensure_string(author_name, "article.author_name"),
        }

    return payload


def build_breadcrumb_jsonld(
    items: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """
    Build BreadcrumbList JSON-LD.

    Expected items:
        [{"name": "...", "url": "https://..."}, ...]
    """
    raw_items = _ensure_list(list(items), "breadcrumb.items", min_length=1)

    elements: List[Dict[str, Any]] = []
    for idx, item in enumerate(raw_items, start=1):
        mapping = _ensure_mapping(item, f"breadcrumb.items[{idx - 1}]")
        name = _ensure_string(mapping.get("name"), f"breadcrumb.items[{idx - 1}].name")
        url = _require_absolute_https_url(
            mapping.get("url"),
            f"breadcrumb.items[{idx - 1}].url",
        )
        elements.append(
            {
                "@type": "ListItem",
                "position": idx,
                "name": name,
                "item": url,
            }
        )

    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": elements,
    }


def build_faq_jsonld(
    items: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """
    Build FAQPage JSON-LD.

    Expected items:
        [{"question": "...", "answer": "..."}, ...]
    """
    raw_items = _ensure_list(list(items), "faq.items", min_length=1)

    entities: List[Dict[str, Any]] = []
    for idx, item in enumerate(raw_items):
        mapping = _ensure_mapping(item, f"faq.items[{idx}]")
        question = _ensure_string(mapping.get("question"), f"faq.items[{idx}].question")
        answer = _ensure_string(mapping.get("answer"), f"faq.items[{idx}].answer")

        entities.append(
            {
                "@type": "Question",
                "name": question,
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": answer,
                },
            }
        )

    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": entities,
    }
