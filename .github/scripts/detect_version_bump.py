"""Detect the minimum semantic version bump of a model pull request.

The Ersilia Model Hub releases every merged change as ``vMAJOR.MINOR.PATCH``:

* PATCH: metadata only (``metadata.yml``, README, descriptions or direction in
  ``run_columns.csv``). No rebuild.
* MINOR: code, dependencies or checkpoints change, and the outputs on the
  example input stay within ``1e-4`` of the previous version.
* MAJOR: outputs change: values beyond ``1e-4``, or column names, order, type
  or number, or a different number of rows.

The script has three sub-commands, used in this order by
``check-version-label.yml``:

``files``
    Classify the files changed between the base commit and the working tree.
``outputs``
    Compare a fresh run of the model on the example input with the example
    output of the base commit.
``verdict``
    Check that the pull request carries exactly one version label and that the
    label is not lower than the detected minimum.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import subprocess
import sys
from pathlib import Path

import yaml

TOLERANCE = 1e-4
BUMPS = ["none", "patch", "minor", "major"]
LABELS = {
    "no-release": "none",
    "semver:patch": "patch",
    "semver:minor": "minor",
    "semver:major": "major",
}

COLUMNS_FILE = "model/framework/columns/run_columns.csv"
EXAMPLE_INPUT = "model/framework/examples/run_input.csv"
EXAMPLE_OUTPUT = "model/framework/examples/run_output.csv"

# Files that never reach the model image or its outputs.
NO_EFFECT_PREFIXES = (".github/",)
NO_EFFECT_FILES = {".gitignore", ".gitattributes", "CLAUDE.md", "AGENTS.md"}
# Files whose change is metadata only.
PATCH_FILES = {"metadata.yml", "metadata.json", "README.md", "LICENSE", "access.json"}


def higher(a: str, b: str) -> str:
    """Return the higher of two bump levels."""
    return a if BUMPS.index(a) >= BUMPS.index(b) else b


def git_show(base: str, path: str) -> str | None:
    """Return the content of ``path`` at commit ``base``, or None if absent."""
    result = subprocess.run(
        ["git", "show", f"{base}:{path}"], check=False, capture_output=True, text=True
    )
    return result.stdout if result.returncode == 0 else None


def read_text(path: str) -> str | None:
    """Return the content of a working-tree file, or None if absent."""
    p = Path(path)
    return p.read_text() if p.exists() else None


def parse_csv(text: str | None) -> tuple[list[str], list[list[str]]]:
    """Parse CSV text into a header and rows; empty input gives empty lists."""
    if not text:
        return [], []
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return [], []
    return rows[0], rows[1:]


def column_signature(text: str | None) -> list[tuple[str, str]]:
    """Return the (name, type) pairs of a ``run_columns.csv``, in order."""
    header, rows = parse_csv(text)
    if not header:
        return []
    i_name, i_type = header.index("name"), header.index("type")
    return [(r[i_name].strip(), r[i_type].strip()) for r in rows if r]


def as_float(value: str) -> float | None:
    """Return ``value`` as a float, or None if it is not numeric."""
    try:
        return float(value)
    except ValueError:
        return None


def cells_differ(a: str, b: str) -> bool:
    """Return True if two output cells differ beyond the tolerance."""
    fa, fb = as_float(a), as_float(b)
    if fa is None or fb is None:
        return a.strip() != b.strip()
    if math.isnan(fa) or math.isnan(fb):
        return not (math.isnan(fa) and math.isnan(fb))
    return abs(fa - fb) > TOLERANCE


def compare_outputs(
    reference: str | None, candidate: str | None, compare_values: bool
) -> list[str]:
    """Compare two example outputs and list the differences that make a MAJOR.

    Parameters
    ----------
    reference : str or None
        CSV text of the previous output.
    candidate : str or None
        CSV text of the new output.
    compare_values : bool
        Compare cell values; False for models with variable output.

    Returns
    -------
    list of str
        Human-readable differences; empty when the outputs match.
    """
    ref_header, ref_rows = parse_csv(reference)
    new_header, new_rows = parse_csv(candidate)
    # Ersilia-formatted outputs carry key and input columns; run.sh outputs do not.
    ref_cols = [c for c in ref_header if c not in ("key", "input")]
    new_cols = [c for c in new_header if c not in ("key", "input")]
    if ref_cols != new_cols:
        return [f"output columns changed: {ref_cols} -> {new_cols}"]
    if len(ref_rows) != len(new_rows):
        return [f"number of output rows changed: {len(ref_rows)} -> {len(new_rows)}"]
    if not compare_values:
        return []
    ref_idx = [ref_header.index(c) for c in ref_cols]
    new_idx = [new_header.index(c) for c in new_cols]
    diffs = []
    for row, (r, n) in enumerate(zip(ref_rows, new_rows), start=1):
        for col, i, j in zip(ref_cols, ref_idx, new_idx):
            a = r[i] if i < len(r) else ""
            b = n[j] if j < len(n) else ""
            if cells_differ(a, b):
                diffs.append(f"row {row}, column {col}: {a} -> {b}")
    if diffs:
        shown = "; ".join(diffs[:5])
        more = f" (and {len(diffs) - 5} more)" if len(diffs) > 5 else ""
        return [f"output values differ beyond {TOLERANCE}: {shown}{more}"]
    return []


def read_metadata() -> dict:
    """Return the model metadata from ``metadata.yml`` or ``metadata.json``."""
    for name in ("metadata.yml", "metadata.json"):
        text = read_text(name)
        if text is not None:
            return (
                yaml.safe_load(text) if name.endswith("yml") else json.loads(text)
            ) or {}
    return {}


def cmd_files(args: argparse.Namespace) -> dict:
    """Classify the changed files and decide whether the model must be run."""
    changed = subprocess.run(
        ["git", "diff", "--name-only", args.base, "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    metadata = read_metadata()
    fixed = "Fixed" in str(metadata.get("Output Consistency", "Fixed"))
    online = metadata.get("Source") == "Online"

    bump, reasons, needs_run = "none", [], False
    for path in changed:
        if path in NO_EFFECT_FILES or path.startswith(NO_EFFECT_PREFIXES):
            continue
        if path in PATCH_FILES:
            bump = higher(bump, "patch")
            reasons.append(f"patch: {path} (metadata)")
        elif path == COLUMNS_FILE:
            before = column_signature(git_show(args.base, path))
            after = column_signature(read_text(path))
            if before != after:
                bump = "major"
                reasons.append(f"major: column names, order or types changed in {path}")
            else:
                bump = higher(bump, "patch")
                reasons.append(f"patch: {path} (descriptions or direction only)")
        elif path == EXAMPLE_OUTPUT:
            diffs = compare_outputs(git_show(args.base, path), read_text(path), fixed)
            if diffs:
                bump = "major"
                reasons.extend(f"major: {d} (committed {path})" for d in diffs)
        elif path == EXAMPLE_INPUT:
            bump = higher(bump, "minor")
            reasons.append(
                f"minor: {path} changed, so outputs cannot be compared with the base; "
                "check by hand whether outputs changed"
            )
        else:
            bump = higher(bump, "minor")
            needs_run = True
            reasons.append(f"minor: {path} (code, dependencies or checkpoints)")

    # A run can only raise MINOR to MAJOR, and only when outputs are comparable.
    needs_run = needs_run and bump == "minor" and not online
    if needs_run and EXAMPLE_INPUT in changed:
        needs_run = False
    return {
        "bump": bump,
        "needs_run": needs_run,
        "fixed_output": fixed,
        "reasons": reasons,
    }


def cmd_outputs(args: argparse.Namespace) -> dict:
    """Compare a fresh run on the example input with the base example output."""
    fresh = read_text(args.fresh)
    if not fresh:
        # Failing here leaves no cached result, so the verdict asks for a fix
        return {
            "bump": "major",
            "reasons": [],
            "errors": [
                "run.sh produced no output on the example input; see the step above"
            ],
        }
    diffs = compare_outputs(git_show(args.base, EXAMPLE_OUTPUT), fresh, args.fixed)
    result = {
        "bump": "major" if diffs else "minor",
        "reasons": [f"major: {d} (fresh run vs base)" for d in diffs]
        or ["minor: fresh outputs match the base example output"],
        "warnings": [],
    }
    committed = compare_outputs(read_text(EXAMPLE_OUTPUT), fresh, args.fixed)
    if committed:
        result["warnings"].append(
            f"{EXAMPLE_OUTPUT} in this PR does not match a fresh run: {committed[0]}. "
            "Regenerate it before merging."
        )
    return result


def cmd_verdict(args: argparse.Namespace) -> dict:
    """Check the PR labels against the detected minimum bump."""
    files = json.loads(Path(args.files).read_text())
    detected, reasons = files["bump"], list(files["reasons"])
    warnings: list[str] = []
    errors: list[str] = []

    if files.get("needs_run"):
        if args.outputs and Path(args.outputs).exists():
            outputs = json.loads(Path(args.outputs).read_text())
            detected = higher(detected, outputs["bump"])
            reasons.extend(outputs["reasons"])
            warnings.extend(outputs.get("warnings", []))
        else:
            errors.append(
                "The model could not be run on the example input, so a change in "
                "outputs cannot be ruled out. Fix the run, or re-run this check."
            )

    labels = [x for x in json.loads(args.labels) if x in LABELS]
    if len(labels) != 1:
        errors.append(
            f"Add exactly one version label ({', '.join(LABELS)}); found {labels or 'none'}."
        )
        chosen = None
    else:
        chosen = LABELS[labels[0]]
        if BUMPS.index(chosen) < BUMPS.index(detected):
            errors.append(
                f"Label {labels[0]} is lower than the detected minimum ({detected})."
            )
    return {
        "detected": detected,
        "label": chosen,
        "reasons": reasons,
        "warnings": warnings,
        "errors": errors,
    }


def write_summary(result: dict, title: str) -> None:
    """Append a Markdown summary to the GitHub job summary, if available."""
    lines = [f"### {title}", ""]
    for key in ("detected", "label", "bump", "needs_run"):
        if key in result:
            lines.append(f"- **{key}:** `{result[key]}`")
    for key in ("errors", "warnings", "reasons"):
        for item in result.get(key, []):
            lines.append(f"- {key[:-1]}: {item}")
    text = "\n".join(lines) + "\n"
    print(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as f:
            f.write(text)


def main() -> int:
    """Parse arguments, run one sub-command and write its JSON result."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("files")
    p.add_argument("--base", required=True, help="Base commit SHA")
    p.add_argument("--out", required=True)

    p = sub.add_parser("outputs")
    p.add_argument("--base", required=True, help="Base commit SHA")
    p.add_argument("--fresh", required=True, help="CSV from running run.sh")
    p.add_argument("--fixed", action="store_true", help="Compare values too")
    p.add_argument("--out", required=True)

    p = sub.add_parser("verdict")
    p.add_argument("--files", required=True, help="JSON from the files step")
    p.add_argument("--outputs", default="", help="JSON from the outputs step")
    p.add_argument("--labels", required=True, help="JSON list of PR label names")
    p.add_argument("--out", required=True)

    args = parser.parse_args()
    handler = {"files": cmd_files, "outputs": cmd_outputs, "verdict": cmd_verdict}
    result = handler[args.command](args)
    Path(args.out).write_text(json.dumps(result, indent=2))
    write_summary(result, f"Version bump: {args.command}")
    for warning in result.get("warnings", []):
        print(f"::warning::{warning}")
    for error in result.get("errors", []):
        print(f"::error::{error}")
    return 1 if result.get("errors") else 0


if __name__ == "__main__":
    sys.exit(main())
