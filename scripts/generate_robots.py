#!/usr/bin/env python3
"""
TourVsTravel — Local Build Orchestrator
=======================================

Purpose
-------
Run the disciplined local build pipeline into a staging directory, then
promote the build to the final output directory only after all steps succeed.

Current build scope
-------------------
Phase 1 includes:
- copy static assets into stage output
- generate multilingual home pages
- generate site-wide robots.txt

Build policy
------------
- build into staging first
- never write directly into final output during generation
- promote staging -> final only after all generation steps succeed
- inside the repository, only ROOT_DIR/output is allowed as build output
- any other in-repo output target is rejected
- outside-repo targets are allowed if safe

Execution
---------
Run from repository root:

    python -m scripts.build
    python -m scripts.build --lang en
    python -m scripts.build --verbose
"""

from __future__ import annotations

import argparse
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Optional, Sequence

from scripts.generate_home import GenerateHomeError, generate_home_pages
from scripts.generate_robots import GenerateRobotsError, generate_robots_file


# ============================================================================
# Paths
# ============================================================================

ROOT_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT_DIR / "static"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "output"

# Only this in-repo output target is sanctioned.
ALLOWED_IN_REPO_OUTPUT_DIR = DEFAULT_OUTPUT_DIR.resolve()

EXPLICIT_SENSITIVE_PATHS = {
    ROOT_DIR.resolve(),
    (ROOT_DIR / ".git").resolve(),
    (ROOT_DIR / ".github").resolve(),
    (ROOT_DIR / "data").resolve(),
    (ROOT_DIR / "templates").resolve(),
    (ROOT_DIR / "static").resolve(),
    (ROOT_DIR / "scripts").resolve(),
    (ROOT_DIR / "tests").resolve(),
}


# ============================================================================
# Logging
# ============================================================================

log = logging.getLogger("build")


def configure_logging(*, verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


# ============================================================================
# Exceptions
# ============================================================================

class BuildError(Exception):
    """Base build exception."""


class BuildSafetyError(BuildError):
    """Raised when a build path is unsafe."""


class BuildStepError(BuildError):
    """Raised when a build step fails."""


# ============================================================================
# Helpers
# ============================================================================

def _is_within(path: Path, ancestor: Path) -> bool:
    try:
        path.relative_to(ancestor)
        return True
    except ValueError:
        return False


def _ensure_safe_output_dir(output_dir: Path) -> Path:
    """
    Validate the requested output directory.

    Rules:
    - must be absolute
    - must not be filesystem root
    - inside repo: only ROOT_DIR/output is allowed
    - outside repo: allowed if not itself a sensitive path
    """
    resolved = output_dir.resolve()
    repo_root = ROOT_DIR.resolve()

    if not resolved.is_absolute():
        raise BuildSafetyError(f"Output directory must be absolute. Got: {output_dir}")

    if str(resolved) == resolved.anchor:
        raise BuildSafetyError(f"Refusing to use filesystem root as output directory: {resolved}")

    if _is_within(resolved, repo_root):
        if resolved != ALLOWED_IN_REPO_OUTPUT_DIR:
            raise BuildSafetyError(
                f"Refusing in-repo output directory outside the sanctioned build target. "
                f"Allowed in-repo output is only: {ALLOWED_IN_REPO_OUTPUT_DIR} ; got: {resolved}"
            )

    if resolved in EXPLICIT_SENSITIVE_PATHS:
        raise BuildSafetyError(f"Refusing to use sensitive path as output directory: {resolved}")

    return resolved


def _require_static_tree() -> Path:
    if not STATIC_DIR.exists():
        raise BuildStepError(f"Missing static directory: {STATIC_DIR}")
    if not STATIC_DIR.is_dir():
        raise BuildStepError(f"Static path is not a directory: {STATIC_DIR}")
    return STATIC_DIR


def _make_stage_dir(final_output_dir: Path) -> Path:
    """
    Create a staging directory safely and unpredictably as a sibling of the
    final output directory.
    """
    stage_parent = final_output_dir.parent.resolve()

    if stage_parent in EXPLICIT_SENSITIVE_PATHS and stage_parent != ROOT_DIR.resolve():
        raise BuildSafetyError(
            f"Refusing to create build stage under a sensitive parent directory: {stage_parent}"
        )

    try:
        stage_path_str = tempfile.mkdtemp(prefix=".build-stage-", dir=str(stage_parent))
    except Exception as exc:
        raise BuildStepError(f"Failed to create staging directory under {stage_parent}: {exc}") from exc

    return Path(stage_path_str)


def _remove_tree_if_exists(path: Path) -> None:
    if path.exists():
        try:
            shutil.rmtree(path)
        except Exception as exc:
            log.warning("Failed to remove directory %s: %s", path, exc)


def _copy_static_tree(stage_output_dir: Path) -> None:
    """
    Copy /static into stage_output_dir/static
    """
    source = _require_static_tree()
    destination = stage_output_dir / "static"

    if destination.exists():
        raise BuildStepError(f"Stage static destination already exists unexpectedly: {destination}")

    try:
        shutil.copytree(source, destination)
    except Exception as exc:
        raise BuildStepError(f"Failed to copy static assets to {destination}: {exc}") from exc

    log.info("Copied static assets -> %s", destination)


def _promote_stage_to_final(stage_dir: Path, final_output_dir: Path) -> None:
    """
    Promote a successful staging build into the final output directory.

    Strategy:
    - if final output exists, move it to a sibling backup
    - move stage -> final
    - verify final now exists
    - remove backup after successful promotion
    - restore backup if promotion fails after backup creation
    """
    backup_dir = Path(
        tempfile.mkdtemp(prefix=".output-backup-", dir=str(final_output_dir.parent.resolve()))
    )
    backup_dir_created = True

    try:
        # mkdtemp created a directory; remove it so the path can receive replace().
        shutil.rmtree(backup_dir)

        if final_output_dir.exists():
            final_output_dir.replace(backup_dir)
            log.debug("Moved existing final output to backup: %s", backup_dir)
        else:
            backup_dir_created = False

        stage_dir.replace(final_output_dir)

        if not final_output_dir.exists():
            raise BuildStepError(
                f"Promotion completed without exception but final output is missing: {final_output_dir}"
            )

        if backup_dir_created and backup_dir.exists():
            shutil.rmtree(backup_dir)

    except Exception as exc:
        if backup_dir_created and backup_dir.exists() and not final_output_dir.exists():
            try:
                backup_dir.replace(final_output_dir)
                log.warning("Rollback succeeded after failed promotion.")
            except Exception as rollback_exc:
                raise BuildStepError(
                    f"Build promotion failed and rollback also failed. "
                    f"Promotion error: {exc}; Rollback error: {rollback_exc}"
                ) from rollback_exc

        raise BuildStepError(f"Failed to promote staging build to final output: {exc}") from exc


# ============================================================================
# Build steps
# ============================================================================

def _run_home_generation(
    *,
    requested_lang: Optional[str],
    stage_dir: Path,
) -> int:
    written_home = generate_home_pages(
        requested_lang=requested_lang,
        output_dir=stage_dir,
    )
    count = len(written_home)
    log.info("Generated home pages: %d", count)
    return count


def _run_robots_generation(*, stage_dir: Path) -> Path:
    robots_path = generate_robots_file(output_dir=stage_dir)
    log.info("Generated robots.txt -> %s", robots_path)
    return robots_path


# ============================================================================
# Build pipeline
# ============================================================================

def run_build(
    *,
    requested_lang: Optional[str] = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    keep_stage_on_failure: bool = False,
) -> Path:
    """
    Execute the local build pipeline into a staging directory,
    then promote it to the final output directory.
    """
    final_output_dir = _ensure_safe_output_dir(output_dir)
    stage_dir = _make_stage_dir(final_output_dir)

    log.info("Build started")
    log.info("Repository root : %s", ROOT_DIR)
    log.info("Final output    : %s", final_output_dir)
    log.info("Stage output    : %s", stage_dir)

    try:
        # Step 1: static assets
        _copy_static_tree(stage_dir)

        # Step 2: pages
        _run_home_generation(
            requested_lang=requested_lang,
            stage_dir=stage_dir,
        )

        # Step 3: robots
        _run_robots_generation(stage_dir=stage_dir)

        # Step 4: promote
        _promote_stage_to_final(stage_dir, final_output_dir)
        log.info("Build promoted successfully -> %s", final_output_dir)
        return final_output_dir

    except Exception:
        if keep_stage_on_failure:
            log.error("Build failed. Staging directory kept at: %s", stage_dir)
        else:
            _remove_tree_if_exists(stage_dir)
            log.error("Build failed. Staging directory removed.")
        raise


# ============================================================================
# CLI
# ============================================================================

def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the TourVsTravel local build pipeline."
    )
    parser.add_argument(
        "--lang",
        type=str,
        default=None,
        help="Build only one enabled language code (e.g. en, ar, fr).",
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
        help="Keep the staging directory for debugging when a build step fails.",
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
            requested_lang=args.lang,
            output_dir=args.output_dir.resolve(),
            keep_stage_on_failure=args.keep_stage_on_failure,
        )
    except (BuildError, GenerateHomeError, GenerateRobotsError) as exc:
        log.error("%s", exc)
        return 1
    except Exception as exc:
        log.exception("Unhandled build error: %s", exc)
        return 1

    log.info("Build completed successfully: %s", final_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
