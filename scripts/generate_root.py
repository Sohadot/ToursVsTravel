#!/usr/bin/env python3
"""
TourVsTravel — Root Entrypoint Generator
========================================

Purpose
-------
Generate a root-level entrypoint:

    output/index.html

The root entrypoint prevents the production domain root from returning 404 and
redirects users to the canonical default language route:

    /en/

Design principles
-----------------
- compatible with the strict build.py staging pipeline
- writes to the output_dir provided by the caller
- atomic write
- deterministic output
- strict base URL handling
- safe HTML escaping
- no direct dependency on browser behavior alone
"""

from __future__ import annotations

import argparse
import html
import logging
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Mapping, Optional, Sequence
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

log = logging.getLogger("generate_root")


# ============================================================================
# Paths
# ============================================================================

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "output"
DEFAULT_LANG = "en"


# ============================================================================
# Exceptions
# ============================================================================

class GenerateRootError(Exception):
    """Raised when root entrypoint generation fails."""


class RootConfigError(GenerateRootError):
    """Raised when root entrypoint configuration is invalid."""


class RootWriteError(GenerateRootError):
    """Raised when root entrypoint writing fails."""


# ============================================================================
# Validation helpers
# ============================================================================

def _ensure_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RootConfigError(f"{label} must be a mapping/object.")
    return value


def _ensure_string(value: Any, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise RootConfigError(f"{label} must be a string.")

    text = value.strip()

    if not allow_empty and not text:
        raise RootConfigError(f"{label} must not be empty.")

    return text


def _load_yaml_file(path: Path) -> Any:
    if not path.exists():
        raise RootConfigError(f"Missing required YAML file: {path}")

    if not path.is_file():
        raise RootConfigError(f"YAML path is not a file: {path}")

    try:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except yaml.YAMLError as exc:
        raise RootConfigError(f"Invalid YAML in {path}: {exc}") from exc
    except OSError as exc:
        raise RootConfigError(f"Unable to read YAML file {path}: {exc}") from exc

    if data is None:
        raise RootConfigError(f"YAML file is empty: {path}")

    return data


def load_site_config() -> Mapping[str, Any]:
    path = DATA_DIR / "site_config.yaml"
    config = _load_yaml_file(path)

    if not isinstance(config, Mapping):
        raise RootConfigError("data/site_config.yaml must contain a top-level mapping/object.")

    if "site" not in config:
        raise RootConfigError("site_config.yaml must contain top-level key 'site'.")

    if "languages" not in config:
        raise RootConfigError("site_config.yaml must contain top-level key 'languages'.")

    return config


def _normalize_https_base_url(value: Any) -> str:
    text = _ensure_string(value, "site.base_url")
    parsed = urlparse(text)

    if parsed.scheme.lower() != "https":
        raise RootConfigError(f"site.base_url must use HTTPS. Got: {text!r}")

    if not parsed.netloc:
        raise RootConfigError(f"site.base_url must be an absolute HTTPS URL. Got: {text!r}")

    if parsed.username is not None or parsed.password is not None:
        raise RootConfigError("site.base_url must not contain embedded credentials.")

    if parsed.query or parsed.fragment:
        raise RootConfigError("site.base_url must not contain query parameters or fragments.")

    if (parsed.path or "") not in ("", "/"):
        raise RootConfigError(f"site.base_url must not contain a path. Got: {text!r}")

    return f"https://{parsed.netloc.rstrip('/')}"


def _validate_lang_code(value: str) -> str:
    text = _ensure_string(value, "default_lang")

    if not text.isascii():
        raise RootConfigError("default_lang must be ASCII.")

    if not text.replace("-", "").isalnum():
        raise RootConfigError("default_lang must contain only letters, numbers, or hyphen.")

    if len(text) > 12:
        raise RootConfigError("default_lang is unexpectedly long.")

    return text


def _resolve_site_name(site_config: Mapping[str, Any], default_lang: str) -> str:
    site = _ensure_mapping(site_config.get("site"), "site")
    raw_name = site.get("name")

    if isinstance(raw_name, str):
        return raw_name.strip() or "TourVsTravel"

    if isinstance(raw_name, Mapping):
        candidate = raw_name.get(default_lang) or raw_name.get("en")
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()

    return "TourVsTravel"


def _extract_enabled_language_codes(site_config: Mapping[str, Any]) -> list[str]:
    languages = site_config.get("languages")

    enabled_codes: list[str] = []

    if isinstance(languages, list):
        for idx, item in enumerate(languages):
            if not isinstance(item, Mapping):
                raise RootConfigError(f"site_config.languages[{idx}] must be a mapping/object.")

            code = item.get("code")
            enabled = item.get("enabled", True)

            if isinstance(code, str) and enabled is True:
                enabled_codes.append(code.strip())

        return enabled_codes

    if isinstance(languages, Mapping):
        for code, item in languages.items():
            if not isinstance(code, str):
                raise RootConfigError("site_config.languages mapping keys must be strings.")

            if isinstance(item, Mapping):
                enabled = item.get("enabled", True)
                if enabled is True:
                    enabled_codes.append(code.strip())
            elif item is True:
                enabled_codes.append(code.strip())

        return enabled_codes

    raise RootConfigError("site_config.languages must be either a list or mapping/object.")


def _ensure_default_language_enabled(site_config: Mapping[str, Any], default_lang: str) -> None:
    enabled_codes = _extract_enabled_language_codes(site_config)

    if default_lang not in enabled_codes:
        raise RootConfigError(
            f"Default root language {default_lang!r} is not enabled. "
            f"Enabled languages: {', '.join(enabled_codes) or 'none'}"
        )


def _ensure_safe_output_dir(output_dir: Path) -> Path:
    resolved = output_dir.resolve()

    if not resolved.is_absolute():
        raise RootWriteError(f"Output directory must resolve to an absolute path: {output_dir}")

    if str(resolved) == resolved.anchor:
        raise RootWriteError(f"Refusing to write root entrypoint to filesystem root: {resolved}")

    if resolved.exists() and resolved.is_symlink():
        raise RootWriteError(f"Refusing symlink output directory: {resolved}")

    parent = resolved.parent

    if parent.exists() and parent.is_symlink():
        raise RootWriteError(f"Refusing output directory with symlink parent: {parent}")

    return resolved


# ============================================================================
# Atomic writing
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
        ) as tmp:
            tmp.write(content)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_path = Path(tmp.name)

        if tmp_path is None:
            raise RootWriteError(f"Failed to create temporary file for {path}")

        tmp_path.replace(path)

    except Exception:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise


# ============================================================================
# Rendering
# ============================================================================

def build_root_entrypoint_html(
    site_config: Mapping[str, Any],
    *,
    default_lang: str = DEFAULT_LANG,
) -> str:
    default_lang = _validate_lang_code(default_lang)
    _ensure_default_language_enabled(site_config, default_lang)

    site = _ensure_mapping(site_config.get("site"), "site")

    base_url = _normalize_https_base_url(
        site.get("base_url", "https://tourvstravel.com")
    )

    site_name = _resolve_site_name(site_config, default_lang)

    target_path = f"/{default_lang}/"
    canonical_url = f"{base_url}{target_path}"

    safe_lang = html.escape(default_lang, quote=True)
    safe_site_name = html.escape(site_name, quote=True)
    safe_target_path = html.escape(target_path, quote=True)
    safe_canonical_url = html.escape(canonical_url, quote=True)

    return f"""<!DOCTYPE html>
<html lang="{safe_lang}">
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="0; url={safe_target_path}">
  <meta name="robots" content="noindex, follow">
  <link rel="canonical" href="{safe_canonical_url}">
  <title>{safe_site_name}</title>
  <script>
    window.location.replace("{safe_target_path}");
  </script>
</head>
<body>
  <main>
    <p>Redirecting to <a href="{safe_target_path}">{safe_site_name}</a>.</p>
  </main>
</body>
</html>
"""


# ============================================================================
# Public API
# ============================================================================

def generate_root_entrypoint(
    *,
    site_config: Optional[Mapping[str, Any]] = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    default_lang: str = DEFAULT_LANG,
) -> Path:
    config = site_config if site_config is not None else load_site_config()

    if not isinstance(config, Mapping):
        raise RootConfigError("site_config must be a mapping/object.")

    safe_output_dir = _ensure_safe_output_dir(output_dir)

    html_output = build_root_entrypoint_html(
        config,
        default_lang=default_lang,
    )

    output_path = safe_output_dir / "index.html"

    _atomic_write_text(output_path, html_output)

    log.info("Generated root entrypoint -> %s", output_path)

    return output_path


# ============================================================================
# CLI
# ============================================================================

def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate TourVsTravel root entrypoint index.html."
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Output directory root. Default: ./output",
    )

    parser.add_argument(
        "--default-lang",
        type=str,
        default=DEFAULT_LANG,
        help="Default language route to redirect root traffic to. Default: en.",
    )

    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)

    try:
        generate_root_entrypoint(
            output_dir=args.output_dir,
            default_lang=args.default_lang,
        )
    except GenerateRootError as exc:
        log.error(str(exc))
        return 1
    except Exception as exc:
        log.exception("Unexpected root entrypoint generator failure: %s", exc)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
