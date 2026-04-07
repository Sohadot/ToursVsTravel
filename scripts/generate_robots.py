#!/usr/bin/env python3
"""
TourVsTravel — Robots.txt Generator
===================================

Purpose
-------
Generate a strict, deterministic robots.txt into:

    output/robots.txt

Design principles
-----------------
- fail closed on invalid configuration
- no unsafe raw line injection
- no silent fallbacks that create ambiguous crawler policy
- deterministic output order
- canonical sitemap URL derived from site_config.site.base_url
- optional extra sitemap URLs are validated strictly
- atomic file write

Execution
---------
Run from repository root:

    python -m scripts.generate_robots
    python -m scripts.generate_robots --output-dir ./output
    python -m scripts.generate_robots --stdout

Configuration contract
----------------------
Reads:
    data/site_config.yaml

Optional robots configuration may exist under:

    seo:
      robots:
        enabled: true
        comments:
          - "Public crawl policy"
        user_agents:
          - name: "*"
            allow:
              - "/"
            disallow: []
            crawl_delay: null
        additional_sitemaps: []
        host: null

Notes
-----
- robots.txt is site-wide, not per language.
- This generator does not require sitemap.xml to exist yet; it emits the
  canonical future location:
      {base_url}/sitemap.xml
"""

from __future__ import annotations

import argparse
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, List, Mapping, Optional, Sequence
from urllib.parse import urlparse

import yaml


# ============================================================================
# Logging
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("generate_robots")


# ============================================================================
# Paths
# ============================================================================

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "output"


# ============================================================================
# Exceptions
# ============================================================================

class GenerateRobotsError(Exception):
    """Base robots generator error."""


class RobotsConfigError(GenerateRobotsError):
    """Raised when robots configuration is invalid."""


class RobotsWriteError(GenerateRobotsError):
    """Raised when robots.txt cannot be written."""


# ============================================================================
# Models
# ============================================================================

@dataclass(frozen=True)
class RobotsGroup:
    """Single User-agent policy group."""
    name: str
    allow: List[str]
    disallow: List[str]
    crawl_delay: Optional[int] = None


@dataclass(frozen=True)
class RobotsDocument:
    """Validated robots.txt document model."""
    enabled: bool
    comments: List[str]
    groups: List[RobotsGroup]
    sitemap_urls: List[str]
    host: Optional[str] = None


# ============================================================================
# YAML loading
# ============================================================================

def _load_yaml_file(path: Path) -> Any:
    if not path.exists():
        raise RobotsConfigError(f"Missing required YAML file: {path}")
    if not path.is_file():
        raise RobotsConfigError(f"YAML path is not a file: {path}")

    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise RobotsConfigError(f"Invalid YAML in {path}: {exc}") from exc

    if data is None:
        raise RobotsConfigError(f"YAML file is empty: {path}")

    return data


def load_site_config() -> Mapping[str, Any]:
    path = DATA_DIR / "site_config.yaml"
    config = _load_yaml_file(path)

    if not isinstance(config, Mapping):
        raise RobotsConfigError("data/site_config.yaml must contain a top-level mapping/object.")
    if "site" not in config:
        raise RobotsConfigError("site_config.yaml must contain top-level key 'site'.")
    if "seo" not in config:
        raise RobotsConfigError("site_config.yaml must contain top-level key 'seo'.")

    return config


# ============================================================================
# General helpers
# ============================================================================

def _ensure_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RobotsConfigError(f"{label} must be a mapping/object.")
    return value


def _ensure_string(value: Any, label: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise RobotsConfigError(f"{label} must be a string.")
    text = value.strip()
    if not allow_empty and not text:
        raise RobotsConfigError(f"{label} must not be empty.")
    return text


def _ensure_list(value: Any, label: str) -> List[Any]:
    if not isinstance(value, list):
        raise RobotsConfigError(f"{label} must be a list.")
    return value


def _ensure_optional_positive_int(value: Any, label: str) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise RobotsConfigError(f"{label} must be an integer or null.")
    if value <= 0:
        raise RobotsConfigError(f"{label} must be > 0 when provided.")
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
        raise RobotsConfigError(
            f"site_config.site.base_url must use https scheme. Got: {text!r}"
        )
    if not parsed.netloc:
        raise RobotsConfigError(
            f"site_config.site.base_url must be an absolute HTTPS URL. Got: {text!r}"
        )
    if parsed.username is not None or parsed.password is not None:
        raise RobotsConfigError(
            "site_config.site.base_url must not contain embedded credentials."
        )
    if parsed.query or parsed.fragment:
        raise RobotsConfigError(
            "site_config.site.base_url must not contain query parameters or fragments."
        )
    if (parsed.path or "") not in ("", "/"):
        raise RobotsConfigError(
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


def _normalize_comment_line(value: Any, label: str) -> str:
    text = _ensure_string(value, label)

    for ch in text:
        code = ord(ch)
        if code < 32 or code == 127:
            raise RobotsConfigError(
                f"{label} contains forbidden control characters."
            )

    return text


def _normalize_robot_path(value: Any, label: str) -> str:
    """
    Normalize a robots.txt Allow/Disallow path.

    Allowed:
      /
      /private/
      /admin
      /search?
      /file$
      /static/*.css

    Rejected:
      full URLs
      protocol-relative URLs
      paths not starting with '/'
      whitespace
      backslashes
      traversal segments
    """
    text = _ensure_string(value, label)

    if text.startswith("//"):
        raise RobotsConfigError(f"{label} must not be protocol-relative. Got: {text!r}")
    if "://" in text:
        raise RobotsConfigError(f"{label} must not be an absolute URL. Got: {text!r}")
    if not text.startswith("/"):
        raise RobotsConfigError(f"{label} must start with '/'. Got: {text!r}")
    if "\\" in text:
        raise RobotsConfigError(f"{label} must not contain backslashes. Got: {text!r}")
    if ".." in text:
        raise RobotsConfigError(f"{label} must not contain traversal segments. Got: {text!r}")
    if any(ch.isspace() for ch in text):
        raise RobotsConfigError(f"{label} must not contain whitespace. Got: {text!r}")

    if len(text) > 2048:
        raise RobotsConfigError(
            f"{label} exceeds the maximum supported length (2048)."
        )

    return text


def _normalize_same_origin_sitemap_url(value: Any, base_url: str, label: str) -> str:
    text = _ensure_string(value, label)

    if not _is_absolute_https_url(text):
        raise RobotsConfigError(f"{label} must be an absolute HTTPS URL. Got: {text!r}")
    if not _same_origin(text, base_url):
        raise RobotsConfigError(
            f"{label} must be same-origin as site base_url. Got: {text!r}"
        )
    return text.rstrip("/")


def _normalize_host(value: Any, base_url: str, label: str) -> str:
    """
    Host directive is non-standard and mostly useful for Yandex.
    If provided, it must match the hostname of base_url exactly.
    """
    text = _ensure_string(value, label)
    if "://" in text or "/" in text or "@" in text:
        raise RobotsConfigError(f"{label} must be a plain hostname/netloc, not a URL. Got: {text!r}")

    base_host = urlparse(base_url).netloc
    if text.lower() != base_host.lower():
        raise RobotsConfigError(
            f"{label} must match base_url host exactly. Expected {base_host!r}, got {text!r}"
        )

    return text


# ============================================================================
# Robots config resolution
# ============================================================================

def _resolve_base_url(site_config: Mapping[str, Any]) -> str:
    site_section = _ensure_mapping(site_config.get("site"), "site_config.site")
    raw = site_section.get("base_url")
    if raw is None:
        raise RobotsConfigError("site_config.site.base_url is missing.")
    return _normalize_https_base_url(raw)


def _resolve_robots_config(site_config: Mapping[str, Any]) -> RobotsDocument:
    base_url = _resolve_base_url(site_config)

    robots_node = _get_nested(site_config, ("seo", "robots"), default={})
    if robots_node in (None, {}):
        robots_node = {}
    robots = _ensure_mapping(robots_node, "site_config.seo.robots")

    enabled_raw = robots.get("enabled", True)
    if not isinstance(enabled_raw, bool):
        raise RobotsConfigError("site_config.seo.robots.enabled must be a boolean.")
    enabled = enabled_raw

    comments_raw = robots.get("comments", [])
    comments: List[str] = []
    if comments_raw:
        for idx, item in enumerate(_ensure_list(comments_raw, "site_config.seo.robots.comments")):
            comments.append(_normalize_comment_line(item, f"site_config.seo.robots.comments[{idx}]"))

    groups_raw = robots.get("user_agents")
    if groups_raw is None:
        groups = [
            RobotsGroup(
                name="*",
                allow=["/"],
                disallow=[],
                crawl_delay=None,
            )
        ]
    else:
        groups_list = _ensure_list(groups_raw, "site_config.seo.robots.user_agents")
        if not groups_list:
            raise RobotsConfigError("site_config.seo.robots.user_agents must not be empty when provided.")

        groups = []
        seen_names = set()

        for idx, raw_group in enumerate(groups_list):
            group = _ensure_mapping(raw_group, f"site_config.seo.robots.user_agents[{idx}]")
            name = _ensure_string(group.get("name"), f"site_config.seo.robots.user_agents[{idx}].name")
            if name in seen_names:
                raise RobotsConfigError(
                    f"Duplicate robots user-agent group name detected: {name!r}"
                )
            seen_names.add(name)

            allow_items: List[str] = []
            for allow_idx, item in enumerate(_ensure_list(group.get("allow", []), f"robots.user_agents[{idx}].allow")):
                allow_items.append(
                    _normalize_robot_path(item, f"robots.user_agents[{idx}].allow[{allow_idx}]")
                )

            disallow_items: List[str] = []
            for disallow_idx, item in enumerate(_ensure_list(group.get("disallow", []), f"robots.user_agents[{idx}].disallow")):
                disallow_items.append(
                    _normalize_robot_path(item, f"robots.user_agents[{idx}].disallow[{disallow_idx}]")
                )

            crawl_delay = _ensure_optional_positive_int(
                group.get("crawl_delay"),
                f"robots.user_agents[{idx}].crawl_delay",
            )

            groups.append(
                RobotsGroup(
                    name=name,
                    allow=allow_items,
                    disallow=disallow_items,
                    crawl_delay=crawl_delay,
                )
            )

    canonical_sitemap_url = f"{base_url}/sitemap.xml"

    sitemap_urls: List[str] = [canonical_sitemap_url]
    additional_sitemaps_raw = robots.get("additional_sitemaps", [])
    if additional_sitemaps_raw:
        for idx, item in enumerate(_ensure_list(additional_sitemaps_raw, "site_config.seo.robots.additional_sitemaps")):
            normalized = _normalize_same_origin_sitemap_url(
                item,
                base_url,
                f"site_config.seo.robots.additional_sitemaps[{idx}]",
            )
            if normalized not in sitemap_urls:
                sitemap_urls.append(normalized)

    host_raw = robots.get("host")
    host: Optional[str] = None
    if host_raw is not None:
        host = _normalize_host(host_raw, base_url, "site_config.seo.robots.host")

    return RobotsDocument(
        enabled=enabled,
        comments=comments,
        groups=groups,
        sitemap_urls=sitemap_urls,
        host=host,
    )


# ============================================================================
# Rendering
# ============================================================================

def build_robots_text(site_config: Mapping[str, Any]) -> str:
    document = _resolve_robots_config(site_config)
    lines: List[str] = []

    for comment in document.comments:
        lines.append(f"# {comment}")

    if document.comments:
        lines.append("")

    if not document.enabled:
        lines.append("User-agent: *")
        lines.append("Disallow: /")
        lines.append("")
    else:
        for idx, group in enumerate(document.groups):
            overlap = sorted(set(group.allow) & set(group.disallow))
            if overlap:
                log.warning(
                    "Robots group %r contains identical Allow/Disallow paths: %s",
                    group.name,
                    ", ".join(overlap),
                )

            lines.append(f"User-agent: {group.name}")

            if group.allow:
                for item in group.allow:
                    lines.append(f"Allow: {item}")

            if group.disallow:
                for item in group.disallow:
                    lines.append(f"Disallow: {item}")
            else:
                lines.append("Disallow:")

            if group.crawl_delay is not None:
                lines.append(f"Crawl-delay: {group.crawl_delay}")

            if idx != len(document.groups) - 1:
                lines.append("")

        lines.append("")

    if document.host:
        lines.append(f"Host: {document.host}")

    for sitemap_url in document.sitemap_urls:
        lines.append(f"Sitemap: {sitemap_url}")

    output = "\n".join(lines).rstrip() + "\n"
    if not output.strip():
        raise RobotsConfigError("Generated robots.txt content is empty, which is not allowed.")
    return output


# ============================================================================
# Writing
# ============================================================================

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
            newline="\n",
        ) as tmp:
            tmp.write(content)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_path = Path(tmp.name)

        if tmp_path is None:
            raise RobotsWriteError(f"Failed to create temporary file for {path}")

        tmp_path.replace(path)

    except Exception as exc:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise RobotsWriteError(f"Failed to write robots.txt atomically: {exc}") from exc


def _ensure_safe_output_dir(output_dir: Path) -> Path:
    resolved = output_dir.resolve()
    repo_root = ROOT_DIR.resolve()
    allowed_in_repo_output = DEFAULT_OUTPUT_DIR.resolve()

    if not output_dir.is_absolute():
    raise RobotsWriteError(f"Output directory must be absolute. Got: {output_dir}")

    if str(resolved) == resolved.anchor:
        raise RobotsWriteError(f"Refusing to write robots.txt to filesystem root: {resolved}")

    try:
        resolved.relative_to(repo_root)
        if resolved != allowed_in_repo_output:
            raise RobotsWriteError(
                f"Refusing in-repo output directory outside the sanctioned build target. "
                f"Allowed in-repo output is only: {allowed_in_repo_output} ; got: {resolved}"
            )
    except ValueError:
        pass

    return resolved


def write_robots_file(output_dir: Path, content: str) -> Path:
    safe_output_dir = _ensure_safe_output_dir(output_dir)
    path = safe_output_dir / "robots.txt"
    _atomic_write_text(path, content)
    return path


# ============================================================================
# Public API
# ============================================================================

def generate_robots_file(*, output_dir: Path = DEFAULT_OUTPUT_DIR) -> Path:
    site_config = load_site_config()
    content = build_robots_text(site_config)
    path = write_robots_file(output_dir, content)
    log.info("Generated robots.txt -> %s", path)
    return path


# ============================================================================
# CLI
# ============================================================================

def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate TourVsTravel robots.txt"
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
        help="Print robots.txt to stdout instead of writing the file.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)

    if args.stdout:
        logging.disable(logging.CRITICAL)

    try:
        site_config = load_site_config()
        content = build_robots_text(site_config)

        if args.stdout:
            print(content, end="")
            return 0

        path = write_robots_file(args.output_dir.resolve(), content)
        log.info("robots.txt generation completed successfully: %s", path)
        return 0

    except GenerateRobotsError as exc:
        log.error(str(exc))
        return 1
    except Exception as exc:
        log.exception("Unexpected robots generator failure: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
