"""Regression gates for crawler-readable social cards and local image assets."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from scripts.build import (
    BuildStepError,
    _verify_social_card_contract,
    _verify_static_asset_references,
    run_build,
)
from scripts.generate_root import build_root_entrypoint_html
from scripts.loaders import load_site_config
from scripts.seo import build_default_social_image_metadata


class RootSocialMetadataTests(unittest.TestCase):
    def test_root_is_readable_without_executing_redirect_scripts(self) -> None:
        config = load_site_config()
        card = build_default_social_image_metadata(config)
        html = build_root_entrypoint_html(config)
        self.assertIn('<meta http-equiv="refresh" content="0; url=/en/">', html)
        self.assertIn('<link rel="canonical" href="https://tourvstravel.com/en/">', html)
        self.assertIn(f'<meta property="og:image" content="{card["image"]}">', html)
        self.assertIn(f'<meta name="twitter:image" content="{card["image"]}">', html)
        self.assertIn('<meta name="twitter:card" content="summary_large_image">', html)
        self.assertIn('<meta property="og:image:width" content="1200">', html)
        self.assertIn('<meta property="og:image:height" content="630">', html)


class PublishedSocialCardContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.directory = tempfile.TemporaryDirectory()
        cls.output = run_build(output_dir=Path(cls.directory.name) / "site")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.directory.cleanup()

    def test_full_multilingual_contract(self) -> None:
        _verify_social_card_contract(self.output)
        _verify_static_asset_references(self.output)

    def test_missing_social_card_cannot_pass(self) -> None:
        card = self.output / "static/img/og/default-og.png"
        missing = card.with_suffix(".unavailable")
        card.rename(missing)
        try:
            with self.assertRaises(BuildStepError):
                _verify_social_card_contract(self.output)
        finally:
            missing.rename(card)

    def test_wrong_dimensions_cannot_pass(self) -> None:
        card = self.output / "static/img/og/default-og.png"
        original = card.read_bytes()
        try:
            card.write_bytes(original[:16] + (1000).to_bytes(4, "big") + original[20:])
            with self.assertRaises(BuildStepError):
                _verify_social_card_contract(self.output)
        finally:
            card.write_bytes(original)

    def test_missing_meta_image_is_a_build_defect(self) -> None:
        page = self.output / "ar/index.html"
        original = page.read_text(encoding="utf-8")
        try:
            page.write_text(original.replace('property="og:image"', 'property="og:unavailable"', 1), encoding="utf-8")
            with self.assertRaises(BuildStepError):
                _verify_social_card_contract(self.output)
        finally:
            page.write_text(original, encoding="utf-8")

    def test_static_reference_gate_checks_meta_content(self) -> None:
        page = self.output / "index.html"
        original = page.read_text(encoding="utf-8")
        try:
            page.write_text(
                original.replace("</head>", '<meta property="og:image" content="/static/img/missing.png">\n</head>'),
                encoding="utf-8",
            )
            with self.assertRaises(BuildStepError):
                _verify_static_asset_references(self.output)
        finally:
            page.write_text(original, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
