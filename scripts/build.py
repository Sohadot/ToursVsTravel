#!/usr/bin/env python3
"""
TourVsTravel — Production Build Orchestrator
============================================

Purpose
-------
Run the complete local and CI build pipeline for TourVsTravel.

This file is the official build orchestrator. It does not generate content
directly. It coordinates approved generators in a strict order, writes everything
to a temporary staging directory, validates the generated output contract, and
then promotes the stage into the final output directory.

Production output contract
--------------------------
A successful build must produce at least:

    output/index.html
    output/en/index.html
    output/ar/index.html
    output/fr/index.html
    output/es/index.html
    output/de/index.html
    output/zh/index.html
    output/ja/index.html

    output/en/methodology/index.html
    output/en/styles/guided-group-tour/index.html
    output/en/report/index.html

    output/static/css/main.css
    output/static/js/main.js
    output/robots.txt
    output/sitemap.xml
    output/.nojekyll

Design principles
-----------------
- no partial production builds
- no direct writes to output/ before staging validation
- no publishing broken output
- no silent failure
- no symlink-based static asset copying
- no broken root entrypoint
- no relative static asset paths in generated HTML
- no known-bad language root links such as /en/.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import shutil
import tempfile
import time
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import List, Optional, Sequence
from urllib.parse import urlsplit


from scripts.generate_root import GenerateRootError, generate_root_entrypoint
from scripts.generate_home import GenerateHomeError, generate_home_pages
from scripts.generate_methodology import GenerateMethodologyError, generate_methodology_pages
from scripts.generate_styles_index import (
    GenerateStylesIndexError,
    generate_styles_index_pages,
)
from scripts.generate_compare import GenerateCompareError, generate_compare_pages
from scripts.generate_tools import GenerateToolsError, generate_tools_pages
from scripts.generate_find_your_match import (
    GenerateFindYourMatchError,
    generate_find_your_match_pages,
)
from scripts.generate_destinations import (
    GenerateDestinationsError,
    generate_destinations_pages,
)
from scripts.generate_report import GenerateReportError, generate_report_pages
from scripts.generate_contact import GenerateContactError, generate_contact_pages
from scripts.generate_about import GenerateAboutError, generate_about_pages
from scripts.generate_privacy import GeneratePrivacyError, generate_privacy_pages
from scripts.generate_acquire import GenerateAcquireError, generate_acquire_pages
from scripts.generate_source_policy import (
    GenerateSourcePolicyError,
    generate_source_policy_pages,
)
from scripts.generate_editorial_standards import (
    GenerateEditorialStandardsError,
    generate_editorial_standards_pages,
)
from scripts.generate_travel_decision_architecture import (
    GenerateTravelDecisionArchitectureError,
    generate_travel_decision_architecture_pages,
)
from scripts.generate_experience_types import (
    GenerateExperienceTypesError,
    generate_experience_type_pages,
)
from scripts.generate_destination_pages import (
    GenerateDestinationPagesError,
    generate_destination_detail_pages,
    load_governed_destinations,
)
from scripts.generate_compass import (
    GenerateCompassError,
    generate_compass_pages,
)
from scripts.generate_category_infrastructure import (
    CATEGORY_INFRASTRUCTURE_ENGLISH_FRAGMENTS,
    GenerateCategoryInfrastructureError,
    generate_category_infrastructure_pages,
)
from scripts.generate_machine_layer import (
    GenerateMachineLayerError,
    generate_machine_layer,
)
from scripts.generate_robots import GenerateRobotsError, generate_robots_file
from scripts.generate_sitemap import GenerateSitemapError, generate_sitemap_file
from scripts.generate_travel_decision_architecture import ENGLISH_SECTIONS as TDA_ENGLISH_SECTIONS
from scripts.trust_authority_copy import TRUST_PAGE_COPY


# ============================================================================
# Logging
# ============================================================================

log = logging.getLogger("build")


def configure_logging(*, verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO

    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=level,
            format="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S",
        )
    else:
        logging.getLogger().setLevel(level)


# ============================================================================
# Paths and constants
# ============================================================================

ROOT_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT_DIR / "static"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "output"

SUPPORTED_LANGUAGES = ("en", "ar", "fr", "es", "de", "zh", "ja")
DEFAULT_ROOT_LANG = "en"
EXPECTED_EXPERIENCE_TYPE_COUNT = 17

REFERENCE_PAGE_PATHS = {
    "about": "{lang}/about/index.html",
    "acquire": "{lang}/acquire/index.html",
    "travel_decision_architecture": "{lang}/travel-decision-architecture/index.html",
    "source_policy": "{lang}/methodology/source-policy/index.html",
    "editorial_standards": "{lang}/methodology/editorial-standards/index.html",
    "privacy": "{lang}/privacy/index.html",
    "contact": "{lang}/contact/index.html",
    "ontology": "{lang}/ontology/index.html",
    "standard": "{lang}/standard/index.html",
    "changelog": "{lang}/changelog/index.html",
}

REFERENCE_ROUTE_PATHS = {
    "about": "/{lang}/about/",
    "acquire": "/{lang}/acquire/",
    "travel_decision_architecture": "/{lang}/travel-decision-architecture/",
    "source_policy": "/{lang}/methodology/source-policy/",
    "editorial_standards": "/{lang}/methodology/editorial-standards/",
    "privacy": "/{lang}/privacy/",
    "contact": "/{lang}/contact/",
    "ontology": "/{lang}/ontology/",
    "standard": "/{lang}/standard/",
    "changelog": "/{lang}/changelog/",
}

COMMON_ENGLISH_REFERENCE_HEADINGS = (
    "Scope",
    "What TourVsTravel is",
    "Why destination-first planning is incomplete",
    "Why the name matters",
    "Strategic buyer logic",
    "What is included conceptually",
    "Qualified strategic inquiries only",
    "What this page does not claim",
    "Source standards",
    "Editorial standards",
)

APPROVED_REFERENCE_ENGLISH_TERMS = (
    "TourVsTravel.com",
    "TourVsTravel",
    "Tour Vs Travel .com",
    "Tour Vs Travel",
    "Travel Decision Architecture",
    "Travel Structure Ontology",
    "Travel Decision Integrity Standard",
    "Structure Fit Protocol",
    "agent@sohadot.com",
    "TSO",
    "TDIS",
    "SFP",
    "AI",
)

SENSITIVE_REPO_PATHS = {
    ROOT_DIR,
    ROOT_DIR / ".git",
    ROOT_DIR / ".github",
    ROOT_DIR / "data",
    ROOT_DIR / "scripts",
    ROOT_DIR / "templates",
    ROOT_DIR / "static",
}


# ============================================================================
# Exceptions
# ============================================================================

class BuildError(Exception):
    """Base build error."""


class BuildSafetyError(BuildError):
    """Raised when a filesystem safety rule is violated."""


class BuildStepError(BuildError):
    """Raised when a build step fails or output contract is invalid."""


class BuildPromotionError(BuildError):
    """Raised when staging output cannot be promoted safely."""


# ============================================================================
# Filesystem helpers
# ============================================================================

def _is_relative_to(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _ensure_safe_output_dir(output_dir: Path) -> Path:
    resolved = output_dir.resolve()
    repo_root = ROOT_DIR.resolve()
    allowed_in_repo_output = DEFAULT_OUTPUT_DIR.resolve()

    if not resolved.is_absolute():
        raise BuildSafetyError(f"Output directory must resolve to an absolute path: {output_dir}")

    if str(resolved) == resolved.anchor:
        raise BuildSafetyError(f"Refusing to use filesystem root as output directory: {resolved}")

    if resolved.exists() and resolved.is_symlink():
        raise BuildSafetyError(f"Refusing symlink output directory: {resolved}")

    parent = resolved.parent
    if parent.exists() and parent.is_symlink():
        raise BuildSafetyError(f"Refusing output directory with symlink parent: {parent}")

    if _is_relative_to(resolved, repo_root):
        if resolved != allowed_in_repo_output:
            raise BuildSafetyError(
                "Refusing in-repository output directory outside the sanctioned build target. "
                f"Allowed: {allowed_in_repo_output}; got: {resolved}"
            )
        return resolved

    for sensitive in SENSITIVE_REPO_PATHS:
        sensitive_resolved = sensitive.resolve()
        if resolved == sensitive_resolved:
            raise BuildSafetyError(f"Refusing sensitive output directory: {resolved}")
        if _is_relative_to(resolved, sensitive_resolved):
            raise BuildSafetyError(
                f"Refusing output directory inside sensitive repository path: {resolved}"
            )

    return resolved


def _reject_symlinks_under(path: Path) -> None:
    if not path.exists():
        return

    for candidate in path.rglob("*"):
        if candidate.is_symlink():
            raise BuildSafetyError(f"Refusing symlink inside build input tree: {candidate}")


def _make_stage_dir(final_output_dir: Path) -> Path:
    parent = final_output_dir.parent
    parent.mkdir(parents=True, exist_ok=True)

    if parent.is_symlink():
        raise BuildSafetyError(f"Refusing staging parent symlink: {parent}")

    stage = Path(
        tempfile.mkdtemp(
            prefix=".build-stage-",
            dir=str(parent),
        )
    ).resolve()

    if not stage.exists() or not stage.is_dir():
        raise BuildSafetyError(f"Failed to create staging directory: {stage}")

    if stage == final_output_dir:
        raise BuildSafetyError("Staging directory must not equal final output directory.")

    log.info("Created staging directory -> %s", stage)
    return stage


def _remove_tree_if_exists(path: Path) -> None:
    if not path.exists():
        return

    try:
        shutil.rmtree(path)
    except Exception as exc:
        log.warning("Failed to remove directory %s: %s", path, exc)


def _copy_static_tree(stage_dir: Path) -> Path:
    if not STATIC_DIR.exists():
        raise BuildStepError(f"Missing static directory: {STATIC_DIR}")
    if not STATIC_DIR.is_dir():
        raise BuildStepError(f"Static path is not a directory: {STATIC_DIR}")

    _reject_symlinks_under(STATIC_DIR)

    target = stage_dir / "static"

    if target.exists():
        raise BuildStepError(f"Static target already exists in staging directory: {target}")

    shutil.copytree(STATIC_DIR, target, symlinks=False)

    log.info("Copied static assets -> %s", target)
    return target


def _write_nojekyll(stage_dir: Path) -> Path:
    path = stage_dir / ".nojekyll"
    path.write_text("", encoding="utf-8")
    log.info("Created .nojekyll -> %s", path)
    return path


# ============================================================================
# Build steps
# ============================================================================

def _run_root_generation(*, stage_dir: Path) -> Path:
    written = generate_root_entrypoint(
        output_dir=stage_dir,
        default_lang=DEFAULT_ROOT_LANG,
    )
    log.info("Generated root entrypoint -> %s", written)
    return written


def _run_home_generation(*, stage_dir: Path) -> int:
    written = generate_home_pages(
        requested_lang=None,
        output_dir=stage_dir,
    )
    count = len(written)
    log.info("Generated home pages: %d", count)
    return count


def _run_methodology_generation(*, stage_dir: Path) -> int:
    written = generate_methodology_pages(
        requested_lang=None,
        output_dir=stage_dir,
    )
    count = len(written)
    log.info("Generated methodology pages: %d", count)
    return count


def _run_styles_index_generation(*, stage_dir: Path) -> int:
    written = generate_styles_index_pages(
        requested_lang=None,
        output_dir=stage_dir,
    )
    count = len(written)
    log.info("Generated styles index pages: %d", count)
    return count


def _run_compare_generation(*, stage_dir: Path) -> int:
    written = generate_compare_pages(
        requested_lang=None,
        output_dir=stage_dir,
    )
    count = len(written)
    log.info("Generated compare pages: %d", count)
    return count


def _run_tools_generation(*, stage_dir: Path) -> int:
    written = generate_tools_pages(
        requested_lang=None,
        output_dir=stage_dir,
    )
    count = len(written)
    log.info("Generated tools pages: %d", count)
    return count


def _run_find_your_match_generation(*, stage_dir: Path) -> int:
    written = generate_find_your_match_pages(
        requested_lang=None,
        output_dir=stage_dir,
    )
    count = len(written)
    log.info("Generated Find Your Match pages: %d", count)
    return count


def _run_destinations_generation(*, stage_dir: Path) -> int:
    written = generate_destinations_pages(
        requested_lang=None,
        output_dir=stage_dir,
    )
    count = len(written)
    log.info("Generated destinations pages: %d", count)
    return count


def _run_experience_type_generation(*, stage_dir: Path) -> int:
    written = generate_experience_type_pages(
        requested_lang=None,
        requested_type_id=None,
        output_dir=stage_dir,
    )
    count = len(written)
    log.info("Generated experience type pages: %d", count)
    return count


def _run_report_generation(*, stage_dir: Path) -> int:
    written = generate_report_pages(
        requested_lang=None,
        output_dir=stage_dir,
    )
    count = len(written)
    log.info("Generated reference report pages: %d", count)
    return count


def _run_contact_generation(*, stage_dir: Path) -> int:
    written = generate_contact_pages(
        requested_lang=None,
        output_dir=stage_dir,
    )
    count = len(written)
    log.info("Generated contact and reports-alias pages: %d", count)
    return count


def _run_about_generation(*, stage_dir: Path) -> int:
    written = generate_about_pages(
        requested_lang=None,
        output_dir=stage_dir,
    )
    count = len(written)
    log.info("Generated about pages: %d", count)
    return count


def _run_privacy_generation(*, stage_dir: Path) -> int:
    written = generate_privacy_pages(
        requested_lang=None,
        output_dir=stage_dir,
    )
    count = len(written)
    log.info("Generated privacy pages: %d", count)
    return count


def _run_acquire_generation(*, stage_dir: Path) -> int:
    written = generate_acquire_pages(
        requested_lang=None,
        output_dir=stage_dir,
    )
    count = len(written)
    log.info("Generated acquire pages: %d", count)
    return count


def _run_source_policy_generation(*, stage_dir: Path) -> int:
    written = generate_source_policy_pages(
        requested_lang=None,
        output_dir=stage_dir,
    )
    count = len(written)
    log.info("Generated source policy pages: %d", count)
    return count


def _run_editorial_standards_generation(*, stage_dir: Path) -> int:
    written = generate_editorial_standards_pages(
        requested_lang=None,
        output_dir=stage_dir,
    )
    count = len(written)
    log.info("Generated editorial standards pages: %d", count)
    return count


def _run_travel_decision_architecture_generation(*, stage_dir: Path) -> int:
    written = generate_travel_decision_architecture_pages(
        requested_lang=None,
        output_dir=stage_dir,
    )
    count = len(written)
    log.info("Generated travel decision architecture pages: %d", count)
    return count


def _run_category_infrastructure_generation(*, stage_dir: Path) -> int:
    written = generate_category_infrastructure_pages(
        requested_lang=None,
        output_dir=stage_dir,
    )
    count = len(written)
    log.info("Generated category infrastructure pages: %d", count)
    return count


def _run_machine_layer_generation(*, stage_dir: Path) -> int:
    written = generate_machine_layer(
        output_dir=stage_dir,
    )
    count = len(written)
    log.info("Generated machine layer artifacts: %d", count)
    return count


def _run_destination_detail_generation(*, stage_dir: Path) -> int:
    written = generate_destination_detail_pages(
        requested_lang=None,
        output_dir=stage_dir,
    )
    count = len(written)
    log.info("Generated destination detail pages: %d", count)
    return count


def _run_compass_generation(*, stage_dir: Path) -> int:
    written = generate_compass_pages(
        requested_lang=None,
        output_dir=stage_dir,
    )
    count = len(written)
    log.info("Generated Travel Decision Compass pages: %d", count)
    return count


def _run_robots_generation(*, stage_dir: Path) -> Path:
    written = generate_robots_file(
        output_dir=stage_dir,
    )
    log.info("Generated robots.txt -> %s", written)
    return written


def _run_sitemap_generation(*, stage_dir: Path) -> Path:
    written = generate_sitemap_file(
        output_dir=stage_dir,
    )
    log.info("Generated sitemap.xml -> %s", written)
    return written


# ============================================================================
# Output contract validation
# ============================================================================

def _require_file(path: Path) -> None:
    if not path.exists():
        raise BuildStepError(f"Required file is missing: {path}")
    if not path.is_file():
        raise BuildStepError(f"Required path is not a file: {path}")


def _require_dir(path: Path) -> None:
    if not path.exists():
        raise BuildStepError(f"Required directory is missing: {path}")
    if not path.is_dir():
        raise BuildStepError(f"Required path is not a directory: {path}")


def _scan_html_forbidden_fragments(stage_dir: Path) -> None:
    forbidden_fragments = [
        'href="/en/."',
        'href="/ar/."',
        'href="/fr/."',
        'href="/es/."',
        'href="/de/."',
        'href="/zh/."',
        'href="/ja/."',
        "href='/en/.'",
        "href='/ar/.'",
        "href='/fr/.'",
        "href='/es/.'",
        "href='/de/.'",
        "href='/zh/.'",
        "href='/ja/.'",
        'src="static/',
        "src='static/",
        'href="static/',
        "href='static/",
        'src="../static/',
        "src='../static/",
        'href="../static/',
        "href='../static/",
        '/experience/',
        'href="/#report"',
        "href='/#report'",
    ]

    for html_file in stage_dir.rglob("*.html"):
        try:
            text = html_file.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise BuildStepError(f"Generated HTML is not valid UTF-8: {html_file}") from exc

        for fragment in forbidden_fragments:
            if fragment in text:
                raise BuildStepError(
                    f"Forbidden generated HTML fragment {fragment!r} found in {html_file}"
                )


def _verify_claims_restraint(stage_dir: Path) -> None:
    """
    Claims-restraint gate (see GOVERNANCE.md).

    No retired or unverifiable quantitative claim may reappear in any generated
    page. Fragments listed here were removed from public copy because no
    published data backed them; their reappearance is a build defect, not a
    copy issue.
    """
    retired_claim_fragments = [
        # "200 destinations" retired 2026-07-03 (DECISIONS.md D-002):
        # zero destination pages were published when the claim shipped.
        # Matching is case-insensitive (covers "200 Destinations" etc.).
        "200 destinations",
        "200 وجهة",
        "200 destinos",
        "200 ziele",
        "200 reiseziele",
        "200个目的地",
        "200の目的地",
    ]

    for html_file in stage_dir.rglob("*.html"):
        try:
            text = html_file.read_text(encoding="utf-8").lower()
        except UnicodeDecodeError as exc:
            raise BuildStepError(f"Generated HTML is not valid UTF-8: {html_file}") from exc

        for fragment in retired_claim_fragments:
            if fragment in text:
                raise BuildStepError(
                    f"Retired unverifiable claim {fragment!r} found in {html_file}. "
                    "Claims restraint: public numbers must be backed by published data "
                    "(see GOVERNANCE.md)."
                )


def _verify_static_asset_references(stage_dir: Path) -> None:
    static_ref_pattern = re.compile(
        r"""(?:src|href)=["'](?:https://tourvstravel\.com)?(/static/[^"'\?#]+)""",
        re.IGNORECASE,
    )

    for html_file in stage_dir.rglob("*.html"):
        try:
            text = html_file.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise BuildStepError(f"Generated HTML is not valid UTF-8: {html_file}") from exc

        for match in static_ref_pattern.finditer(text):
            static_path = match.group(1).lstrip("/")
            asset_path = (stage_dir / static_path).resolve()

            if not _is_relative_to(asset_path, stage_dir.resolve()):
                raise BuildStepError(
                    f"Generated HTML references unsafe static asset path {match.group(1)!r} in {html_file}"
                )

            if not asset_path.is_file():
                raise BuildStepError(
                    f"Generated HTML references missing static asset {match.group(1)!r} in {html_file}"
                )


class _HtmlIntegrityParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.html_lang = ""
        self.html_dir = ""
        self.h1_count = 0
        self.canonical_href = ""
        self.robots_content = ""
        self.hrefs: List[str] = []
        self.text_parts: List[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        attr_map = {name.lower(): value or "" for name, value in attrs}
        tag_name = tag.lower()
        if tag_name in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return
        if tag_name == "html":
            self.html_lang = attr_map.get("lang", "")
            self.html_dir = attr_map.get("dir", "")
        elif tag_name == "h1":
            self.h1_count += 1
        elif tag_name == "a" and attr_map.get("href"):
            self.hrefs.append(attr_map["href"])
        elif tag_name == "link" and attr_map.get("rel", "").lower() == "canonical":
            self.canonical_href = attr_map.get("href", "")
        elif tag_name == "meta" and attr_map.get("name", "").lower() == "robots":
            self.robots_content = attr_map.get("content", "")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0 and data.strip():
            self.text_parts.append(data)

    @property
    def visible_text(self) -> str:
        return re.sub(r"\s+", " ", unescape(" ".join(self.text_parts))).strip()


def _parse_generated_html(path: Path) -> _HtmlIntegrityParser:
    parser = _HtmlIntegrityParser()
    try:
        parser.feed(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        raise BuildStepError(f"Generated HTML is not valid UTF-8: {path}") from exc
    return parser


def _english_reference_fragments(page_key: str) -> List[str]:
    fragments: List[str] = []
    if page_key == "travel_decision_architecture":
        for section in TDA_ENGLISH_SECTIONS:
            fragments.extend(section.get("paragraphs", []))
        return [text for text in fragments if isinstance(text, str) and len(text) >= 80]

    if page_key in CATEGORY_INFRASTRUCTURE_ENGLISH_FRAGMENTS:
        return list(CATEGORY_INFRASTRUCTURE_ENGLISH_FRAGMENTS[page_key])

    copy = TRUST_PAGE_COPY[page_key]
    fragments.append(str(copy.get("lead", "")))
    for section in copy.get("sections", []):
        if isinstance(section, dict):
            fragments.extend(section.get("paragraphs", []))
    return [text for text in fragments if isinstance(text, str) and len(text) >= 80]


def _strip_approved_english_terms(text: str) -> str:
    stripped = text
    for term in APPROVED_REFERENCE_ENGLISH_TERMS:
        stripped = stripped.replace(term, " ")
    return stripped


def _verify_no_large_english_blocks(html_file: Path, text: str, lang: str) -> None:
    if lang not in {"ar", "zh", "ja"}:
        return
    stripped = _strip_approved_english_terms(text)
    if re.search(r"[A-Za-z][A-Za-z0-9 ,.;:'\"!?()/-]{80,}[A-Za-z]", stripped):
        raise BuildStepError(
            f"Large English text block found in localized {lang} reference page: {html_file}"
        )


def _verify_reference_page_integrity(stage_dir: Path) -> None:
    site_base = "https://tourvstravel.com"
    for lang in SUPPORTED_LANGUAGES:
        expected_dir = "rtl" if lang == "ar" else "ltr"
        for page_key, path_template in REFERENCE_PAGE_PATHS.items():
            html_file = stage_dir / path_template.format(lang=lang)
            _require_file(html_file)
            parser = _parse_generated_html(html_file)
            text = parser.visible_text

            if parser.html_lang != lang:
                raise BuildStepError(f"Expected html lang={lang!r} in {html_file}, found {parser.html_lang!r}")
            if parser.html_dir != expected_dir:
                raise BuildStepError(f"Expected html dir={expected_dir!r} in {html_file}, found {parser.html_dir!r}")
            if parser.h1_count != 1:
                raise BuildStepError(f"Expected exactly one H1 in {html_file}, found {parser.h1_count}")
            if "noindex" in parser.robots_content.lower() or "noindex" in text.lower():
                raise BuildStepError(f"Reference page must not contain noindex: {html_file}")
            robots_normalized = parser.robots_content.lower().replace(" ", "")
            if "index,follow" not in robots_normalized:
                raise BuildStepError(f"Reference page must declare index, follow robots directive: {html_file}")

            expected_route = REFERENCE_ROUTE_PATHS[page_key].format(lang=lang)
            expected_canonical = f"{site_base}{expected_route}"
            if parser.canonical_href != expected_canonical:
                raise BuildStepError(
                    f"Unexpected canonical URL in {html_file}: expected {expected_canonical}, found {parser.canonical_href}"
                )

            if lang == "en":
                continue

            for heading in COMMON_ENGLISH_REFERENCE_HEADINGS:
                if heading in text:
                    raise BuildStepError(
                        f"English fallback heading {heading!r} found in localized reference page: {html_file}"
                    )

            for fragment in _english_reference_fragments(page_key):
                if fragment in text:
                    raise BuildStepError(
                        f"English fallback body paragraph found in localized reference page: {html_file}"
                    )

            _verify_no_large_english_blocks(html_file, text, lang)


def _resolve_local_href(stage_dir: Path, href: str) -> Optional[Path]:
    parsed = urlsplit(href)
    if parsed.scheme or parsed.netloc or href.startswith(("mailto:", "tel:", "#")):
        return None
    path = parsed.path
    if not path or path.startswith("/static/"):
        return None
    if path == "/":
        return stage_dir / "index.html"
    if path.endswith("/"):
        return stage_dir / path.lstrip("/") / "index.html"
    candidate = stage_dir / path.lstrip("/")
    if candidate.suffix:
        return candidate
    return candidate / "index.html"


def _verify_local_links(stage_dir: Path) -> None:
    for html_file in stage_dir.rglob("*.html"):
        parser = _parse_generated_html(html_file)
        for href in parser.hrefs:
            target = _resolve_local_href(stage_dir, href)
            if target is None:
                continue
            resolved = target.resolve()
            if not _is_relative_to(resolved, stage_dir.resolve()):
                raise BuildStepError(f"Generated local link escapes output directory in {html_file}: {href}")
            if not resolved.is_file():
                raise BuildStepError(f"Generated local link points to missing page in {html_file}: {href}")


def _verify_sitemap_contract(stage_dir: Path) -> None:
    sitemap_path = stage_dir / "sitemap.xml"
    _require_file(sitemap_path)

    text = sitemap_path.read_text(encoding="utf-8")

    required_fragments = [
        "/en/",
        "/en/methodology/",
        "/en/compare/",
        "/en/tools/",
        "/en/tools/find-your-match/",
        "/en/destinations/",
        "/en/report/",
        "/en/contact/",
        "/en/styles/guided-group-tour/",
    ]

    for fragment in required_fragments:
        if fragment not in text:
            raise BuildStepError(f"sitemap.xml is missing required URL fragment: {fragment}")

    for lang in SUPPORTED_LANGUAGES:
        for route_template in REFERENCE_ROUTE_PATHS.values():
            fragment = route_template.format(lang=lang)
            if fragment not in text:
                raise BuildStepError(f"sitemap.xml is missing reference URL fragment: {fragment}")


def _verify_experience_type_count(stage_dir: Path) -> None:
    styles_dir = stage_dir / "en" / "styles"
    _require_dir(styles_dir)

    pages = sorted(styles_dir.glob("*/index.html"))

    if len(pages) != EXPECTED_EXPERIENCE_TYPE_COUNT:
        raise BuildStepError(
            f"Expected {EXPECTED_EXPERIENCE_TYPE_COUNT} English experience type pages, "
            f"found {len(pages)} in {styles_dir}"
        )


def _verify_destination_pages_contract(stage_dir: Path) -> None:
    """
    Every enabled destination in the governed dataset must have a page in
    every supported language — and no phantom destination pages may exist
    beyond the dataset.
    """
    expected_ids = {dest["id"] for dest in load_governed_destinations()}
    if not expected_ids:
        raise BuildStepError("Governed destinations dataset is empty.")

    for lang in SUPPORTED_LANGUAGES:
        dest_dir = stage_dir / lang / "destinations"
        _require_dir(dest_dir)
        found_ids = {p.parent.name for p in dest_dir.glob("*/index.html")}
        missing = expected_ids - found_ids
        if missing:
            raise BuildStepError(
                f"Missing destination pages for {lang}: {sorted(missing)}"
            )
        phantom = found_ids - expected_ids
        if phantom:
            raise BuildStepError(
                f"Phantom destination pages for {lang} not backed by the dataset: {sorted(phantom)}"
            )


def _verify_machine_layer_contract(stage_dir: Path) -> None:
    """
    The machine layer must ship complete or not at all: the versioned
    ontology and standard artifacts, exactly one JSON artifact per
    ontology class, the criteria dataset, and the asset identity file.
    Every artifact must parse as JSON and carry its artifact envelope.
    """
    import json as _json

    required_files = [
        stage_dir / "ontology" / "tso-v1.json",
        stage_dir / "standard" / "tdis-v1.json",
        stage_dir / "api" / "criteria-v1.json",
        stage_dir / "about.json",
    ]
    for path in required_files:
        _require_file(path)

    structures_dir = stage_dir / "api" / "structures"
    _require_dir(structures_dir)
    structure_files = sorted(structures_dir.glob("*.json"))
    if len(structure_files) != EXPECTED_EXPERIENCE_TYPE_COUNT:
        raise BuildStepError(
            f"Expected {EXPECTED_EXPERIENCE_TYPE_COUNT} machine-layer structure artifacts, "
            f"found {len(structure_files)} in {structures_dir}"
        )

    for path in required_files + structure_files:
        try:
            payload = _json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise BuildStepError(f"Machine-layer artifact is not valid JSON: {path}: {exc}") from exc
        if not isinstance(payload, dict) or not payload:
            raise BuildStepError(f"Machine-layer artifact must be a non-empty JSON object: {path}")
        if path.name != "about.json":
            for envelope_key in ("artifact", "version", "issued_by"):
                if envelope_key not in payload:
                    raise BuildStepError(
                        f"Machine-layer artifact {path} is missing envelope key {envelope_key!r}"
                    )

    tso_payload = _json.loads((stage_dir / "ontology" / "tso-v1.json").read_text(encoding="utf-8"))
    if tso_payload.get("structure_count") != EXPECTED_EXPERIENCE_TYPE_COUNT:
        raise BuildStepError(
            "tso-v1.json structure_count does not match the ontology contract "
            f"({tso_payload.get('structure_count')!r} != {EXPECTED_EXPERIENCE_TYPE_COUNT})"
        )


def _verify_trust_pages_are_indexable(stage_dir: Path) -> None:
    trust_path_templates = [
        "{lang}/about/index.html",
        "{lang}/privacy/index.html",
        "{lang}/acquire/index.html",
        "{lang}/methodology/source-policy/index.html",
        "{lang}/methodology/editorial-standards/index.html",
    ]
    for lang in SUPPORTED_LANGUAGES:
        for path_template in trust_path_templates:
            html_file = stage_dir / path_template.format(lang=lang)
            if not html_file.exists():
                continue
            text = html_file.read_text(encoding="utf-8")
            if "noindex" in text:
                raise BuildStepError(
                    f"Trust page must not contain noindex: {html_file}"
                )


def _verify_output_contract(stage_dir: Path) -> None:
    log.info("Verifying staged output contract")

    _require_dir(stage_dir)
    _require_dir(stage_dir / "static")
    _require_dir(stage_dir / "static" / "css")
    _require_dir(stage_dir / "static" / "js")

    _require_file(stage_dir / "index.html")
    _require_file(stage_dir / ".nojekyll")
    _require_file(stage_dir / "robots.txt")
    _require_file(stage_dir / "sitemap.xml")
    _require_file(stage_dir / "static" / "css" / "main.css")
    _require_file(stage_dir / "static" / "js" / "main.js")

    for lang in SUPPORTED_LANGUAGES:
        _require_file(stage_dir / lang / "index.html")
        _require_file(stage_dir / lang / "methodology" / "index.html")
        _require_file(stage_dir / lang / "styles" / "index.html")
        _require_file(stage_dir / lang / "compare" / "index.html")
        _require_file(stage_dir / lang / "tools" / "index.html")
        _require_file(stage_dir / lang / "tools" / "find-your-match" / "index.html")
        _require_file(stage_dir / lang / "tools" / "travel-decision-compass" / "index.html")
        _require_file(stage_dir / lang / "destinations" / "index.html")
        _require_file(stage_dir / lang / "report" / "index.html")
        _require_file(stage_dir / lang / "contact" / "index.html")
        _require_file(stage_dir / lang / "about" / "index.html")
        _require_file(stage_dir / lang / "privacy" / "index.html")
        _require_file(stage_dir / lang / "acquire" / "index.html")
        _require_file(stage_dir / lang / "methodology" / "source-policy" / "index.html")
        _require_file(stage_dir / lang / "methodology" / "editorial-standards" / "index.html")
        _require_file(stage_dir / lang / "travel-decision-architecture" / "index.html")

    _require_file(stage_dir / "en" / "styles" / "guided-group-tour" / "index.html")

    _verify_destination_pages_contract(stage_dir)
    _verify_machine_layer_contract(stage_dir)
    _verify_trust_pages_are_indexable(stage_dir)
    _verify_experience_type_count(stage_dir)
    _verify_sitemap_contract(stage_dir)
    _scan_html_forbidden_fragments(stage_dir)
    _verify_claims_restraint(stage_dir)
    _verify_static_asset_references(stage_dir)
    _verify_reference_page_integrity(stage_dir)
    _verify_local_links(stage_dir)

    log.info("Staged output contract verified successfully")


# ============================================================================
# Promotion
# ============================================================================

def _promote_stage_to_final(stage_dir: Path, final_output_dir: Path) -> None:
    stage_dir = stage_dir.resolve()
    final_output_dir = final_output_dir.resolve()

    if not stage_dir.exists() or not stage_dir.is_dir():
        raise BuildPromotionError(f"Stage directory is missing: {stage_dir}")

    if stage_dir == final_output_dir:
        raise BuildPromotionError("Stage directory must not equal final output directory.")

    parent = final_output_dir.parent
    backup_dir: Optional[Path] = None

    log.info("Promoting stage to final output -> %s", final_output_dir)

    try:
        if final_output_dir.exists():
            if final_output_dir.is_symlink():
                raise BuildPromotionError(f"Refusing to replace symlink output directory: {final_output_dir}")
            if not final_output_dir.is_dir():
                raise BuildPromotionError(f"Final output path exists but is not a directory: {final_output_dir}")

            backup_dir = parent / f".build-backup-{os.getpid()}-{time.time_ns()}"
            final_output_dir.replace(backup_dir)
            log.info("Existing output moved to backup -> %s", backup_dir)

        stage_dir.replace(final_output_dir)

        if not final_output_dir.exists() or not final_output_dir.is_dir():
            raise BuildPromotionError(
                "Promotion appeared to succeed but final output directory is missing."
            )

        if backup_dir is not None and backup_dir.exists():
            shutil.rmtree(backup_dir)
            log.info("Removed backup -> %s", backup_dir)

        log.info("Build promoted successfully -> %s", final_output_dir)

    except Exception as exc:
        log.error("Promotion failed: %s", exc)

        if final_output_dir.exists() and final_output_dir != stage_dir:
            _remove_tree_if_exists(final_output_dir)

        if backup_dir is not None and backup_dir.exists():
            try:
                backup_dir.replace(final_output_dir)
                log.warning("Restored previous output from backup -> %s", final_output_dir)
            except Exception as restore_exc:
                raise BuildPromotionError(
                    f"Promotion failed and rollback also failed: {restore_exc}"
                ) from exc

        raise


# ============================================================================
# Public build API
# ============================================================================

def run_build(
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    keep_stage_on_failure: bool = False,
) -> Path:
    final_output_dir = _ensure_safe_output_dir(output_dir)

    stage_dir = _make_stage_dir(final_output_dir)

    try:
        log.info("Step 1: Copy static assets")
        _copy_static_tree(stage_dir)

        log.info("Step 2: Generate root entrypoint")
        _run_root_generation(stage_dir=stage_dir)

        log.info("Step 3: Generate multilingual home pages")
        _run_home_generation(stage_dir=stage_dir)

        log.info("Step 4: Generate multilingual methodology pages")
        _run_methodology_generation(stage_dir=stage_dir)

        log.info("Step 5: Generate multilingual styles index pages")
        _run_styles_index_generation(stage_dir=stage_dir)

        log.info("Step 6: Generate multilingual compare pages")
        _run_compare_generation(stage_dir=stage_dir)

        log.info("Step 7: Generate multilingual tools pages")
        _run_tools_generation(stage_dir=stage_dir)

        log.info("Step 8: Generate multilingual Find Your Match tool pages")
        _run_find_your_match_generation(stage_dir=stage_dir)

        log.info("Step 9: Generate multilingual destinations pages")
        _run_destinations_generation(stage_dir=stage_dir)

        log.info("Step 10: Generate destination detail pages (governed batch)")
        _run_destination_detail_generation(stage_dir=stage_dir)

        log.info("Step 11: Generate multilingual experience type pages")
        _run_experience_type_generation(stage_dir=stage_dir)

        log.info("Step 12: Generate multilingual reference report pages")
        _run_report_generation(stage_dir=stage_dir)

        log.info("Step 13: Generate contact pages and legacy /reports/ redirects")
        _run_contact_generation(stage_dir=stage_dir)

        log.info("Step 14: Generate multilingual about pages")
        _run_about_generation(stage_dir=stage_dir)

        log.info("Step 15: Generate multilingual privacy pages")
        _run_privacy_generation(stage_dir=stage_dir)

        log.info("Step 16: Generate multilingual acquire pages")
        _run_acquire_generation(stage_dir=stage_dir)

        log.info("Step 17: Generate multilingual source policy pages")
        _run_source_policy_generation(stage_dir=stage_dir)

        log.info("Step 18: Generate multilingual editorial standards pages")
        _run_editorial_standards_generation(stage_dir=stage_dir)

        log.info("Step 19: Generate multilingual Travel Decision Architecture pages")
        _run_travel_decision_architecture_generation(stage_dir=stage_dir)

        log.info("Step 20: Generate category infrastructure pages (ontology, standard, changelog)")
        _run_category_infrastructure_generation(stage_dir=stage_dir)

        log.info("Step 21: Generate machine layer artifacts (agent-readable JSON)")
        _run_machine_layer_generation(stage_dir=stage_dir)

        log.info("Step 22: Generate Travel Decision Compass pages")
        _run_compass_generation(stage_dir=stage_dir)

        log.info("Step 23: Generate robots.txt")
        _run_robots_generation(stage_dir=stage_dir)

        log.info("Step 24: Generate sitemap.xml")
        _run_sitemap_generation(stage_dir=stage_dir)

        log.info("Step 25: Create .nojekyll")
        _write_nojekyll(stage_dir)

        log.info("Step 26: Verify staged output")
        _verify_output_contract(stage_dir)

        log.info("Step 27: Promote staged output")
        _promote_stage_to_final(stage_dir, final_output_dir)

    except Exception:
        if keep_stage_on_failure:
            log.error("Build failed. Staging directory preserved for inspection: %s", stage_dir)
        else:
            _remove_tree_if_exists(stage_dir)
        raise

    return final_output_dir


# ============================================================================
# CLI
# ============================================================================

def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the full TourVsTravel production build pipeline."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Final output directory. Default: ./output",
    )
    parser.add_argument(
        "--keep-stage-on-failure",
        action="store_true",
        help="Preserve the temporary staging directory if the build fails.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose build logging.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    configure_logging(verbose=args.verbose)

    try:
        final_output = run_build(
            output_dir=args.output_dir.resolve(),
            keep_stage_on_failure=args.keep_stage_on_failure,
        )
    except (
        BuildError,
        GenerateRootError,
        GenerateHomeError,
        GenerateMethodologyError,
        GenerateStylesIndexError,
        GenerateCompareError,
        GenerateToolsError,
        GenerateFindYourMatchError,
        GenerateDestinationsError,
        GenerateReportError,
        GenerateContactError,
        GenerateAboutError,
        GeneratePrivacyError,
        GenerateAcquireError,
        GenerateSourcePolicyError,
        GenerateEditorialStandardsError,
        GenerateTravelDecisionArchitectureError,
        GenerateExperienceTypesError,
        GenerateRobotsError,
        GenerateSitemapError,
    ) as exc:
        log.error(str(exc))
        return 1
    except Exception as exc:
        log.exception("Unexpected build failure: %s", exc)
        return 1

    log.info("Production build completed successfully -> %s", final_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
