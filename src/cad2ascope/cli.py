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

    p = sub.add_parser("codegen", help="write RobotModel.java and its test from an export")
    p.add_argument("export", help="URDF zip downloaded from Onshape")
    p.add_argument("-c", "--config", default=CONFIG_NAME, help=f"team config (default {CONFIG_NAME})")
    p.add_argument("--repo-root", default=".", help="robot repo root; codegen paths are relative to it (default .)")

    p = sub.add_parser("fetch", help="export the assembly from Onshape through the API (cached by Version)")
    p.add_argument("-c", "--config", default=CONFIG_NAME, help=f"team config (default {CONFIG_NAME})")
    p.add_argument("--workspace", action="store_true", help="export the live workspace instead of a Version (preview)")
    p.add_argument("--cache-dir", help="where exports are cached (default ~/.cache/cad2ascope or $CAD2ASCOPE_CACHE)")

    p = sub.add_parser("run", help="fetch from Onshape (or use --zip), then build")
    p.add_argument("-c", "--config", default=CONFIG_NAME, help=f"team config (default {CONFIG_NAME})")
    p.add_argument("--zip", help="use this URDF zip (for example one dropped in cad/drops/) instead of the API")
    p.add_argument("--workspace", action="store_true", help="export the live workspace instead of a Version (preview)")
    p.add_argument("--cache-dir", help="where exports are cached (default ~/.cache/cad2ascope or $CAD2ASCOPE_CACHE)")
    p.add_argument(
        "-o", "--out", default="assets/advantagescope", help="custom assets folder (default assets/advantagescope)"
    )
    p.add_argument("--repo-root", default=".", help="robot repo root, for relative paths in the config (default .)")
    return parser


def _fetch(args):
    from pathlib import Path

    from cad2ascope.config import load_config
    from cad2ascope.onshape import fetch

    cfg = load_config(args.config)
    if not cfg.robot.onshape_url:
        raise CadError(
            f"{args.config} has no robot.onshape_url. Paste the main assembly's URL there, or pass a zip with --zip."
        )
    return fetch(
        cfg.robot.onshape_url,
        cfg.robot.version,
        cfg.robot.configuration,
        workspace=args.workspace,
        cache_dir=Path(args.cache_dir) if args.cache_dir else None,
        log=lambda m: print(m, file=sys.stderr),
    )


def _codegen(model, cameras, frames, source: str, repo_root: str) -> None:
    from pathlib import Path

    from cad2ascope.codegen import generate, write

    java, test = generate(model, cameras, frames, source)
    written = write(java, test, model.config, Path(repo_root))
    for p in written.generated:
        print(f"Generated {p}")
    for p in written.created:
        print(f"Created {p} (yours to edit from now on)")


def _print_build(result) -> None:
    for w in result.warnings:
        print(f"Warning: {w}", file=sys.stderr)
    comps = len(result.model.components)
    print(
        f"Built {result.folder}: base model + {comps} moving component{'s' if comps != 1 else ''}, "
        f"{len(result.cameras)} camera(s), {len(result.frames)} frame(s), {len(result.warnings)} warning(s)."
    )


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

            _print_build(build(args.export, args.config, args.out, args.repo_root))
        elif args.command == "fetch":
            got = _fetch(args)
            print(got.zip_path)
            print(f"{'Cached' if got.cached else 'Exported'}; {got.calls} API call(s).", file=sys.stderr)
        elif args.command == "run":
            from cad2ascope.build import build
            from cad2ascope.codegen import source_description

            if args.zip:
                result = build(args.zip, args.config, args.out, args.repo_root)
                source = source_description(None, result.source_name, result.source_sha256)
            else:
                got = _fetch(args)
                result = build(got.zip_path, args.config, args.out, args.repo_root, onshape_source=got.source)
                source = source_description(got.source, result.source_name, result.source_sha256)
            _print_build(result)
            _codegen(result.model, result.cameras, result.frames, source, args.repo_root)
        elif args.command == "codegen":
            from pathlib import Path

            from cad2ascope.build import analyze
            from cad2ascope.codegen import source_description
            from cad2ascope.config import load_config
            from cad2ascope.export import load_export

            cfg = load_config(args.config)
            model, cameras, frames = analyze(args.export, cfg, Path(args.repo_root))
            with load_export(args.export) as export:
                sha = export.sha256
            _codegen(model, cameras, frames, source_description(None, Path(args.export).name, sha), args.repo_root)
    except CadError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
