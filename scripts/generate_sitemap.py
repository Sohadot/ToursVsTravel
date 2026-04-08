#!/usr/bin/env python3
"""
TourVsTravel — Sitemap Generator
================================

Purpose
-------
Generate a strict, deterministic sitemap.xml into:

    output/sitemap.xml

Architectural policy
--------------------
This generator is OUTPUT-DRIVEN, not assumption-driven.

That means:
- it scans the actual generated HTML files under the build output directory
- it includes only pages that truly exist on disk
- it never invents phantom URLs from data files alone
- it automatically includes future generated pages once they are emitted
  into the output tree by the build system

This is the correct sovereign behavior for a static SEO infrastructure:
the sitemap reflects the real public surface of the site, not hypothetical
routes that may not exist yet.

Design principles
-----------------
- fail closed on invalid configuration
- no phantom URLs
- no silent fallback to broken sitemap shapes
- deterministic ordering
- atomic write
- same-origin URL enforcement
- multilingual alternate URL support from actual generated files
- single official public API:
      generate_sitemap_file(output_dir=...)

Execution
---------
Run from repository root:

    python -m scripts.generate_sitemap
    python -m scripts.generate_sitemap --output-dir ./output
    python -m scripts.generate_sitemap --stdout

Notes
-----
- sitemap.xml is site-wide, not per language
- this generator scans actual generated HTML files under output/
- it skips:
    * static assets
    * robots.txt
    * sitemap.xml
    * hidden files/directories
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
import xml.etree.ElementTree as ET

import yaml


# ============================================================================
# Logging
# ============================================================================

log = logging.getLogger("generate_sitemap")


def configure_logging() -> None:
    """
    Configure logging for standalone CLI execution.

    This is called only from main(), so importing this module from build.py
    does not mutate the host process logging policy.
    """
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S",
        )


# ============================================================================
# XML namespaces
# ============================================================================

SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
XHTML_NS = "http://www.w3.org/1999/xhtml"

ET.register_namespace("", SITEMAP_NS)
ET.register_namespace("xhtml", XHTML_NS)


# ============================================================================
# Paths
# ============================================================================

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "output"


# ============================================================================
# Exceptions
# ============================================================================

class GenerateSitemapError(Exception):
    """Base sitemap generator error."""


class SitemapConfigError(GenerateSitemapError):
    """Raised when sitemap configuration or site configuration is invalid."""


class SitemapWriteError(GenerateSitemapError):
    """Raised when sitemap.xml cannot be written."""


# ============================================================================
# Models
# ============================================================================

@dataclass(frozen=True)
class DiscoveredPage:
    """
    A discovered HTML page from the output tree.

    url_path:
        Root-relative public path, e.g. "/en/" or "/fr/methodology/"
    loc:
        Absolute canonical URL, e.g. "https://tourvstravel.com/en/"
    source_file:
        Physical file that produced the URL.
    lastmod:
        W3C datetime in UTC, e.g. "2026-04-07T18:17:36Z"
    lang_code:
        Optional top-level language segment if the page lives under /{lang}/...
    cluster_key:
        Relative path after stripping the top-level language directory.
        Used to build hreflang alternates only across pages that truly exist.
    """
    url_path: str
    loc: str
    source_file: Path
    lastmod: str
    lang_code: Optional[str]
    cluster_key: Optional[Tuple[str, ...]]


@dataclass(frozen=True)
class SitemapEntry:
    """
    Final sitemap entry model.

    alternates:
        Mapping of hreflang code -> absolute URL
    """
    loc: str
    lastmod: str
    alternates: Dict[str, str]


# ============================================================================
# YAML loading
# ============================================================================

def _load_yaml_file(path: Path) -> Any:
    if not path.exists():
        raise SitemapConfigError(f"Missing required YAML file: {path}")
    if not path.is_file():
        raise SitemapConfigError(f"YAML path is not a file: {path}")

    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise SitemapConfigError(f"Invalid YAML in {path}: {exc}") from exc

    if data is None:
        raise SitemapConfigError(f"YAML file is empty: {path}")

    return data


def load_site_config() -> Mapping[str, Any]:
    path = DATA_DIR / "site_config.yaml"
    config = _load_yaml_file(path)

    if not isinstance(config, Mapping):
        raise SitemapConfigError("data/site_config.yaml must contain a top-level mapping/object.")
    if "site" not in config:
        raise SitemapConfigError("site_config.yaml must contain top-level key 'site'.")
    if "languages" not in config:
        raise SitemapConfigError("site_config.yaml must contain top-level key 'languages'.")
    if "seo" not in config:
        raise SitemapConfigError("site_config.yaml must contain top-level key 'seo'.")

    return config


# ============================================================================
# General helpers
# ============================================================================

def _ensure_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SitemapConfigError(f"{label} must be a mapping/object.")
    return value


def _ensure_string(value: Any, label: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise SitemapConfigError(f"{label} must be a string.")
    text = value.strip()
    if not allow_empty and not text:
        raise SitemapConfigError(f"{label} must not be empty.")
    return text


def _ensure_list(value: Any, label: str) -> List[Any]:
    if not isinstance(value, list):
        raise SitemapConfigError(f"{label} must be a list.")
    return value


def _get_nested(mapping: Mapping[str, Any], path: Sequence[str], default: Any = None) -> Any:
    current: Any = mapping
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return default
        current = current[key]
    return current


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


def _normalize_https_base_url(raw: str) -> str:
    text = _ensure_string(raw, "site_config.site.base_url")
    parsed = urlparse(text)

    if parsed.scheme != "https":
        raise SitemapConfigError(
            f"site_config.site.base_url must use https scheme. Got: {text!r}"
        )
    if not parsed.netloc:
        raise SitemapConfigError(
            f"site_config.site.base_url must be an absolute HTTPS URL. Got: {text!r}"
        )
    if parsed.username is not None or parsed.password is not None:
        raise SitemapConfigError(
            "site_config.site.base_url must not contain embedded credentials."
        )
    if parsed.query or parsed.fragment:
        raise SitemapConfigError(
            "site_config.site.base_url must not contain query parameters or fragments."
        )
    if (parsed.path or "") not in ("", "/"):
        raise SitemapConfigError(
            f"site_config.site.base_url must not contain a path. Got: {text!r}"
        )

    return f"https://{parsed.netloc.rstrip('/')}"


def _default_port(parsed) -> int:
    scheme = (parsed.scheme or "").lower()
    if scheme == "https":
        return 443
    if scheme == "http":
        return 80
    return 0


def _same_origin(url_a: str, url_b: str) -> bool:
    a = urlparse(url_a)
    b = urlparse(url_b)

    a_scheme = (a.scheme or "").lower()
    b_scheme = (b.scheme or "").lower()
    a_host = (a.hostname or "").lower()
    b_host = (b.hostname or "").lower()
    a_port = a.port or _default_port(a)
    b_port = b.port or _default_port(b)

    return a_scheme == b_scheme and a_host == b_host and a_port == b_port


def _ensure_safe_output_dir(output_dir: Path) -> Path:
    """
    Allow only:
    - ROOT_DIR/output
    - direct build stages named '.build-stage-*' under ROOT_DIR
    - safe directories outside the repo

    Reject:
    - filesystem root
    - arbitrary in-repo destinations
    """
    resolved = output_dir.resolve()
    repo_root = ROOT_DIR.resolve()
    allowed_in_repo_output = DEFAULT_OUTPUT_DIR.resolve()

    if not resolved.is_absolute():
        raise SitemapWriteError(f"Output directory must be absolute. Got: {output_dir}")

    if str(resolved) == resolved.anchor:
        raise SitemapWriteError(f"Refusing to write sitemap.xml to filesystem root: {resolved}")

    if resolved == allowed_in_repo_output:
        return resolved

    if resolved.parent == repo_root and resolved.name.startswith(".build-stage-"):
        return resolved

    try:
        resolved.relative_to(repo_root)
        raise SitemapWriteError(
            f"Refusing in-repo output directory outside the sanctioned build target. "
            f"Allowed in-repo outputs are only: {allowed_in_repo_output} "
            f"and direct build stages named '.build-stage-*' under {repo_root} ; got: {resolved}"
        )
    except ValueError:
        # Outside repo is allowed
        pass

    return resolved


def _resolve_base_url(site_config: Mapping[str, Any]) -> str:
    site_section = _ensure_mapping(site_config.get("site"), "site_config.site")
    raw = site_section.get("base_url")
    if raw is None:
        raise SitemapConfigError("site_config.site.base_url is missing.")
    return _normalize_https_base_url(raw)


def _resolve_enabled_languages(site_config: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    raw = site_config.get("languages")
    languages = _ensure_list(raw, "site_config.languages")
    enabled: List[Mapping[str, Any]] = []

    for idx, item in enumerate(languages):
        lang = _ensure_mapping(item, f"site_config.languages[{idx}]")
        code = _ensure_string(lang.get("code"), f"site_config.languages[{idx}].code")
        enabled_flag = lang.get("enabled", True)
        if not isinstance(enabled_flag, bool):
            raise SitemapConfigError(f"site_config.languages[{idx}].enabled must be a boolean.")
        if enabled_flag:
            # Ensure required fields are structurally valid if present
            _ensure_string(code, f"site_config.languages[{idx}].code")
            if "hreflang" in lang:
                _ensure_string(lang.get("hreflang"), f"site_config.languages[{idx}].hreflang")
            enabled.append(lang)

    if not enabled:
        raise SitemapConfigError("At least one language must be enabled in site_config.languages.")

    return enabled


def _resolve_include_hreflang(site_config: Mapping[str, Any]) -> bool:
    value = _get_nested(site_config, ("seo", "sitemap", "include_hreflang_alternates"), default=True)
    if not isinstance(value, bool):
        raise SitemapConfigError("site_config.seo.sitemap.include_hreflang_alternates must be a boolean.")
    return value


def _resolve_include_x_default(site_config: Mapping[str, Any]) -> bool:
    value = _get_nested(site_config, ("seo", "sitemap", "include_x_default"), default=False)
    if not isinstance(value, bool):
        raise SitemapConfigError("site_config.seo.sitemap.include_x_default must be a boolean.")
    return value


def _resolve_x_default_lang(site_config: Mapping[str, Any], enabled_languages: List[Mapping[str, Any]]) -> str:
    enabled_codes = [_ensure_string(item.get("code"), "enabled_language.code") for item in enabled_languages]
    raw = _get_nested(site_config, ("seo", "sitemap", "x_default_lang"), default=None)

    if raw is None:
        return enabled_codes[0]

    value = _ensure_string(raw, "site_config.seo.sitemap.x_default_lang")
    if value not in enabled_codes:
        raise SitemapConfigError(
            f"site_config.seo.sitemap.x_default_lang {value!r} is not an enabled language. "
            f"Enabled: {', '.join(enabled_codes)}"
        )
    return value


def _resolve_hreflang_code(lang_item: Mapping[str, Any]) -> str:
    if "hreflang" in lang_item:
        return _ensure_string(lang_item.get("hreflang"), "language.hreflang")
    return _ensure_string(lang_item.get("code"), "language.code")


def _dedupe_preserve_order(values: List[str]) -> List[str]:
    seen = set()
    output: List[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            output.append(value)
    return output


def _format_lastmod(path: Path) -> str:
    dt = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).replace(microsecond=0)
    return dt.isoformat().replace("+00:00", "Z")


def _path_to_public_url_path(relative_file: Path) -> str:
    """
    Convert an output-relative HTML path to a public URL path.

    Examples:
      en/index.html              -> /en/
      en/about/index.html        -> /en/about/
      en/report.html             -> /en/report
    """
    parts = list(relative_file.parts)
    if not parts:
        raise SitemapConfigError(f"Cannot derive public URL from empty relative path: {relative_file}")

    if relative_file.name.lower() == "index.html":
        prefix = "/".join(parts[:-1])
        return f"/{prefix}/" if prefix else "/"

    stem = relative_file.stem
    prefix_parts = parts[:-1] + [stem]
    return "/" + "/".join(prefix_parts)


def _build_absolute_url(base_url: str, url_path: str) -> str:
    path = url_path if url_path.startswith("/") else f"/{url_path}"
    if path == "/":
        absolute = base_url + "/"
    else:
        absolute = base_url + path

    if not _is_absolute_https_url(absolute):
        raise SitemapConfigError(f"Derived absolute URL is invalid: {absolute!r}")
    if not _same_origin(absolute, base_url):
        raise SitemapConfigError(f"Derived absolute URL is not same-origin as base_url: {absolute!r}")

    return absolute


# ============================================================================
# Discovery
# ============================================================================

def _should_skip_relative_path(relative_file: Path) -> bool:
    parts = relative_file.parts
    if not parts:
        return True

    # Skip hidden files/directories
    if any(part.startswith(".") for part in parts):
        return True

    # Skip static assets entirely
    if parts[0] == "static":
        return True

    # Skip obvious non-page control files even if html-looking logic changes later
    if relative_file.name in {"robots.txt", "sitemap.xml"}:
        return True

    # Only HTML pages belong in sitemap discovery here
    if relative_file.suffix.lower() != ".html":
        return True

    return False


def discover_output_pages(
    *,
    output_dir: Path,
    site_config: Mapping[str, Any],
) -> List[DiscoveredPage]:
    safe_output_dir = _ensure_safe_output_dir(output_dir)

    if not safe_output_dir.exists():
        raise SitemapConfigError(f"Output directory does not exist: {safe_output_dir}")
    if not safe_output_dir.is_dir():
        raise SitemapConfigError(f"Output path is not a directory: {safe_output_dir}")

    base_url = _resolve_base_url(site_config)
    enabled_languages = _resolve_enabled_languages(site_config)
    enabled_codes = {
        _ensure_string(item.get("code"), "enabled_language.code")
        for item in enabled_languages
    }

    pages: List[DiscoveredPage] = []
    seen_urls = set()

    for file_path in sorted(safe_output_dir.rglob("*.html")):
        relative_file = file_path.relative_to(safe_output_dir)

        if _should_skip_relative_path(relative_file):
            continue

        url_path = _path_to_public_url_path(relative_file)
        loc = _build_absolute_url(base_url, url_path)

        if loc in seen_urls:
            raise SitemapConfigError(
                f"Duplicate public URL discovered from output tree: {loc!r}"
            )
        seen_urls.add(loc)

        lang_code: Optional[str] = None
        cluster_key: Optional[Tuple[str, ...]] = None

        if relative_file.parts and relative_file.parts[0] in enabled_codes:
            lang_code = relative_file.parts[0]
            cluster_key = tuple(relative_file.parts[1:])

        pages.append(
            DiscoveredPage(
                url_path=url_path,
                loc=loc,
                source_file=file_path,
                lastmod=_format_lastmod(file_path),
                lang_code=lang_code,
                cluster_key=cluster_key,
            )
        )

    if not pages:
        raise SitemapConfigError(
            f"No HTML pages were discovered under output directory: {safe_output_dir}"
        )

    return pages


# ============================================================================
# Alternate URL clustering
# ============================================================================

def _build_alternate_clusters(
    *,
    pages: List[DiscoveredPage],
    site_config: Mapping[str, Any],
) -> Dict[str, Dict[str, str]]:
    include_hreflang = _resolve_include_hreflang(site_config)
    if not include_hreflang:
        return {}

    enabled_languages = _resolve_enabled_languages(site_config)

    code_to_hreflang: Dict[str, str] = {}
    for item in enabled_languages:
        code = _ensure_string(item.get("code"), "enabled_language.code")
        hreflang = _resolve_hreflang_code(item)
        if hreflang in code_to_hreflang.values():
            raise SitemapConfigError(
                f"Duplicate hreflang code detected in enabled languages: {hreflang!r}"
            )
        code_to_hreflang[code] = hreflang

    include_x_default = _resolve_include_x_default(site_config)
    x_default_lang = _resolve_x_default_lang(site_config, enabled_languages) if include_x_default else None

    clusters: Dict[Tuple[str, ...], Dict[str, str]] = {}
    for page in pages:
        if page.lang_code is None or page.cluster_key is None:
            continue

        cluster = clusters.setdefault(page.cluster_key, {})
        hreflang_code = code_to_hreflang[page.lang_code]
        if hreflang_code in cluster:
            raise SitemapConfigError(
                f"Duplicate hreflang alternate detected for cluster {page.cluster_key!r} "
                f"and hreflang {hreflang_code!r}"
            )
        cluster[hreflang_code] = page.loc

    url_to_alternates: Dict[str, Dict[str, str]] = {}
    for page in pages:
        if page.lang_code is None or page.cluster_key is None:
            url_to_alternates[page.loc] = {}
            continue

        cluster = dict(clusters.get(page.cluster_key, {}))

        if include_x_default and x_default_lang is not None:
            x_default_hreflang = code_to_hreflang[x_default_lang]
            x_default_url = cluster.get(x_default_hreflang)
            if x_default_url is None:
                raise SitemapConfigError(
                    f"x_default_lang {x_default_lang!r} was requested for cluster "
                    f"{page.cluster_key!r} but that language page does not exist."
                )
            cluster["x-default"] = x_default_url

        # Deterministic ordering for XML output later
        ordered: Dict[str, str] = {}
        for key in _dedupe_preserve_order(sorted(cluster.keys(), key=lambda x: (x == "x-default", x))):
            ordered[key] = cluster[key]

        url_to_alternates[page.loc] = ordered

    return url_to_alternates


# ============================================================================
# Entry construction
# ============================================================================

def build_sitemap_entries(
    *,
    output_dir: Path,
    site_config: Mapping[str, Any],
) -> List[SitemapEntry]:
    pages = discover_output_pages(output_dir=output_dir, site_config=site_config)
    alternates_by_url = _build_alternate_clusters(pages=pages, site_config=site_config)

    entries = [
        SitemapEntry(
            loc=page.loc,
            lastmod=page.lastmod,
            alternates=alternates_by_url.get(page.loc, {}),
        )
        for page in pages
    ]

    entries.sort(key=lambda item: item.loc)
    return entries


# ============================================================================
# XML rendering
# ============================================================================

def _build_url_element(entry: SitemapEntry) -> ET.Element:
    url_el = ET.Element(f"{{{SITEMAP_NS}}}url")

    loc_el = ET.SubElement(url_el, f"{{{SITEMAP_NS}}}loc")
    loc_el.text = entry.loc

    lastmod_el = ET.SubElement(url_el, f"{{{SITEMAP_NS}}}lastmod")
    lastmod_el.text = entry.lastmod

    for hreflang_code, href in entry.alternates.items():
        link_el = ET.SubElement(url_el, f"{{{XHTML_NS}}}link")
        link_el.set("rel", "alternate")
        link_el.set("hreflang", hreflang_code)
        link_el.set("href", href)

    return url_el


def build_sitemap_xml(site_config: Mapping[str, Any], *, output_dir: Path) -> bytes:
    entries = build_sitemap_entries(output_dir=output_dir, site_config=site_config)

    if not entries:
        raise SitemapConfigError("No sitemap entries were built.")

    root = ET.Element(f"{{{SITEMAP_NS}}}urlset")

    for entry in entries:
        root.append(_build_url_element(entry))

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


# ============================================================================
# Writing
# ============================================================================

def _atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: Optional[Path] = None

    try:
        with NamedTemporaryFile(
            "wb",
            dir=str(path.parent),
            delete=False,
            suffix=".tmp",
        ) as tmp:
            tmp.write(content)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_path = Path(tmp.name)

        if tmp_path is None:
            raise SitemapWriteError(f"Failed to create temporary file for {path}")

        tmp_path.replace(path)

    except Exception as exc:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise SitemapWriteError(f"Failed to write sitemap.xml atomically: {exc}") from exc


def write_sitemap_file(output_dir: Path, content: bytes) -> Path:
    safe_output_dir = _ensure_safe_output_dir(output_dir)
    path = safe_output_dir / "sitemap.xml"
    _atomic_write_bytes(path, content)
    return path


# ============================================================================
# Public API
# ============================================================================

def generate_sitemap_file(*, output_dir: Path = DEFAULT_OUTPUT_DIR) -> Path:
    """
    Official file-generation API for build.py and standalone usage.

    Returns the full output path of the generated sitemap.xml file.
    """
    site_config = load_site_config()
    content = build_sitemap_xml(site_config, output_dir=output_dir)
    path = write_sitemap_file(output_dir, content)
    log.info("Generated sitemap.xml -> %s", path)
    return path


# ============================================================================
# CLI
# ============================================================================

def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate TourVsTravel sitemap.xml"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Output directory root. Default: ./output",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print sitemap.xml to stdout instead of writing the file.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)

    if args.stdout:
        logging.disable(logging.CRITICAL)
    else:
        configure_logging()

    try:
        if args.stdout:
            site_config = load_site_config()
            content = build_sitemap_xml(site_config, output_dir=args.output_dir.resolve())
            print(content.decode("utf-8"), end="")
            return 0

        path = generate_sitemap_file(output_dir=args.output_dir.resolve())
        log.info("sitemap.xml generation completed successfully: %s", path)
        return 0

    except GenerateSitemapError as exc:
        log.error(str(exc))
        return 1
    except Exception as exc:
        log.exception("Unexpected sitemap generator failure: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
