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
    connection = commands.add_parser("connect", help="Start the interactive Windows connection helper")
    connection.add_argument("--controller-key", required=True, type=Path, help="Pinned controller PUBLIC key file")
    commands.add_parser("doctor", help="Check runtime prerequisites without revealing credentials")
    commands.add_parser("windows-smoke", help="Open Calculator and test three calculations; clears its current calculation")
    automatic = commands.add_parser("self-test", help="Automatically test Windows inventory, Calculator and disposable Notepad; save a report")
    automatic.add_argument("--with-cloud", action="store_true", help="Also run AI tasks; prompts securely for a missing API key")
    commands.add_parser("scan", help="Discover apps and persist installation/version changes")
    commands.add_parser("apps", help="List discovered apps and documentation status")
    study = commands.add_parser("study-next", help="Research one queued app within the daily background budget")
    study.add_argument("--daily-limit", type=int, default=3, choices=range(1, 51))
    campaign = commands.add_parser("study-campaign", help="Study queued apps and design capability experiments; no desktop mutations")
    campaign.add_argument("--daily-limit", type=int, default=50, choices=range(1, 51))
    campaign.add_argument("--max-apps", type=int, default=5, choices=range(1, 51))
    campaign.add_argument("--max-plans", type=int, default=3, choices=range(0, 51))
    commands.add_parser("learning-report", help="Show current evidence counts and campaign progress")
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
        if args.command == "connect":
            from .remote_ui import launch_connection
            launch_connection(args.data_dir, args.controller_key)
            return
        if args.command == "ui":
            from .ui import launch
            launch(args.data_dir)
            return
        if args.command == "self-test":
            import sys
            if sys.platform != "win32":
                raise RuntimeError("Live self-test needs an interactive Windows computer; cloud Linux cannot control your PC.")
            from .automation_worker import initialize_com
            cleanup = initialize_com()
            try:
                from .self_test import self_test
                cloud = None
                if args.with_cloud:
                    key = os.getenv("AGENT_API_KEY") or os.getenv("OPENAI_API_KEY")
                    if not key:
                        from getpass import getpass
                        key = getpass("OpenAI API key (hidden; blank skips cloud checks): ").strip()
                    if key:
                        cloud = CloudResearcher(key=key)
                report = self_test(args.data_dir, cloud=cloud)
                print(json.dumps(report, indent=2))
                if report["status"] in ("failed", "cancelled"):
                    parser.exit(1, "Self-test did not pass; see the saved report.\n")
            finally:
                cleanup()
            return
        if args.command == "discover":
            result = installed_apps()
        elif args.command in ("doctor", "windows-smoke"):
            from .windows_checks import doctor, calculator_smoke
            result = doctor() if args.command == "doctor" else calculator_smoke()
        elif args.command in ("scan", "apps", "study-next", "study-campaign", "learning-report"):
            catalog = Catalog(args.data_dir)
            try:
                if args.command == "scan":
                    result = catalog.sync(scan_apps())
                elif args.command == "apps":
                    result = [{key: value for key, value in app.items() if key not in ("blueprint", "location")} for app in catalog.apps()]
                elif args.command == "learning-report":
                    result = {"overview": catalog.learning_overview(), "campaign": catalog.setting("campaign_state", {})}
                elif args.command == "study-campaign":
                    from .campaign import study_campaign
                    if os.name == "nt":
                        catalog.sync(scan_apps())
                    result = study_campaign(catalog, CloudResearcher(), lambda text: print(text), args.daily_limit, args.max_apps, args.max_plans)
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
