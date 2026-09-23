"""Regression coverage for the Japan Evidence Closure Pilot 01 release gate."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import evidence
from scripts.build import (
    DESTINATIONS_V1_SHA256,
    BuildStepError,
    _verify_evidence_claim_contract,
    _verify_machine_layer_contract,
    run_build,
)
from scripts.generate_machine_layer import _atomic_write_json
from scripts.loaders import load_destinations, load_yaml


class EvidenceRegistryNegativeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.records = load_yaml("evidence_records.yaml")
        self.claims = load_yaml("evidence_claims.yaml")

    def assert_registry_rejected(self, records: dict, claims: dict) -> None:
        with patch("scripts.evidence.load_yaml", side_effect=lambda name: records if name == "evidence_records.yaml" else claims):
            with self.assertRaises(evidence.EvidenceContractError):
                evidence.load_evidence_registry()

    def test_missing_material_claim_coverage_is_rejected(self) -> None:
        registry = evidence.load_evidence_registry()
        japan = next(item for item in load_destinations() if item["id"] == "japan")
        registry["claims"] = registry["claims"][1:]
        with self.assertRaises(evidence.EvidenceContractError):
            evidence.validate_published_projection(japan, registry)

    def test_new_raw_family_path_is_rejected(self) -> None:
        registry = evidence.load_evidence_registry()
        japan = deepcopy(next(item for item in load_destinations() if item["id"] == "japan"))
        japan["family_fit"]["new_family"] = "high"
        with self.assertRaises(evidence.EvidenceContractError):
            evidence.validate_published_projection(japan, registry)

    def test_unknown_evidence_id_is_rejected(self) -> None:
        claims = deepcopy(self.claims)
        claims["claims"][0]["evidence_ids"] = ["unknown"]
        self.assert_registry_rejected(self.records, claims)

    def test_published_claim_without_evidence_is_rejected(self) -> None:
        claims = deepcopy(self.claims)
        claims["claims"][0]["evidence_ids"] = []
        self.assert_registry_rejected(self.records, claims)

    def test_invalid_disposition_is_rejected(self) -> None:
        claims = deepcopy(self.claims)
        claims["claims"][0]["evidence_status"] = "RETIRE"
        self.assert_registry_rejected(self.records, claims)

    def test_missing_localized_claim_language_is_rejected(self) -> None:
        claims = deepcopy(self.claims)
        del claims["claims"][0]["claim_text"]["ja"]
        self.assert_registry_rejected(self.records, claims)

    def test_duplicate_claim_id_or_source_path_is_rejected(self) -> None:
        claims = deepcopy(self.claims)
        claims["claims"][1]["claim_id"] = claims["claims"][0]["claim_id"]
        self.assert_registry_rejected(self.records, claims)
        claims = deepcopy(self.claims)
        claims["claims"][1]["source_path"] = claims["claims"][0]["source_path"]
        self.assert_registry_rejected(self.records, claims)


class GeneratedContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.output = run_build(output_dir=Path(cls.temp_dir.name) / "site")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp_dir.cleanup()

    def mutate_and_expect_rejection(self, relative_path: str, mutation, verifier) -> None:
        path = self.output / relative_path
        original = path.read_bytes()
        try:
            path.write_bytes(mutation(original))
            with self.assertRaises(BuildStepError):
                verifier(self.output)
        finally:
            path.write_bytes(original)

    def test_json_is_deterministic_lf_and_v1_hash_is_canonical(self) -> None:
        v1 = (self.output / "api" / "destinations-v1.json").read_bytes()
        self.assertNotIn(b"\r\n", v1)
        self.assertTrue(v1.endswith(b"\n"))
        self.assertEqual(hashlib.sha256(v1).hexdigest(), DESTINATIONS_V1_SHA256)
        self.assertEqual(DESTINATIONS_V1_SHA256, "3b76bb8f4f20aca5c9f617ef0a159967087a704bb6d1857a646bcefbb3fb2f9a")
        with tempfile.TemporaryDirectory() as directory:
            left = Path(directory) / "left.json"
            right = Path(directory) / "right.json"
            _atomic_write_json(left, {"é": [1, 2]})
            _atomic_write_json(right, {"é": [1, 2]})
            self.assertEqual(left.read_bytes(), right.read_bytes())

    def test_v1_byte_drift_and_v2_evidence_drift_are_rejected(self) -> None:
        self.mutate_and_expect_rejection("api/destinations-v1.json", lambda data: data + b" ", _verify_machine_layer_contract)
        def alter_v2(data: bytes) -> bytes:
            payload = json.loads(data)
            payload["destinations"][0]["evidence_records"][0]["source_url"] = "https://invalid.example/"
            return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        self.mutate_and_expect_rejection("api/destinations-v2.json", alter_v2, _verify_evidence_claim_contract)

    def test_only_japan_has_markers_and_non_japan_marker_is_rejected(self) -> None:
        for lang in ("en", "ar", "fr", "es", "de", "zh", "ja"):
            japan = (self.output / lang / "destinations" / "japan" / "index.html").read_text(encoding="utf-8")
            self.assertEqual(japan.count('data-evidence-family-id="'), 2)
            for destination in load_destinations():
                if destination["id"] != "japan":
                    page = (self.output / lang / "destinations" / destination["id"] / "index.html").read_text(encoding="utf-8")
                    self.assertNotIn("data-evidence-", page)
        self.mutate_and_expect_rejection(
            "en/destinations/spain/index.html",
            lambda data: data.replace(b"<li>", b'<li data-evidence-family-id="bad">', 1),
            _verify_evidence_claim_contract,
        )
