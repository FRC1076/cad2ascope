"""Command-line entry point. Commands arrive in Phase 1 (see docs/PLAN.md §6.2)."""

from __future__ import annotations

import argparse

from cad2ascope import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cad2ascope",
        description="Turn an Onshape robot assembly into an AdvantageScope robot asset.",
    )
    parser.add_argument("--version", action="version", version=f"cad2ascope {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
