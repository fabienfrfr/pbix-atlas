"""Command-line entry point: `pbix-atlas-codegen my_report.pbix -o pipeline.py`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .codegen import generate_python_pipeline


def main(argv: list[str] | None = None) -> int:
    """Main. Takes `argv`."""
    parser = argparse.ArgumentParser(
        prog="pbix-atlas-codegen",
        description=(
            "Generate a single standalone Python file reproducing a .pbix report's "
            "full chain: source -> extraction -> Power Query transforms -> semantic "
            "model -> Vizro dashboard. Best-effort: unsupported steps/measures are "
            "left as explicit TODOs, never guessed or silently dropped."
        ),
    )
    parser.add_argument("pbix_path", type=Path, help="Path to the input .pbix file")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output .py path (default: <pbix name>_pipeline.py next to the input file)",
    )
    args = parser.parse_args(argv)

    if not args.pbix_path.exists():
        print(f"error: {args.pbix_path} does not exist", file=sys.stderr)
        return 1

    output = args.output or args.pbix_path.with_name(f"{args.pbix_path.stem}_pipeline.py")
    generate_python_pipeline(args.pbix_path, output)
    print(f"Generated: {output}")
    print('Search the file for "TODO" to find every step/measure needing manual completion.')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
