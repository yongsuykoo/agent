import argparse
import json
import os
import sqlite3
from pathlib import Path
from .discovery import installed_apps
from .knowledge import KnowledgeStore
from .research import CloudResearcher, research_app


def main():
    parser = argparse.ArgumentParser(description="Application agent foundation")
    parser.add_argument("--data-dir", type=Path, default=Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "AppAgent")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("discover", help="Read installed Windows application metadata")
    commands.add_parser("ui", help="Launch Windows chat and push-to-talk interface")
    commands.add_parser("doctor", help="Check runtime prerequisites without revealing credentials")
    commands.add_parser("windows-smoke", help="Open Calculator and test three calculations; clears its current calculation")
    blueprint = commands.add_parser("blueprint", help="Create or inspect an app knowledge record")
    blueprint.add_argument("name")
    blueprint.add_argument("--create", action="store_true")
    blueprint.add_argument("--version", default="")
    research = commands.add_parser("research", help="Find documentation and build an unverified app blueprint using cloud AI")
    research.add_argument("name")
    research.add_argument("--version", default="")
    research.add_argument("--source", action="append", help="Optional documentation HTTPS URL; repeat up to five times")
    args = parser.parse_args()
    try:
        if args.command == "ui":
            from .ui import launch
            launch(args.data_dir)
            return
        if args.command == "discover":
            result = installed_apps()
        elif args.command in ("doctor", "windows-smoke"):
            from .windows_checks import doctor, calculator_smoke
            result = doctor() if args.command == "doctor" else calculator_smoke()
        else:
            store = KnowledgeStore(args.data_dir / "knowledge.sqlite3")
            try:
                if args.command == "research":
                    result = research_app(args.name, args.version, CloudResearcher(), args.source)
                    store.save_research(result)
                else:
                    result = store.create(args.name, args.version) if args.create else store.get(args.name)
            finally:
                store.close()
        print(json.dumps(result, indent=2))
    except sqlite3.IntegrityError:
        parser.exit(1, "Blueprint already exists; inspect it without --create.\n")
    except (RuntimeError, KeyError, ValueError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
