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
from pathlib import Path
from typing import List, Optional, Sequence


from scripts.generate_root import GenerateRootError, generate_root_entrypoint
from scripts.generate_home import GenerateHomeError, generate_home_pages
from scripts.generate_methodology import GenerateMethodologyError, generate_methodology_pages
from scripts.generate_styles_index import (
    GenerateStylesIndexError,
    generate_styles_index_pages,
)
from scripts.generate_compare import GenerateCompareError, generate_compare_pages
from scripts.generate_experience_types import (
    GenerateExperienceTypesError,
    generate_experience_type_pages,
)
from scripts.generate_robots import GenerateRobotsError, generate_robots_file
from scripts.generate_sitemap import GenerateSitemapError, generate_sitemap_file


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


def _run_experience_type_generation(*, stage_dir: Path) -> int:
    written = generate_experience_type_pages(
        requested_lang=None,
        requested_type_id=None,
        output_dir=stage_dir,
    )
    count = len(written)
    log.info("Generated experience type pages: %d", count)
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


def _verify_sitemap_contract(stage_dir: Path) -> None:
    sitemap_path = stage_dir / "sitemap.xml"
    _require_file(sitemap_path)

    text = sitemap_path.read_text(encoding="utf-8")

    required_fragments = [
        "/en/",
        "/en/methodology/",
        "/en/compare/",
        "/en/styles/guided-group-tour/",
    ]

    for fragment in required_fragments:
        if fragment not in text:
            raise BuildStepError(f"sitemap.xml is missing required URL fragment: {fragment}")


def _verify_experience_type_count(stage_dir: Path) -> None:
    styles_dir = stage_dir / "en" / "styles"
    _require_dir(styles_dir)

    pages = sorted(styles_dir.glob("*/index.html"))

    if len(pages) != EXPECTED_EXPERIENCE_TYPE_COUNT:
        raise BuildStepError(
            f"Expected {EXPECTED_EXPERIENCE_TYPE_COUNT} English experience type pages, "
            f"found {len(pages)} in {styles_dir}"
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

    _require_file(stage_dir / "en" / "styles" / "guided-group-tour" / "index.html")

    _verify_experience_type_count(stage_dir)
    _verify_sitemap_contract(stage_dir)
    _scan_html_forbidden_fragments(stage_dir)
    _verify_static_asset_references(stage_dir)

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

        log.info("Step 7: Generate multilingual experience type pages")
        _run_experience_type_generation(stage_dir=stage_dir)

        log.info("Step 8: Generate robots.txt")
        _run_robots_generation(stage_dir=stage_dir)

        log.info("Step 9: Generate sitemap.xml")
        _run_sitemap_generation(stage_dir=stage_dir)

        log.info("Step 10: Create .nojekyll")
        _write_nojekyll(stage_dir)

        log.info("Step 11: Verify staged output")
        _verify_output_contract(stage_dir)

        log.info("Step 12: Promote staged output")
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
