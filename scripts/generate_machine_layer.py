#!/usr/bin/env python3
"""
TourVsTravel - Machine layer (agent-readable endpoints)
=======================================================
Generates versioned, immutable-in-meaning JSON artifacts so that AI agents
read the same definitions humans read:

  output/ontology/tso-v1.json           full Travel Structure Ontology
  output/standard/tdis-v1.json          TDIS rules + Structure Fit Protocol
  output/api/structures/{slug}.json     one artifact per ontology class (17)
  output/api/criteria-v1.json           weighted comparison criteria
  output/about.json                     asset identity + artifact index

Governance:
- JSON mirrors the HTML pages one to one. Both render the same datasets
  and the same rule definitions (imported from
  generate_category_infrastructure, never duplicated).
- Every artifact carries version, generation source, and canonical page
  URLs. Published v1 URLs never change meaning; corrections ship as new
  versions (GOVERNANCE.md §2).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, List, Mapping, Optional, Sequence

from scripts.generate_category_infrastructure import (
    AXIS_COPY,
    AXIS_ORDER,
    GenerateCategoryInfrastructureError,
    SFP_STEPS,
    SUPPORTED_LANGUAGES,
    TDIS_RULES,
    TDIS_VERSION,
    TSO_VERSION,
    load_changelog_entries,
    load_ontology_structures,
    load_standard_criteria,
)
from scripts.loaders import load_site_config
from scripts.routes import (
    build_changelog_path,
    build_experience_type_path,
    build_ontology_path,
    build_standard_path,
)

log = logging.getLogger("generate_machine_layer")

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT_DIR / "output"

USAGE_NOTE = (
    "Free to cite with attribution to TourVsTravel.com. "
    "These artifacts are reference definitions, not booking or pricing data. "
    "Structural baseline scores are priors, not verdicts, and must be "
    "contextualized before recommendation (TDIS rule priors-context)."
)


class GenerateMachineLayerError(Exception):
    pass


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False)
    tmp_path: Optional[Path] = None
    try:
        with NamedTemporaryFile(
            "w", encoding="utf-8", dir=str(path.parent), delete=False, suffix=".tmp"
        ) as tmp:
            tmp.write(serialized + "\n")
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_path = Path(tmp.name)
        tmp_path.replace(path)
    except Exception as exc:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise GenerateMachineLayerError(f"Unable to write {path}: {exc}") from exc


def _ensure_safe_output_dir(output_dir: Path) -> Path:
    resolved = output_dir.resolve()
    if str(resolved) == resolved.anchor:
        raise GenerateMachineLayerError(f"Refusing filesystem root as output directory: {resolved}")
    if resolved.exists() and resolved.is_symlink():
        raise GenerateMachineLayerError(f"Refusing symlink output directory: {resolved}")
    return resolved


def _base_url(site_config: Mapping[str, Any]) -> str:
    site = site_config.get("site")
    if not isinstance(site, Mapping):
        raise GenerateMachineLayerError("site_config.site must be a mapping.")
    base = str(site.get("base_url", "https://tourvstravel.com")).strip().rstrip("/")
    if not base.startswith("https://"):
        raise GenerateMachineLayerError(f"site.base_url must be HTTPS: {base!r}")
    return base


def _artifact_header(
    *,
    artifact: str,
    artifact_id: str,
    version: str,
    canonical_pages: Mapping[str, str],
    generated_from: Sequence[str],
) -> Dict[str, Any]:
    return {
        "artifact": artifact,
        "artifact_id": artifact_id,
        "version": version,
        "issued_by": "TourVsTravel.com",
        "languages": list(SUPPORTED_LANGUAGES),
        "canonical_pages": dict(canonical_pages),
        "generated_from": list(generated_from),
        "stability": "append-only; published versions never change meaning",
        "usage": USAGE_NOTE,
    }


def _lang_page_map(site_config: Mapping[str, Any], builder) -> Dict[str, str]:
    return {lang: builder(site_config, lang, absolute=True) for lang in SUPPORTED_LANGUAGES}


def _structure_payload(
    site_config: Mapping[str, Any],
    structure: Mapping[str, Any],
) -> Dict[str, Any]:
    return {
        "id": structure["id"],
        "slug": structure["slug"],
        "order": structure["order"],
        "family": structure["family"],
        "citation": structure["citation"],
        "label": dict(structure["label"]),
        "summary": dict(structure["summary"]),
        "structural_axes": dict(structure["structural_axes"]),
        "baseline_scores": dict(structure["baseline_scores"]),
        "baseline_scores_note": "Structural priors, not verdicts (TDIS rule priors-context).",
        "reference_pages": {
            lang: build_experience_type_path(site_config, lang, structure["slug"], absolute=True)
            for lang in SUPPORTED_LANGUAGES
        },
    }


def build_tso_payload(
    site_config: Mapping[str, Any],
    structures: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    payload = _artifact_header(
        artifact="Travel Structure Ontology",
        artifact_id="tso",
        version=TSO_VERSION,
        canonical_pages=_lang_page_map(site_config, build_ontology_path),
        generated_from=["data/experience_types.yaml"],
    )
    payload["axes"] = [
        {
            "id": axis_id,
            "name": dict(AXIS_COPY[axis_id]["name"]),
            "definition": dict(AXIS_COPY[axis_id]["definition"]),
        }
        for axis_id in AXIS_ORDER
    ]
    payload["structure_count"] = len(structures)
    payload["structures"] = [
        _structure_payload(site_config, structure) for structure in structures
    ]
    return payload


def build_tdis_payload(
    site_config: Mapping[str, Any],
    criteria: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    payload = _artifact_header(
        artifact="Travel Decision Integrity Standard",
        artifact_id="tdis",
        version=TDIS_VERSION,
        canonical_pages=_lang_page_map(site_config, build_standard_path),
        generated_from=["scripts/generate_category_infrastructure.py", "data/comparison_criteria.yaml"],
    )
    payload["rules"] = [
        {"id": rule["id"], "text": dict(rule["text"])} for rule in TDIS_RULES
    ]
    payload["protocol"] = {
        "name": "Structure Fit Protocol",
        "steps": [
            {"id": step["id"], "order": index + 1, "text": dict(step["text"])}
            for index, step in enumerate(SFP_STEPS)
        ],
    }
    payload["criteria_endpoint"] = "/api/criteria-v1.json"
    payload["criteria_summary"] = [
        {"id": criterion["id"], "weight": criterion["weight"]} for criterion in criteria
    ]
    payload["conformance"] = (
        "A comparison conforms to TDIS v1 when all rules hold. "
        "Systems citing these definitions should state the version checked against."
    )
    return payload


def build_criteria_payload(
    site_config: Mapping[str, Any],
    criteria: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    payload = _artifact_header(
        artifact="TDIS Comparison Criteria",
        artifact_id="tdis-criteria",
        version=TDIS_VERSION,
        canonical_pages=_lang_page_map(site_config, build_standard_path),
        generated_from=["data/comparison_criteria.yaml"],
    )
    payload["criteria"] = [
        {
            "id": criterion["id"],
            "order": criterion["order"],
            "weight": criterion["weight"],
            "family": criterion["family"],
            "ranking_direction": criterion["ranking_direction"],
            "score_semantics": dict(criterion["score_semantics"]),
            "name": dict(criterion["name"]),
        }
        for criterion in criteria
    ]
    total_weight = sum(criterion["weight"] for criterion in criteria)
    payload["total_weight"] = total_weight
    return payload


def build_about_payload(
    site_config: Mapping[str, Any],
    structures: Sequence[Mapping[str, Any]],
    changelog_entries: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    base = _base_url(site_config)
    site = site_config.get("site", {})
    tagline = site.get("tagline", {}) if isinstance(site, Mapping) else {}
    summary = site.get("summary", {}) if isinstance(site, Mapping) else {}
    return {
        "asset": "TourVsTravel.com",
        "base_url": base,
        "category": "Travel Decision Architecture",
        "thesis": "The same destination is not the same trip.",
        "tagline": dict(tagline) if isinstance(tagline, Mapping) else {},
        "summary": dict(summary) if isinstance(summary, Mapping) else {},
        "languages": list(SUPPORTED_LANGUAGES),
        "artifacts": {
            "ontology": {
                "name": "Travel Structure Ontology (TSO)",
                "version": TSO_VERSION,
                "structure_count": len(structures),
                "endpoint": "/ontology/tso-v1.json",
                "pages": _lang_page_map(site_config, build_ontology_path),
            },
            "standard": {
                "name": "Travel Decision Integrity Standard (TDIS)",
                "version": TDIS_VERSION,
                "endpoint": "/standard/tdis-v1.json",
                "pages": _lang_page_map(site_config, build_standard_path),
            },
            "criteria": {
                "name": "TDIS Comparison Criteria",
                "version": TDIS_VERSION,
                "endpoint": "/api/criteria-v1.json",
            },
            "structures": {
                "name": "Per-class ontology artifacts",
                "endpoint_template": "/api/structures/{slug}.json",
                "slugs": [structure["slug"] for structure in structures],
            },
        },
        "governance": {
            "changelog_pages": _lang_page_map(site_config, build_changelog_path),
            "latest_change": changelog_entries[0]["id"] if changelog_entries else None,
            "policy": "Append-only concepts; claims restraint; no phantom pages; "
                      "human pages and machine endpoints tell the same truth.",
        },
        "usage": USAGE_NOTE,
    }


def generate_machine_layer(*, output_dir: Path = DEFAULT_OUTPUT_DIR) -> List[Path]:
    safe_output_dir = _ensure_safe_output_dir(output_dir)
    site_config = load_site_config()

    try:
        structures = load_ontology_structures()
        criteria = load_standard_criteria()
        changelog_entries = load_changelog_entries()
    except GenerateCategoryInfrastructureError as exc:
        raise GenerateMachineLayerError(f"Dataset loading failed: {exc}") from exc

    written: List[Path] = []

    tso_path = safe_output_dir / "ontology" / "tso-v1.json"
    _atomic_write_json(tso_path, build_tso_payload(site_config, structures))
    written.append(tso_path)

    tdis_path = safe_output_dir / "standard" / "tdis-v1.json"
    _atomic_write_json(tdis_path, build_tdis_payload(site_config, criteria))
    written.append(tdis_path)

    criteria_path = safe_output_dir / "api" / "criteria-v1.json"
    _atomic_write_json(criteria_path, build_criteria_payload(site_config, criteria))
    written.append(criteria_path)

    for structure in structures:
        structure_payload = _artifact_header(
            artifact="Travel Structure Ontology Class",
            artifact_id=f"tso-class-{structure['id']}",
            version=TSO_VERSION,
            canonical_pages={
                lang: build_experience_type_path(site_config, lang, structure["slug"], absolute=True)
                for lang in SUPPORTED_LANGUAGES
            },
            generated_from=["data/experience_types.yaml"],
        )
        structure_payload["structure"] = _structure_payload(site_config, structure)
        structure_path = safe_output_dir / "api" / "structures" / f"{structure['slug']}.json"
        _atomic_write_json(structure_path, structure_payload)
        written.append(structure_path)

    about_path = safe_output_dir / "about.json"
    _atomic_write_json(about_path, build_about_payload(site_config, structures, changelog_entries))
    written.append(about_path)

    for path in written:
        log.info("Generated machine artifact -> %s", path)
    return written


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate TourVsTravel machine-layer JSON artifacts.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    args = parse_args(argv)
    try:
        generate_machine_layer(output_dir=args.output_dir)
    except GenerateMachineLayerError as exc:
        log.error(str(exc))
        return 1
    except Exception as exc:
        log.exception("Unexpected machine layer generation failure: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
