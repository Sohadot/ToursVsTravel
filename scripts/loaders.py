#!/usr/bin/env python3
"""
TourVsTravel — Strict YAML Loaders & Validators
===============================================

A sovereign-grade loader layer for:
- secure YAML loading from /data only
- strict schema validation
- early failure on ambiguity
- normalized access structures for generators

Design goals:
- fail closed, not fail open
- zero silent fallbacks for core config
- zero path traversal
- strict multilingual completeness where required
- strict scoring band coverage
- strict tool schema consistency
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Sequence, Set, Tuple
from urllib.parse import urlparse
import logging
import yaml


# ============================================================================
# Logging
# ============================================================================

log = logging.getLogger(__name__)


# ============================================================================
# Exceptions
# ============================================================================

class LoaderError(Exception):
    """Base loader exception."""


class DataFileNotFoundError(LoaderError):
    """Raised when a required YAML file does not exist."""


class ConfigValidationError(LoaderError):
    """Raised when configuration validation fails."""


# ============================================================================
# Paths / Limits
# ============================================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

MAX_YAML_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MiB
ALLOWED_YAML_SUFFIXES = {".yaml", ".yml"}


# ============================================================================
# Generic YAML Loading
# ============================================================================

def _raise(message: str) -> None:
    raise ConfigValidationError(message)


def _path(path: Sequence[str | int]) -> str:
    parts: List[str] = []
    for item in path:
        if isinstance(item, int):
            parts.append(f"[{item}]")
        else:
            if not parts:
                parts.append(str(item))
            else:
                parts.append(f".{item}")
    return "".join(parts)


def _ensure_mapping(value: Any, path: Sequence[str | int]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _raise(f"{_path(path)} must be a mapping/object.")
    return value


def _ensure_mutable_mapping(value: Any, path: Sequence[str | int]) -> MutableMapping[str, Any]:
    if not isinstance(value, MutableMapping):
        _raise(f"{_path(path)} must be a mutable mapping/object.")
    return value


def _ensure_list(value: Any, path: Sequence[str | int]) -> List[Any]:
    if not isinstance(value, list):
        _raise(f"{_path(path)} must be a list.")
    return value


def _ensure_string(value: Any, path: Sequence[str | int], allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        _raise(f"{_path(path)} must be a string.")
    if not allow_empty and not value.strip():
        _raise(f"{_path(path)} must not be empty.")
    return value


def _ensure_bool(value: Any, path: Sequence[str | int]) -> bool:
    if not isinstance(value, bool):
        _raise(f"{_path(path)} must be a boolean.")
    return value


def _ensure_int(value: Any, path: Sequence[str | int]) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        _raise(f"{_path(path)} must be an integer.")
    return value


def _require_keys(mapping: Mapping[str, Any], required_keys: Set[str], path: Sequence[str | int]) -> None:
    missing = required_keys - set(mapping.keys())
    if missing:
        _raise(f"{_path(path)} is missing required key(s): {', '.join(sorted(missing))}")


def _forbid_unknown_keys(
    mapping: Mapping[str, Any],
    allowed_keys: Set[str],
    path: Sequence[str | int],
    enabled: bool = True,
) -> None:
    if not enabled:
        return
    unknown = set(mapping.keys()) - allowed_keys
    if unknown:
        _raise(f"{_path(path)} contains unknown key(s): {', '.join(sorted(unknown))}")


def _ensure_language_map(
    value: Any,
    required_languages: Sequence[str],
    path: Sequence[str | int],
    *,
    allow_empty_values: bool = False,
) -> Mapping[str, str]:
    mapping = _ensure_mapping(value, path)
    missing = [lang for lang in required_languages if lang not in mapping]
    if missing:
        _raise(f"{_path(path)} is missing required language(s): {', '.join(missing)}")

    for lang in required_languages:
        _ensure_string(mapping[lang], [*path, lang], allow_empty=allow_empty_values)

    return mapping


def _safe_data_path(filename: str) -> Path:
    filename_str = _ensure_string(filename, ["load_yaml", "filename"])
    candidate = (DATA_DIR / filename_str).resolve()
    data_root = DATA_DIR.resolve()

    if candidate.suffix.lower() not in ALLOWED_YAML_SUFFIXES:
        raise DataFileNotFoundError(f"Illegal file type requested: {filename_str}")

    try:
        candidate.relative_to(data_root)
    except ValueError as exc:
        raise DataFileNotFoundError(f"Illegal path outside data directory: {filename_str}") from exc

    return candidate


def _read_yaml(path: Path) -> Any:
    if not path.exists():
        raise DataFileNotFoundError(f"Missing data file: {path}")
    if not path.is_file():
        raise DataFileNotFoundError(f"Expected file, found non-file path: {path}")

    file_size = path.stat().st_size
    if file_size > MAX_YAML_FILE_SIZE_BYTES:
        raise ConfigValidationError(
            f"YAML file exceeds maximum allowed size ({MAX_YAML_FILE_SIZE_BYTES} bytes): {path}"
        )

    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    if data is None:
        raise ConfigValidationError(f"YAML file is empty: {path}")

    return data


def load_yaml(filename: str) -> Any:
    return _read_yaml(_safe_data_path(filename))


# ============================================================================
# URL Validation
# ============================================================================

def _is_absolute_https_url(value: str) -> bool:
    parsed = urlparse(value)
    return (
        parsed.scheme == "https"
        and bool(parsed.netloc)
        and parsed.username is None
        and parsed.password is None
    )


def _validate_absolute_https_url(value: str, path: Sequence[str | int]) -> None:
    if not _is_absolute_https_url(value):
        _raise(f"{_path(path)} must be an absolute HTTPS URL without embedded credentials.")


# ============================================================================
# Site Config Validation
# ============================================================================

_SITE_TOP_LEVEL_KEYS = {
    "site",
    "branding",
    "languages",
    "routes",
    "seo",
    "ui",
    "defaults",
}


def validate_site_config(config: Any) -> Dict[str, Any]:
    root = _ensure_mutable_mapping(config, ["site_config"])
    _forbid_unknown_keys(root, _SITE_TOP_LEVEL_KEYS, ["site_config"], enabled=True)
    _require_keys(root, _SITE_TOP_LEVEL_KEYS, ["site_config"])

    site = _ensure_mapping(root["site"], ["site_config", "site"])
    _require_keys(site, {"name", "domain", "base_url", "tagline", "summary"}, ["site_config", "site"])
    _ensure_string(site["name"], ["site_config", "site", "name"])
    _validate_absolute_https_url(_ensure_string(site["domain"], ["site_config", "site", "domain"]), ["site_config", "site", "domain"])
    _validate_absolute_https_url(_ensure_string(site["base_url"], ["site_config", "site", "base_url"]), ["site_config", "site", "base_url"])

    languages = _ensure_list(root["languages"], ["site_config", "languages"])
    if not languages:
        _raise("site_config.languages must contain at least one language.")

    required_site_lang_keys = {"code", "hreflang", "locale", "dir", "native_name", "label", "enabled"}
    seen_codes: Set[str] = set()
    enabled_languages: List[str] = []

    for idx, lang_item in enumerate(languages):
        lang = _ensure_mapping(lang_item, ["site_config", "languages", idx])
        _require_keys(lang, required_site_lang_keys, ["site_config", "languages", idx])

        code = _ensure_string(lang["code"], ["site_config", "languages", idx, "code"])
        if code in seen_codes:
            _raise(f"Duplicate language code found in site_config.languages: {code}")
        seen_codes.add(code)

        _ensure_string(lang["hreflang"], ["site_config", "languages", idx, "hreflang"])
        _ensure_string(lang["locale"], ["site_config", "languages", idx, "locale"])

        direction = _ensure_string(lang["dir"], ["site_config", "languages", idx, "dir"])
        if direction not in {"ltr", "rtl"}:
            _raise(f"{_path(['site_config', 'languages', idx, 'dir'])} must be 'ltr' or 'rtl'.")

        _ensure_string(lang["native_name"], ["site_config", "languages", idx, "native_name"])
        _ensure_string(lang["label"], ["site_config", "languages", idx, "label"])

        enabled = _ensure_bool(lang["enabled"], ["site_config", "languages", idx, "enabled"])
        if enabled:
            enabled_languages.append(code)

    if not enabled_languages:
        _raise("site_config.languages must have at least one enabled language.")

    _ensure_language_map(site["tagline"], enabled_languages, ["site_config", "site", "tagline"])
    _ensure_language_map(site["summary"], enabled_languages, ["site_config", "site", "summary"])

    branding = _ensure_mapping(root["branding"], ["site_config", "branding"])
    _require_keys(branding, {"colors", "logo", "wordmark"}, ["site_config", "branding"])

    seo = _ensure_mapping(root["seo"], ["site_config", "seo"])
    _require_keys(
        seo,
        {
            "robots_directive",
            "og_type",
            "twitter_card",
            "default_og_image",
            "theme_color",
            "hreflang",
            "title_templates",
            "description_templates",
        },
        ["site_config", "seo"],
    )
    _validate_absolute_https_url(
        _ensure_string(seo["default_og_image"], ["site_config", "seo", "default_og_image"]),
        ["site_config", "seo", "default_og_image"],
    )

    hreflang = _ensure_mapping(seo["hreflang"], ["site_config", "seo", "hreflang"])
    _require_keys(hreflang, {"include_x_default", "x_default_lang"}, ["site_config", "seo", "hreflang"])
    _ensure_bool(hreflang["include_x_default"], ["site_config", "seo", "hreflang", "include_x_default"])
    x_default_lang = _ensure_string(hreflang["x_default_lang"], ["site_config", "seo", "hreflang", "x_default_lang"])
    if x_default_lang not in seen_codes:
        _raise("site_config.seo.hreflang.x_default_lang must match an existing site language code.")

    return dict(root)


def load_site_config() -> Dict[str, Any]:
    log.info("Loading site_config.yaml")
    raw = load_yaml("site_config.yaml")
    validated = validate_site_config(raw)
    log.info("Loaded site_config.yaml successfully")
    return validated


# ============================================================================
# Tools Config Validation
# ============================================================================

_TOOLS_TOP_LEVEL_KEYS = {
    "schema",
    "settings",
    "shared_text",
    "shared",
    "tools",
    "guardrails",
}

_SCHEMA_KEYS = {
    "file_id",
    "schema_version",
    "strict_mode",
    "required_languages",
    "validation",
}

_SETTINGS_KEYS = {
    "disabled_tools_build_behavior",
    "canonical_tool_path_template",
    "public_tools_order",
}

_SHARED_TEXT_KEYS = {
    "affiliate_disclosure_label",
    "affiliate_disclosure_text",
    "precision_warning_text",
}

_SHARED_KEYS = {
    "input_types",
    "enums",
}

_INPUT_TYPE_KEYS = {
    "value_kind",
    "allow_unknown_values",
    "requires_enum_id",
    "requires_min_selections",
    "requires_max_selections",
    "value_source",
    "validation",
}

_VALUE_SOURCE_KEYS = {
    "file",
    "collection",
    "value_field",
    "label_field",
}

_VALUE_SOURCE_VALIDATION_KEYS = {
    "require_existing_value",
}

_TOOL_KEYS = {
    "id",
    "version",
    "publication",
    "routing",
    "category",
    "priority",
    "name",
    "short_description",
    "long_description",
    "primary_cta",
    "inputs",
    "outputs",
    "evaluation_model",
    "data_dependencies",
    "external_resources",
    "trust_policy",
    "seo",
}

_PUBLICATION_KEYS = {
    "status",
    "build_visibility",
    "interactive",
    "evergreen",
    "shareable",
    "indexable",
    "uses_live_data",
}

_ROUTING_KEYS = {
    "slug",
    "path_template",
}

_INPUT_KEYS = {
    "key",
    "type_id",
    "enum_id",
    "required",
    "validation",
}

_INPUT_VALIDATION_KEYS = {
    "min",
    "max",
    "min_selections",
    "max_selections",
}

_OUTPUT_KEYS = {
    "primary_output",
    "secondary_outputs",
}

_EVALUATION_MODEL_KEYS = {
    "mode",
    "engine",
    "score_range",
    "score_bands",
    "ranking",
    "precision",
}

_SCORE_RANGE_KEYS = {
    "min",
    "max",
}

_SCORE_BAND_KEYS = {
    "key",
    "min",
    "max",
}

_RANKING_KEYS = {
    "enabled",
    "max_results",
}

_PRECISION_KEYS = {
    "type",
    "show_precision_warning",
    "warning_text",
}

_DEPENDENCY_KEYS = {
    "file",
    "required",
}

_EXTERNAL_RESOURCES_KEYS = {
    "official_links",
    "affiliate",
    "external_url_policy",
}

_OFFICIAL_LINKS_KEYS = {
    "enabled",
    "preferred",
}

_AFFILIATE_KEYS = {
    "enabled",
    "providers",
    "disclosure",
}

_DISCLOSURE_KEYS = {
    "required",
    "label",
    "text",
    "position",
}

_EXTERNAL_URL_POLICY_KEYS = {
    "require_https",
    "allow_relative_urls",
    "rel_attributes",
}

_TRUST_POLICY_KEYS = {
    "claim_live_pricing",
    "claim_real_time_availability",
    "claim_medical_or_psychological_diagnosis",
    "require_explanation_layer",
    "require_disclaimer",
    "require_affiliate_disclosure",
    "require_official_source_routing",
}

_SEO_KEYS = {
    "title_template",
    "description_template",
}

_GUARDRAILS_KEYS = {
    "no_live_data",
    "no_fake_precision",
    "require_explanation_layer",
    "require_source_routing_when_externalized",
    "affiliate_links_must_be_disclosed",
    "official_sources_preferred",
}


def _validate_tools_schema(root: Mapping[str, Any]) -> Tuple[List[str], Mapping[str, Any]]:
    schema = _ensure_mapping(root["schema"], ["tools_config", "schema"])
    _forbid_unknown_keys(schema, _SCHEMA_KEYS, ["tools_config", "schema"], enabled=True)
    _require_keys(schema, _SCHEMA_KEYS, ["tools_config", "schema"])

    _ensure_string(schema["file_id"], ["tools_config", "schema", "file_id"])
    _ensure_string(schema["schema_version"], ["tools_config", "schema", "schema_version"])
    _ensure_bool(schema["strict_mode"], ["tools_config", "schema", "strict_mode"])

    required_languages = _ensure_list(schema["required_languages"], ["tools_config", "schema", "required_languages"])
    if not required_languages:
        _raise("tools_config.schema.required_languages must contain at least one language.")

    normalized_languages: List[str] = []
    for idx, lang in enumerate(required_languages):
        normalized_languages.append(_ensure_string(lang, ["tools_config", "schema", "required_languages", idx]))

    validation = _ensure_mapping(schema["validation"], ["tools_config", "schema", "validation"])
    return normalized_languages, validation


def _validate_shared_texts(shared_text: Mapping[str, Any], required_languages: Sequence[str]) -> None:
    _forbid_unknown_keys(shared_text, _SHARED_TEXT_KEYS, ["tools_config", "shared_text"], enabled=True)
    _require_keys(shared_text, _SHARED_TEXT_KEYS, ["tools_config", "shared_text"])
    for key in _SHARED_TEXT_KEYS:
        _ensure_language_map(shared_text[key], required_languages, ["tools_config", "shared_text", key])


def _validate_shared_types(shared: Mapping[str, Any], validation_flags: Mapping[str, Any]) -> None:
    _forbid_unknown_keys(shared, _SHARED_KEYS, ["tools_config", "shared"], enabled=True)
    _require_keys(shared, _SHARED_KEYS, ["tools_config", "shared"])

    input_types = _ensure_mapping(shared["input_types"], ["tools_config", "shared", "input_types"])
    enums = _ensure_mapping(shared["enums"], ["tools_config", "shared", "enums"])

    for type_name, type_def in input_types.items():
        type_mapping = _ensure_mapping(type_def, ["tools_config", "shared", "input_types", type_name])
        _forbid_unknown_keys(
            type_mapping,
            _INPUT_TYPE_KEYS,
            ["tools_config", "shared", "input_types", type_name],
            enabled=True,
        )
        _require_keys(type_mapping, {"value_kind", "allow_unknown_values"}, ["tools_config", "shared", "input_types", type_name])

    if bool(validation_flags.get("fail_on_empty_required_options_source", True)):
        if "destination_select" not in input_types:
            _raise("tools_config.shared.input_types must define 'destination_select'.")

        dest_select = _ensure_mapping(
            input_types["destination_select"],
            ["tools_config", "shared", "input_types", "destination_select"],
        )
        _require_keys(dest_select, {"value_source", "validation"}, ["tools_config", "shared", "input_types", "destination_select"])

        value_source = _ensure_mapping(dest_select["value_source"], ["tools_config", "shared", "input_types", "destination_select", "value_source"])
        _forbid_unknown_keys(
            value_source,
            _VALUE_SOURCE_KEYS,
            ["tools_config", "shared", "input_types", "destination_select", "value_source"],
            enabled=True,
        )
        _require_keys(value_source, _VALUE_SOURCE_KEYS, ["tools_config", "shared", "input_types", "destination_select", "value_source"])

        for key in _VALUE_SOURCE_KEYS:
            _ensure_string(value_source[key], ["tools_config", "shared", "input_types", "destination_select", "value_source", key])

        validation = _ensure_mapping(dest_select["validation"], ["tools_config", "shared", "input_types", "destination_select", "validation"])
        _forbid_unknown_keys(
            validation,
            _VALUE_SOURCE_VALIDATION_KEYS,
            ["tools_config", "shared", "input_types", "destination_select", "validation"],
            enabled=True,
        )
        _require_keys(validation, _VALUE_SOURCE_VALIDATION_KEYS, ["tools_config", "shared", "input_types", "destination_select", "validation"])
        _ensure_bool(validation["require_existing_value"], ["tools_config", "shared", "input_types", "destination_select", "validation", "require_existing_value"])

    for enum_name, enum_values in enums.items():
        values = _ensure_list(enum_values, ["tools_config", "shared", "enums", enum_name])
        if not values:
            _raise(f"tools_config.shared.enums.{enum_name} must not be empty.")
        seen: Set[str] = set()
        for idx, item in enumerate(values):
            enum_value = _ensure_string(item, ["tools_config", "shared", "enums", enum_name, idx])
            if enum_value in seen:
                _raise(f"Duplicate value '{enum_value}' in tools_config.shared.enums.{enum_name}")
            seen.add(enum_value)


def _validate_score_bands(
    bands: List[Any],
    score_min: int,
    score_max: int,
    path: Sequence[str | int],
    validation_flags: Mapping[str, Any],
) -> None:
    if not bands:
        return

    validated_bands: List[Tuple[int, int]] = []

    for idx, band_item in enumerate(bands):
        band = _ensure_mapping(band_item, [*path, idx])
        _forbid_unknown_keys(band, _SCORE_BAND_KEYS, [*path, idx], enabled=True)
        _require_keys(band, _SCORE_BAND_KEYS, [*path, idx])

        _ensure_string(band["key"], [*path, idx, "key"])
        bmin = _ensure_int(band["min"], [*path, idx, "min"])
        bmax = _ensure_int(band["max"], [*path, idx, "max"])

        if bmin > bmax:
            _raise(f"{_path([*path, idx])} has min greater than max.")
        if bmin < score_min or bmax > score_max:
            _raise(f"{_path([*path, idx])} is outside score_range bounds.")

        validated_bands.append((bmin, bmax))

    sorted_bands = sorted(validated_bands, key=lambda x: x[0])

    if bool(validation_flags.get("fail_on_invalid_score_band_order", True)):
        if sorted_bands != validated_bands:
            _raise(f"{_path(path)} must be ordered by ascending min values.")

    if bool(validation_flags.get("fail_on_scoring_gaps", True)):
        expected = score_min
        for current_min, current_max in sorted_bands:
            if current_min != expected:
                _raise(f"{_path(path)} contains a scoring gap or overlap near score {expected}.")
            expected = current_max + 1
        if expected != score_max + 1:
            _raise(f"{_path(path)} does not cover full score_range through {score_max}.")


def _validate_tool(
    tool: Mapping[str, Any],
    idx: int,
    required_languages: Sequence[str],
    validation_flags: Mapping[str, Any],
    shared_input_types: Mapping[str, Any],
    shared_enums: Mapping[str, Any],
) -> None:
    tool_path = ["tools_config", "tools", idx]

    _forbid_unknown_keys(tool, _TOOL_KEYS, tool_path, enabled=True)
    _require_keys(tool, _TOOL_KEYS, tool_path)

    _ensure_string(tool["id"], [*tool_path, "id"])
    _ensure_string(tool["version"], [*tool_path, "version"])
    _ensure_string(tool["category"], [*tool_path, "category"])
    _ensure_int(tool["priority"], [*tool_path, "priority"])

    publication = _ensure_mapping(tool["publication"], [*tool_path, "publication"])
    _forbid_unknown_keys(publication, _PUBLICATION_KEYS, [*tool_path, "publication"], enabled=True)
    _require_keys(publication, _PUBLICATION_KEYS, [*tool_path, "publication"])
    for key in _PUBLICATION_KEYS:
        if key in {"status", "build_visibility"}:
            _ensure_string(publication[key], [*tool_path, "publication", key])
        else:
            _ensure_bool(publication[key], [*tool_path, "publication", key])

    routing = _ensure_mapping(tool["routing"], [*tool_path, "routing"])
    _forbid_unknown_keys(routing, _ROUTING_KEYS, [*tool_path, "routing"], enabled=True)
    _require_keys(routing, _ROUTING_KEYS, [*tool_path, "routing"])
    _ensure_string(routing["slug"], [*tool_path, "routing", "slug"])
    _ensure_string(routing["path_template"], [*tool_path, "routing", "path_template"])

    for key in ("name", "short_description", "long_description", "primary_cta"):
        _ensure_language_map(tool[key], required_languages, [*tool_path, key])

    inputs = _ensure_list(tool["inputs"], [*tool_path, "inputs"])
    if not inputs:
        _raise(f"{_path([*tool_path, 'inputs'])} must not be empty.")

    for input_idx, input_item in enumerate(inputs):
        input_path = [*tool_path, "inputs", input_idx]
        input_def = _ensure_mapping(input_item, input_path)
        _forbid_unknown_keys(input_def, _INPUT_KEYS, input_path, enabled=True)

        _require_keys(input_def, {"key", "type_id", "required"}, input_path)

        _ensure_string(input_def["key"], [*input_path, "key"])
        type_id = _ensure_string(input_def["type_id"], [*input_path, "type_id"])
        _ensure_bool(input_def["required"], [*input_path, "required"])

        if type_id not in shared_input_types:
            _raise(f"{_path([*input_path, 'type_id'])} references unknown input type '{type_id}'.")

        type_schema = _ensure_mapping(shared_input_types[type_id], ["tools_config", "shared", "input_types", type_id])

        needs_enum = bool(type_schema.get("requires_enum_id", False))
        if needs_enum:
            if "enum_id" not in input_def:
                _raise(f"{_path(input_path)} requires enum_id because type_id='{type_id}'.")
            enum_id = _ensure_string(input_def["enum_id"], [*input_path, "enum_id"])
            if enum_id not in shared_enums:
                _raise(f"{_path([*input_path, 'enum_id'])} references unknown enum '{enum_id}'.")

        validation = input_def.get("validation")
        if type_id in {"integer", "enum_multi_select"} and validation is None:
            _raise(f"{_path(input_path)} must define validation for type_id='{type_id}'.")

        if validation is not None:
            validation_map = _ensure_mapping(validation, [*input_path, "validation"])
            _forbid_unknown_keys(validation_map, _INPUT_VALIDATION_KEYS, [*input_path, "validation"], enabled=True)

            if type_id == "integer":
                _require_keys(validation_map, {"min", "max"}, [*input_path, "validation"])
                vmin = _ensure_int(validation_map["min"], [*input_path, "validation", "min"])
                vmax = _ensure_int(validation_map["max"], [*input_path, "validation", "max"])
                if vmin > vmax:
                    _raise(f"{_path([*input_path, 'validation'])} has min greater than max.")

            if type_id == "enum_multi_select":
                _require_keys(validation_map, {"min_selections", "max_selections"}, [*input_path, "validation"])
                vmin = _ensure_int(validation_map["min_selections"], [*input_path, "validation", "min_selections"])
                vmax = _ensure_int(validation_map["max_selections"], [*input_path, "validation", "max_selections"])
                if vmin < 1:
                    _raise(f"{_path([*input_path, 'validation', 'min_selections'])} must be >= 1.")
                if vmin > vmax:
                    _raise(f"{_path([*input_path, 'validation'])} has min_selections greater than max_selections.")

    outputs = _ensure_mapping(tool["outputs"], [*tool_path, "outputs"])
    _forbid_unknown_keys(outputs, _OUTPUT_KEYS, [*tool_path, "outputs"], enabled=True)
    _require_keys(outputs, _OUTPUT_KEYS, [*tool_path, "outputs"])
    _ensure_string(outputs["primary_output"], [*tool_path, "outputs", "primary_output"])
    secondary = _ensure_list(outputs["secondary_outputs"], [*tool_path, "outputs", "secondary_outputs"])
    for out_idx, output_name in enumerate(secondary):
        _ensure_string(output_name, [*tool_path, "outputs", "secondary_outputs", out_idx])

    evaluation_model = _ensure_mapping(tool["evaluation_model"], [*tool_path, "evaluation_model"])
    _forbid_unknown_keys(evaluation_model, _EVALUATION_MODEL_KEYS, [*tool_path, "evaluation_model"], enabled=True)
    _require_keys(evaluation_model, _EVALUATION_MODEL_KEYS, [*tool_path, "evaluation_model"])

    _ensure_string(evaluation_model["mode"], [*tool_path, "evaluation_model", "mode"])
    _ensure_string(evaluation_model["engine"], [*tool_path, "evaluation_model", "engine"])

    score_range = evaluation_model["score_range"]
    if score_range is not None:
        score_range_map = _ensure_mapping(score_range, [*tool_path, "evaluation_model", "score_range"])
        _forbid_unknown_keys(score_range_map, _SCORE_RANGE_KEYS, [*tool_path, "evaluation_model", "score_range"], enabled=True)
        _require_keys(score_range_map, _SCORE_RANGE_KEYS, [*tool_path, "evaluation_model", "score_range"])
        score_min = _ensure_int(score_range_map["min"], [*tool_path, "evaluation_model", "score_range", "min"])
        score_max = _ensure_int(score_range_map["max"], [*tool_path, "evaluation_model", "score_range", "max"])
        if score_min > score_max:
            _raise(f"{_path([*tool_path, 'evaluation_model', 'score_range'])} has min greater than max.")
    else:
        score_min = None
        score_max = None

    score_bands = _ensure_list(evaluation_model["score_bands"], [*tool_path, "evaluation_model", "score_bands"])
    if score_bands and (score_min is None or score_max is None):
        _raise(f"{_path([*tool_path, 'evaluation_model'])} defines score_bands but score_range is null.")
    if score_min is not None and score_max is not None:
        _validate_score_bands(score_bands, score_min, score_max, [*tool_path, "evaluation_model", "score_bands"], validation_flags)

    ranking = _ensure_mapping(evaluation_model["ranking"], [*tool_path, "evaluation_model", "ranking"])
    _forbid_unknown_keys(ranking, _RANKING_KEYS, [*tool_path, "evaluation_model", "ranking"], enabled=True)
    _require_keys(ranking, _RANKING_KEYS, [*tool_path, "evaluation_model", "ranking"])
    _ensure_bool(ranking["enabled"], [*tool_path, "evaluation_model", "ranking", "enabled"])
    _ensure_int(ranking["max_results"], [*tool_path, "evaluation_model", "ranking", "max_results"])

    precision = _ensure_mapping(evaluation_model["precision"], [*tool_path, "evaluation_model", "precision"])
    _forbid_unknown_keys(precision, _PRECISION_KEYS, [*tool_path, "evaluation_model", "precision"], enabled=True)
    _require_keys(precision, {"type", "show_precision_warning"}, [*tool_path, "evaluation_model", "precision"])
    _ensure_string(precision["type"], [*tool_path, "evaluation_model", "precision", "type"])
    show_warning = _ensure_bool(precision["show_precision_warning"], [*tool_path, "evaluation_model", "precision", "show_precision_warning"])
    if show_warning:
        if "warning_text" not in precision:
            _raise(f"{_path([*tool_path, 'evaluation_model', 'precision'])} must include warning_text when show_precision_warning=true.")
        _ensure_language_map(precision["warning_text"], required_languages, [*tool_path, "evaluation_model", "precision", "warning_text"])

    dependencies = _ensure_list(tool["data_dependencies"], [*tool_path, "data_dependencies"])
    if not dependencies:
        _raise(f"{_path([*tool_path, 'data_dependencies'])} must not be empty.")

    for dep_idx, dep_item in enumerate(dependencies):
        dep_path = [*tool_path, "data_dependencies", dep_idx]
        dep = _ensure_mapping(dep_item, dep_path)
        _forbid_unknown_keys(dep, _DEPENDENCY_KEYS, dep_path, enabled=True)
        _require_keys(dep, _DEPENDENCY_KEYS, dep_path)

        dep_file = _ensure_string(dep["file"], [*dep_path, "file"])
        _ensure_bool(dep["required"], [*dep_path, "required"])

        if bool(validation_flags.get("fail_on_circular_self_dependency", True)):
            if dep_file == "tools_config.yaml":
                _raise(f"{_path(dep_path)} must not self-reference tools_config.yaml.")

        if dep["required"]:
            _safe_data_path(dep_file)

    external_resources = _ensure_mapping(tool["external_resources"], [*tool_path, "external_resources"])
    _forbid_unknown_keys(external_resources, _EXTERNAL_RESOURCES_KEYS, [*tool_path, "external_resources"], enabled=True)
    _require_keys(external_resources, _EXTERNAL_RESOURCES_KEYS, [*tool_path, "external_resources"])

    official_links = _ensure_mapping(external_resources["official_links"], [*tool_path, "external_resources", "official_links"])
    _forbid_unknown_keys(official_links, _OFFICIAL_LINKS_KEYS, [*tool_path, "external_resources", "official_links"], enabled=True)
    _require_keys(official_links, _OFFICIAL_LINKS_KEYS, [*tool_path, "external_resources", "official_links"])
    _ensure_bool(official_links["enabled"], [*tool_path, "external_resources", "official_links", "enabled"])
    _ensure_bool(official_links["preferred"], [*tool_path, "external_resources", "official_links", "preferred"])

    affiliate = _ensure_mapping(external_resources["affiliate"], [*tool_path, "external_resources", "affiliate"])
    _forbid_unknown_keys(affiliate, _AFFILIATE_KEYS, [*tool_path, "external_resources", "affiliate"], enabled=True)
    _require_keys(affiliate, _AFFILIATE_KEYS, [*tool_path, "external_resources", "affiliate"])
    affiliate_enabled = _ensure_bool(affiliate["enabled"], [*tool_path, "external_resources", "affiliate", "enabled"])
    providers = _ensure_list(affiliate["providers"], [*tool_path, "external_resources", "affiliate", "providers"])
    for prov_idx, provider in enumerate(providers):
        _ensure_string(provider, [*tool_path, "external_resources", "affiliate", "providers", prov_idx])

    disclosure = _ensure_mapping(affiliate["disclosure"], [*tool_path, "external_resources", "affiliate", "disclosure"])
    _forbid_unknown_keys(disclosure, _DISCLOSURE_KEYS, [*tool_path, "external_resources", "affiliate", "disclosure"], enabled=True)
    _require_keys(disclosure, _DISCLOSURE_KEYS, [*tool_path, "external_resources", "affiliate", "disclosure"])
    disclosure_required = _ensure_bool(disclosure["required"], [*tool_path, "external_resources", "affiliate", "disclosure", "required"])

    if affiliate_enabled:
        if not providers:
            _raise(f"{_path([*tool_path, 'external_resources', 'affiliate'])} has affiliate enabled but providers is empty.")
        if bool(validation_flags.get("fail_on_missing_affiliate_disclosure_when_affiliate_enabled", True)):
            if not disclosure_required:
                _raise(f"{_path([*tool_path, 'external_resources', 'affiliate', 'disclosure', 'required'])} must be true when affiliate is enabled.")
            _ensure_language_map(disclosure["label"], required_languages, [*tool_path, "external_resources", "affiliate", "disclosure", "label"])
            _ensure_language_map(disclosure["text"], required_languages, [*tool_path, "external_resources", "affiliate", "disclosure", "text"])
            _ensure_string(disclosure["position"], [*tool_path, "external_resources", "affiliate", "disclosure", "position"])
    else:
        if disclosure_required:
            _raise(f"{_path([*tool_path, 'external_resources', 'affiliate', 'disclosure', 'required'])} cannot be true when affiliate is disabled.")

    external_url_policy = _ensure_mapping(external_resources["external_url_policy"], [*tool_path, "external_resources", "external_url_policy"])
    _forbid_unknown_keys(external_url_policy, _EXTERNAL_URL_POLICY_KEYS, [*tool_path, "external_resources", "external_url_policy"], enabled=True)
    _require_keys(external_url_policy, _EXTERNAL_URL_POLICY_KEYS, [*tool_path, "external_resources", "external_url_policy"])
    _ensure_bool(external_url_policy["require_https"], [*tool_path, "external_resources", "external_url_policy", "require_https"])
    _ensure_bool(external_url_policy["allow_relative_urls"], [*tool_path, "external_resources", "external_url_policy", "allow_relative_urls"])
    rel_attributes = _ensure_list(external_url_policy["rel_attributes"], [*tool_path, "external_resources", "external_url_policy", "rel_attributes"])
    for rel_idx, rel_value in enumerate(rel_attributes):
        _ensure_string(rel_value, [*tool_path, "external_resources", "external_url_policy", "rel_attributes", rel_idx])

    trust_policy = _ensure_mapping(tool["trust_policy"], [*tool_path, "trust_policy"])
    _forbid_unknown_keys(trust_policy, _TRUST_POLICY_KEYS, [*tool_path, "trust_policy"], enabled=True)
    _require_keys(trust_policy, _TRUST_POLICY_KEYS, [*tool_path, "trust_policy"])
    for trust_key in _TRUST_POLICY_KEYS:
        _ensure_bool(trust_policy[trust_key], [*tool_path, "trust_policy", trust_key])

    if affiliate_enabled and not trust_policy["require_affiliate_disclosure"]:
        _raise(f"{_path([*tool_path, 'trust_policy', 'require_affiliate_disclosure'])} must be true when affiliate is enabled.")

    seo = _ensure_mapping(tool["seo"], [*tool_path, "seo"])
    _forbid_unknown_keys(seo, _SEO_KEYS, [*tool_path, "seo"], enabled=True)
    _require_keys(seo, _SEO_KEYS, [*tool_path, "seo"])
    _ensure_language_map(seo["title_template"], required_languages, [*tool_path, "seo", "title_template"])
    _ensure_language_map(seo["description_template"], required_languages, [*tool_path, "seo", "description_template"])


def validate_tools_config(config: Any) -> Dict[str, Any]:
    root = _ensure_mutable_mapping(config, ["tools_config"])
    _forbid_unknown_keys(root, _TOOLS_TOP_LEVEL_KEYS, ["tools_config"], enabled=True)
    _require_keys(root, _TOOLS_TOP_LEVEL_KEYS, ["tools_config"])

    required_languages, validation_flags = _validate_tools_schema(root)

    settings = _ensure_mapping(root["settings"], ["tools_config", "settings"])
    _forbid_unknown_keys(settings, _SETTINGS_KEYS, ["tools_config", "settings"], enabled=True)
    _require_keys(settings, _SETTINGS_KEYS, ["tools_config", "settings"])
    _ensure_string(settings["disabled_tools_build_behavior"], ["tools_config", "settings", "disabled_tools_build_behavior"])
    _ensure_string(settings["canonical_tool_path_template"], ["tools_config", "settings", "canonical_tool_path_template"])
    public_tools_order = _ensure_list(settings["public_tools_order"], ["tools_config", "settings", "public_tools_order"])

    shared_text = _ensure_mapping(root["shared_text"], ["tools_config", "shared_text"])
    _validate_shared_texts(shared_text, required_languages)

    shared = _ensure_mapping(root["shared"], ["tools_config", "shared"])
    _validate_shared_types(shared, validation_flags)

    guardrails = _ensure_mapping(root["guardrails"], ["tools_config", "guardrails"])
    _forbid_unknown_keys(guardrails, _GUARDRAILS_KEYS, ["tools_config", "guardrails"], enabled=True)
    _require_keys(guardrails, _GUARDRAILS_KEYS, ["tools_config", "guardrails"])
    for key in _GUARDRAILS_KEYS:
        _ensure_bool(guardrails[key], ["tools_config", "guardrails", key])

    tools = _ensure_list(root["tools"], ["tools_config", "tools"])
    if not tools:
        _raise("tools_config.tools must not be empty.")

    shared_input_types = _ensure_mapping(shared["input_types"], ["tools_config", "shared", "input_types"])
    shared_enums = _ensure_mapping(shared["enums"], ["tools_config", "shared", "enums"])

    seen_ids: Set[str] = set()
    seen_slugs: Set[str] = set()

    for idx, tool_item in enumerate(tools):
        tool = _ensure_mapping(tool_item, ["tools_config", "tools", idx])

        tool_id = tool.get("id")
        if isinstance(tool_id, str):
            if tool_id in seen_ids and bool(validation_flags.get("fail_on_duplicate_tool_ids", True)):
                _raise(f"Duplicate tool id detected: {tool_id}")
            seen_ids.add(tool_id)

        routing = tool.get("routing")
        if isinstance(routing, Mapping):
            tool_slug = routing.get("slug")
            if isinstance(tool_slug, str):
                if tool_slug in seen_slugs and bool(validation_flags.get("fail_on_duplicate_tool_slugs", True)):
                    _raise(f"Duplicate tool slug detected: {tool_slug}")
                seen_slugs.add(tool_slug)

        _validate_tool(
            tool,
            idx,
            required_languages=required_languages,
            validation_flags=validation_flags,
            shared_input_types=shared_input_types,
            shared_enums=shared_enums,
        )

    known_tool_ids = {tool["id"] for tool in tools if isinstance(tool, Mapping) and "id" in tool}
    seen_public_order: Set[str] = set()
    for idx, tool_id in enumerate(public_tools_order):
        value = _ensure_string(tool_id, ["tools_config", "settings", "public_tools_order", idx])
        if value in seen_public_order:
            _raise(f"Duplicate tool id '{value}' inside tools_config.settings.public_tools_order")
        seen_public_order.add(value)
        if value not in known_tool_ids:
            _raise(f"tools_config.settings.public_tools_order references unknown tool id '{value}'.")

    return dict(root)


def load_tools_config() -> Dict[str, Any]:
    log.info("Loading tools_config.yaml")
    raw = load_yaml("tools_config.yaml")
    validated = validate_tools_config(raw)

    tools = _ensure_list(validated["tools"], ["tools_config", "tools"])

    tools_by_id: Dict[str, Dict[str, Any]] = {}
    tools_by_slug: Dict[str, Dict[str, Any]] = {}

    for idx, tool in enumerate(tools):
        tool_mapping = _ensure_mapping(tool, ["tools_config", "tools", idx])

        tool_id = _ensure_string(tool_mapping["id"], ["tools_config", "tools", idx, "id"])
        routing = _ensure_mapping(tool_mapping["routing"], ["tools_config", "tools", idx, "routing"])
        slug = _ensure_string(routing["slug"], ["tools_config", "tools", idx, "routing", "slug"])

        tools_by_id[tool_id] = dict(tool_mapping)
        tools_by_slug[slug] = dict(tool_mapping)

    validated["tools_by_id"] = tools_by_id
    validated["tools_by_slug"] = tools_by_slug
    validated["active_public_tools"] = [
        tool
        for tool in tools
        if tool["publication"]["status"] == "active"
        and tool["publication"]["build_visibility"] == "public"
    ]

    log.info("Loaded tools_config.yaml successfully")
    return validated


# ============================================================================
# Domain Data Validation
# ============================================================================

def _validate_unique_ids(items: List[Any], root_key: str) -> None:
    seen: Set[str] = set()
    for idx, item in enumerate(items):
        mapping = _ensure_mapping(item, [root_key, idx])
        if "id" not in mapping:
            _raise(f"{root_key}[{idx}] is missing required key 'id'.")
        item_id = _ensure_string(mapping["id"], [root_key, idx, "id"])
        if item_id in seen:
            _raise(f"Duplicate id '{item_id}' found in {root_key}.")
        seen.add(item_id)


def _validate_unique_comparison_keys(items: List[Any]) -> None:
    seen: Set[Tuple[str, str, str]] = set()

    for idx, item in enumerate(items):
        mapping = _ensure_mapping(item, ["comparisons", idx])

        required_keys = {"destination_id", "experience_a", "experience_b"}
        _require_keys(mapping, required_keys, ["comparisons", idx])

        destination_id = _ensure_string(mapping["destination_id"], ["comparisons", idx, "destination_id"])
        experience_a = _ensure_string(mapping["experience_a"], ["comparisons", idx, "experience_a"])
        experience_b = _ensure_string(mapping["experience_b"], ["comparisons", idx, "experience_b"])

        composite_key = (destination_id, experience_a, experience_b)
        if composite_key in seen:
            _raise(
                "Duplicate comparison key found in comparisons.yaml: "
                f"{destination_id} | {experience_a} | {experience_b}"
            )
        seen.add(composite_key)


def load_destinations() -> List[Dict[str, Any]]:
    log.info("Loading destinations.yaml")
    raw = load_yaml("destinations.yaml")
    root = _ensure_mapping(raw, ["destinations_yaml"])
    if "destinations" not in root:
        _raise("destinations.yaml must contain top-level key 'destinations'.")
    items = _ensure_list(root["destinations"], ["destinations_yaml", "destinations"])
    _validate_unique_ids(items, "destinations")
    log.info("Loaded destinations.yaml successfully")
    return [dict(item) for item in items]


def load_experience_types() -> List[Dict[str, Any]]:
    log.info("Loading experience_types.yaml")
    raw = load_yaml("experience_types.yaml")
    root = _ensure_mapping(raw, ["experience_types_yaml"])
    if "experience_types" not in root:
        _raise("experience_types.yaml must contain top-level key 'experience_types'.")
    items = _ensure_list(root["experience_types"], ["experience_types_yaml", "experience_types"])
    _validate_unique_ids(items, "experience_types")
    log.info("Loaded experience_types.yaml successfully")
    return [dict(item) for item in items]


def load_comparisons() -> List[Dict[str, Any]]:
    log.info("Loading comparisons.yaml")
    raw = load_yaml("comparisons.yaml")
    root = _ensure_mapping(raw, ["comparisons_yaml"])

    if "comparisons" not in root:
        _raise("comparisons.yaml must contain top-level key 'comparisons'.")

    items = _ensure_list(root["comparisons"], ["comparisons_yaml", "comparisons"])
    _validate_unique_comparison_keys(items)

    log.info("Loaded comparisons.yaml successfully")
    return [dict(item) for item in items]


def load_comparison_criteria() -> Dict[str, Any]:
    log.info("Loading comparison_criteria.yaml")
    raw = load_yaml("comparison_criteria.yaml")
    root = _ensure_mapping(raw, ["comparison_criteria_yaml"])

    if "criteria" not in root:
        _raise("comparison_criteria.yaml must contain top-level key 'criteria'.")

    criteria = _ensure_list(root["criteria"], ["comparison_criteria_yaml", "criteria"])
    _validate_unique_ids(criteria, "criteria")

    log.info("Loaded comparison_criteria.yaml successfully")
    return dict(root)


# ============================================================================
# Bundled Core Loader
# ============================================================================

def load_core_data_bundle() -> Dict[str, Any]:
    """
    Load the core site configuration and main domain data files.

    Returns:
        {
            "site_config": ...,
            "tools_config": ...,
            "destinations": ...,
            "experience_types": ...,
            "comparisons": ...,
            "comparison_criteria": ...
        }
    """
    log.info("Loading core data bundle...")

    site_config = load_site_config()
    tools_config = load_tools_config()
    destinations = load_destinations()
    experience_types = load_experience_types()
    comparisons = load_comparisons()
    comparison_criteria = load_comparison_criteria()

    bundle = {
        "site_config": site_config,
        "tools_config": tools_config,
        "destinations": destinations,
        "experience_types": experience_types,
        "comparisons": comparisons,
        "comparison_criteria": comparison_criteria,
    }

    log.info("Core data bundle loaded successfully")
    return bundle
