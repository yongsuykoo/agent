import argparse
import json
import os
import sqlite3
from pathlib import Path
from .discovery import installed_apps, scan_apps
from .catalog import Catalog
from .learning import learn_next
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
    commands.add_parser("scan", help="Discover apps and persist installation/version changes")
    commands.add_parser("apps", help="List discovered apps and documentation status")
    study = commands.add_parser("study-next", help="Research one queued app within the daily background budget")
    study.add_argument("--daily-limit", type=int, default=3, choices=range(1, 51))
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
        elif args.command in ("scan", "apps", "study-next"):
            catalog = Catalog(args.data_dir)
            try:
                if args.command == "scan":
                    result = catalog.sync(scan_apps())
                elif args.command == "apps":
                    result = [{key: value for key, value in app.items() if key not in ("blueprint", "location")} for app in catalog.apps()]
                else:
                    result = learn_next(catalog, CloudResearcher(), lambda text: print(text), args.daily_limit)
            finally:
                catalog.close()
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
