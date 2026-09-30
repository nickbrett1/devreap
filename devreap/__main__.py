"""CLI entrypoint: python3 -m devreap [--dry-run] [--days N]

Installed as /usr/local/bin/devreap by install.py.

    devreap                 # reap: stop quiet devcontainers, close their windows
    devreap --dry-run       # show the verdict table, touch nothing
    devreap --days 5        # quieter threshold
    devreap --list-windows  # diagnostic: can we see VS Code windows at all?
"""

import argparse
import json
import sys
import warnings

warnings.filterwarnings("ignore", category=ResourceWarning)

from . import __version__, config, containers, reap, vscode


def _print_windows():
    titles, err = vscode.list_window_titles()
    if err:
        print(f"System Events error: {err}", file=sys.stderr)
    if not titles:
        print("System Events sees no VS Code windows.\n"
              "  • grant Accessibility to whatever runs devreap "
              "(System Settings → Privacy & Security → Accessibility),\n"
              "  • and run it inside your GUI login session (Terminal, not a daemon).")
        return 1
    print(f"VS Code windows visible to System Events ({len(titles)}):")
    for t in titles:
        print(f"  {t}")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="devreap",
        description="Stop devcontainers whose project has gone quiet, and close their VS Code windows.",
    )
    p.add_argument("--dry-run", action="store_true", help="show the decision table, change nothing")
    p.add_argument("--days", type=float, default=None,
                   help="reap when the last human-triggered build is older than this (default: config, 3)")
    p.add_argument("--only", default=None, help="only consider this one workspace")
    p.add_argument("--no-close-windows", action="store_true", help="stop containers but leave VS Code windows alone")
    p.add_argument("--list-windows", action="store_true", help="diagnostic: list the VS Code windows System Events can see")
    p.add_argument("--json", action="store_true", help="emit decisions as JSON")
    p.add_argument("--version", action="version", version=f"devreap {__version__}")
    args = p.parse_args(argv)

    if args.list_windows:
        return _print_windows()

    if not containers.docker_available():
        print("[devreap] docker is not reachable (is OrbStack/Docker running?)", file=sys.stderr)
        return 2

    cfg = config.load()
    try:
        decisions = reap.plan(cfg, days=args.days, only=args.only)
    except containers.DockerError as e:
        print(f"[devreap] {e}", file=sys.stderr)
        return 2

    if not args.dry_run:
        reap.execute(decisions, cfg, dry_run=False,
                     close_windows=not args.no_close_windows)

    if args.json:
        print(json.dumps(decisions, indent=2))
    else:
        header = "devreap — dry run" if args.dry_run else "devreap"
        print(f"{header} (threshold: {args.days if args.days is not None else cfg.get('days')} days)")
        print()
        print(reap.render(decisions))
        n = sum(1 for d in decisions if d["verdict"] == "reap")
        if args.dry_run:
            print(f"\n{n} container(s) would be stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
