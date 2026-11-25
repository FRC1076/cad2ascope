"""Command-line entry point (PLAN §6.2). Errors exit 1, warnings exit 0, so CI can tell them apart (§6.6)."""

from __future__ import annotations

import argparse
import sys

from cad2ascope import __version__
from cad2ascope.config import CONFIG_NAME
from cad2ascope.errors import CadError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cad2ascope",
        description="Turn an Onshape robot assembly into an AdvantageScope robot asset.",
    )
    parser.add_argument("--version", action="version", version=f"cad2ascope {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="command")

    p = sub.add_parser("inspect", help="print the joints and parts in an Onshape URDF export")
    p.add_argument("export", help="URDF zip downloaded from Onshape (or its unzipped folder)")

    p = sub.add_parser("init", help=f"write a starter {CONFIG_NAME} from an export")
    p.add_argument("export", help="URDF zip downloaded from Onshape")
    p.add_argument("-o", "--output", default=CONFIG_NAME, help=f"where to write it (default {CONFIG_NAME})")
    p.add_argument("--name", help="robot name shown in AdvantageScope (default: the export's name)")
    p.add_argument("--folder", help="output folder name, Robot_<something> (default: from the name)")
    p.add_argument("--force", action="store_true", help="replace an existing config")

    p = sub.add_parser("build", help="build the AdvantageScope robot folder from an export")
    p.add_argument("export", help="URDF zip downloaded from Onshape")
    p.add_argument("-c", "--config", default=CONFIG_NAME, help=f"team config (default {CONFIG_NAME})")
    p.add_argument(
        "-o", "--out", default="assets/advantagescope", help="custom assets folder (default assets/advantagescope)"
    )
    p.add_argument("--repo-root", default=".", help="robot repo root, for relative paths in the config (default .)")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    try:
        if args.command == "inspect":
            from cad2ascope.inspect_cmd import inspect

            print(inspect(args.export))
        elif args.command == "init":
            from cad2ascope.inspect_cmd import init

            out = init(args.export, args.output, force=args.force, name=args.name, folder=args.folder)
            print(f"Wrote {out}. Fill in signals, ratios and directions, then run 'cad2ascope build'.")
        elif args.command == "build":
            from cad2ascope.build import build

            result = build(args.export, args.config, args.out, args.repo_root)
            for w in result.warnings:
                print(f"Warning: {w}", file=sys.stderr)
            comps = len(result.model.components)
            print(
                f"Built {result.folder}: base model + {comps} moving component{'s' if comps != 1 else ''}, "
                f"{len(result.cameras)} camera(s), {len(result.frames)} frame(s), {len(result.warnings)} warning(s)."
            )
    except CadError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
