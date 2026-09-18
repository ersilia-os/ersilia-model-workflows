#!/usr/bin/env python3
"""Decide whether a model repository needs a new semantic release.

The decision is intentionally based on committed model outputs and columns,
not on generated metadata or workflow artifacts.  This keeps a rerun of a
workflow idempotent and prevents metadata-only commits from creating releases.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


SEMVER_TAG = re.compile(r"^v?(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$")
DEFAULT_OUTPUT_PATH = "model/framework/examples/run_output.csv"
DEFAULT_COLUMNS_PATH = "model/framework/columns/run_columns.csv"


def _git_diff_changed(repo: Path, base: str, target: str, path: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repo), "diff", "--quiet", base, target, "--", path],
        check=False,
    )
    if result.returncode == 0:
        return False
    if result.returncode == 1:
        return True
    raise RuntimeError(
        f"Unable to compare {path!r} between {base!r} and {target!r} "
        f"(git exit code {result.returncode})"
    )


def _parse_tag(tag: str) -> tuple[int, int, int]:
    match = SEMVER_TAG.fullmatch(tag)
    if match is None:
        raise ValueError(
            f"Latest release tag {tag!r} is not supported; expected vMAJOR.MINOR.PATCH"
        )
    return tuple(int(match.group(name)) for name in ("major", "minor", "patch"))


def decide_release(
    repo: Path,
    base_tag: str | None,
    target: str,
    output_path: str = DEFAULT_OUTPUT_PATH,
    columns_path: str = DEFAULT_COLUMNS_PATH,
    initial_version: str = "v1.0.0",
) -> dict[str, object]:
    """Return a release decision suitable for GitHub Actions outputs."""
    if base_tag is None:
        _parse_tag(initial_version)
        return {
            "release": True,
            "tag": initial_version,
            "changed_paths": "",
            "reason": "initial release",
        }

    major, _, _ = _parse_tag(base_tag)
    changed_paths = [
        path
        for path in (output_path, columns_path)
        if _git_diff_changed(repo, base_tag, target, path)
    ]
    if not changed_paths:
        return {
            "release": False,
            "tag": base_tag,
            "changed_paths": "",
            "reason": "model output and columns are unchanged",
        }

    return {
        "release": True,
        "tag": f"v{major + 1}.0.0",
        "changed_paths": ",".join(changed_paths),
        "reason": "observable model output changed",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--base-tag")
    parser.add_argument("--target", required=True)
    parser.add_argument("--output-path", default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--columns-path", default=DEFAULT_COLUMNS_PATH)
    parser.add_argument("--initial-version", default="v1.0.0")
    args = parser.parse_args()

    try:
        decision = decide_release(
            repo=args.repo,
            base_tag=args.base_tag,
            target=args.target,
            output_path=args.output_path,
            columns_path=args.columns_path,
            initial_version=args.initial_version,
        )
    except (RuntimeError, ValueError) as error:
        print(f"release decision failed: {error}", file=sys.stderr)
        return 1

    for key, value in decision.items():
        print(f"{key}={str(value).lower() if isinstance(value, bool) else value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
