"""Claim-level evidence registry and publication projection.

The pilot covers Japan only.  A destination enters this system by being named
as ``pilot_destination`` in both evidence datasets.  Other destinations retain
their current behavior until a later, separately governed audit.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date
from typing import Any, Dict, List, Mapping

from scripts.loaders import load_yaml


SUPPORTED_LANGUAGES = ("en", "ar", "fr", "es", "de", "zh", "ja")
CLAIM_TYPES = {"FACT", "DERIVED", "EDITORIAL_INTERPRETATION", "STRUCTURAL_PRIOR"}
EVIDENCE_STATUSES = {"SUPPORTED", "NARROW", "REPLACE_SOURCE", "RETIRE"}
PUBLICATION_STATES = {"PUBLISHED", "WITHHELD"}


class EvidenceContractError(ValueError):
    pass


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise EvidenceContractError(f"{label} must be a mapping.")
    return value


def _list(value: Any, label: str) -> List[Any]:
    if not isinstance(value, list):
        raise EvidenceContractError(f"{label} must be a list.")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceContractError(f"{label} must be a non-empty string.")
    return value.strip()


def _iso_date(value: Any, label: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    text = _text(value, label)
    try:
        date.fromisoformat(text)
    except ValueError as exc:
        raise EvidenceContractError(f"{label} must be an ISO date: {text!r}") from exc
    return text


def _localized_or_scalar(value: Any, label: str) -> Any:
    if isinstance(value, Mapping):
        missing = set(SUPPORTED_LANGUAGES) - set(value)
        extra = set(value) - set(SUPPORTED_LANGUAGES)
        if missing or extra:
            raise EvidenceContractError(
                f"{label} language keys mismatch; missing={sorted(missing)}, extra={sorted(extra)}"
            )
        return {lang: _text(value[lang], f"{label}.{lang}") for lang in SUPPORTED_LANGUAGES}
    return _text(value, label)


def load_evidence_registry() -> Dict[str, Any]:
    records_root = _mapping(load_yaml("evidence_records.yaml"), "evidence_records")
    claims_root = _mapping(load_yaml("evidence_claims.yaml"), "evidence_claims")
    for root, name in ((records_root, "evidence_records"), (claims_root, "evidence_claims")):
        if root.get("schema_version") != "1.0.0" or root.get("dataset") != name:
            raise EvidenceContractError(f"{name} must declare schema_version 1.0.0 and dataset {name!r}.")

    pilot = _text(claims_root.get("pilot_destination"), "evidence_claims.pilot_destination")
    if records_root.get("pilot_destination") != pilot:
        raise EvidenceContractError("Evidence datasets must name the same pilot_destination.")
    declared_types = set(_list(claims_root.get("claim_types"), "evidence_claims.claim_types"))
    declared_statuses = set(_list(claims_root.get("evidence_statuses"), "evidence_claims.evidence_statuses"))
    declared_states = set(_list(claims_root.get("publication_states"), "evidence_claims.publication_states"))
    if declared_types != CLAIM_TYPES or declared_statuses != EVIDENCE_STATUSES or declared_states != PUBLICATION_STATES:
        raise EvidenceContractError("Evidence schema enumerations must match the application contract exactly.")

    records: Dict[str, Dict[str, Any]] = {}
    for index, raw in enumerate(_list(records_root.get("records"), "evidence_records.records")):
        record = dict(_mapping(raw, f"evidence_records.records[{index}]"))
        evidence_id = _text(record.get("evidence_id"), f"records[{index}].evidence_id")
        if evidence_id in records:
            raise EvidenceContractError(f"Duplicate evidence_id: {evidence_id}")
        for key in ("title", "publisher", "source_url", "source_locator", "geography", "rights_status", "limitations"):
            record[key] = _text(record.get(key), f"records[{index}].{key}")
        if not record["source_url"].startswith("https://"):
            raise EvidenceContractError(f"records[{index}].source_url must use HTTPS.")
        record["retrieved_at"] = _iso_date(record.get("retrieved_at"), f"records[{index}].retrieved_at")
        records[evidence_id] = record

    claims: List[Dict[str, Any]] = []
    ids: set[str] = set()
    paths: set[str] = set()
    for index, raw in enumerate(_list(claims_root.get("claims"), "evidence_claims.claims")):
        claim = dict(_mapping(raw, f"evidence_claims.claims[{index}]"))
        claim_id = _text(claim.get("claim_id"), f"claims[{index}].claim_id")
        source_path = _text(claim.get("source_path"), f"claims[{index}].source_path")
        if claim_id in ids or source_path in paths:
            raise EvidenceContractError(f"Duplicate claim_id or source_path at {claim_id}.")
        ids.add(claim_id)
        paths.add(source_path)
        if claim.get("destination_id") != pilot:
            raise EvidenceContractError(f"{claim_id} must belong to pilot destination {pilot!r}.")
        claim_type = _text(claim.get("claim_type"), f"{claim_id}.claim_type")
        status = _text(claim.get("evidence_status"), f"{claim_id}.evidence_status")
        state = _text(claim.get("publication_state"), f"{claim_id}.publication_state")
        if claim_type not in CLAIM_TYPES or status not in EVIDENCE_STATUSES or state not in PUBLICATION_STATES:
            raise EvidenceContractError(f"{claim_id} uses an unknown claim type, evidence status, or publication state.")
        evidence_ids = [_text(value, f"{claim_id}.evidence_ids[]") for value in _list(
            claim.get("evidence_ids"), f"{claim_id}.evidence_ids"
        )]
        unknown = set(evidence_ids) - set(records)
        if unknown:
            raise EvidenceContractError(f"{claim_id} references unknown evidence: {sorted(unknown)}")
        claim["rationale"] = _text(claim.get("rationale"), f"{claim_id}.rationale")
        claim["reviewer"] = _text(claim.get("reviewer"), f"{claim_id}.reviewer")
        claim["reviewed_at"] = _iso_date(claim.get("reviewed_at"), f"{claim_id}.reviewed_at")
        claim["next_review"] = _iso_date(claim.get("next_review"), f"{claim_id}.next_review", nullable=True)

        if state == "PUBLISHED":
            if status not in {"SUPPORTED", "NARROW"}:
                raise EvidenceContractError(f"{claim_id} cannot be published with status {status}.")
            claim["claim_text"] = _localized_or_scalar(claim.get("claim_text"), f"{claim_id}.claim_text")
            if not evidence_ids:
                raise EvidenceContractError(f"Published material claim {claim_id} requires evidence.")
        else:
            if status not in {"REPLACE_SOURCE", "RETIRE"}:
                raise EvidenceContractError(f"Withheld claim {claim_id} must be REPLACE_SOURCE or RETIRE.")
            if "claim_text" in claim:
                raise EvidenceContractError(f"Withheld claim {claim_id} must not define claim_text.")
        claims.append(claim)

    return {"pilot_destination": pilot, "records": records, "claims": claims}


def derive_material_source_paths(destination: Mapping[str, Any]) -> set[str]:
    """Derive the audit boundary from the governed destination, not the ledger."""
    expected = {field for field in ("summary", "best_seasons") if field in destination}
    if "typical_duration" in destination:
        expected.add("typical_duration")
    family_fit = _mapping(destination.get("family_fit"), "destination.family_fit")
    expected.update(f"family_fit.{key}" for key in family_fit)
    return expected


def apply_evidence_projection(destination: Mapping[str, Any], registry: Mapping[str, Any]) -> Dict[str, Any]:
    """Return the current publishable projection for the audited destination."""
    projected = deepcopy(dict(destination))
    if projected.get("id") != registry["pilot_destination"]:
        return projected
    projected["family_fit"] = dict(projected.get("family_fit", {}))
    projected["evidence_claims"] = []
    for claim in registry["claims"]:
        path = claim["source_path"]
        state = claim["publication_state"]
        if path.startswith("family_fit."):
            key = path.split(".", 1)[1]
            if state == "PUBLISHED":
                projected["family_fit"][key] = claim["claim_text"]
            else:
                projected["family_fit"].pop(key, None)
        elif state == "PUBLISHED":
            projected[path] = deepcopy(claim["claim_text"])
        else:
            projected.pop(path, None)
        projected["evidence_claims"].append({
            "claim_id": claim["claim_id"],
            "source_path": path,
            "claim_type": claim["claim_type"],
            "evidence_status": claim["evidence_status"],
            "publication_state": state,
            "evidence_ids": list(claim["evidence_ids"]),
        })
    projected["evidence_records"] = [dict(record) for record in registry["records"].values()]
    projected["sources"] = [
        {"label": record["title"], "url": record["source_url"], "evidence_id": evidence_id}
        for evidence_id, record in registry["records"].items()
    ]
    return projected


def validate_published_projection(destination: Mapping[str, Any], registry: Mapping[str, Any]) -> None:
    expected_paths = derive_material_source_paths(destination)
    registered_paths = {claim["source_path"] for claim in registry["claims"]}
    if expected_paths != registered_paths:
        raise EvidenceContractError(
            f"Pilot material-claim coverage mismatch; missing={sorted(expected_paths-registered_paths)}, "
            f"unexpected={sorted(registered_paths-expected_paths)}"
        )
    projected = apply_evidence_projection(destination, registry)
    for claim in registry["claims"]:
        path = claim["source_path"]
        if path.startswith("family_fit."):
            present = path.split(".", 1)[1] in projected.get("family_fit", {})
        else:
            present = path in projected
        if present != (claim["publication_state"] == "PUBLISHED"):
            raise EvidenceContractError(f"Publication projection contradicts {claim['claim_id']}.")
