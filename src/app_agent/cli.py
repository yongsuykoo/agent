import argparse
import json
import os
import sqlite3
from pathlib import Path
from .machine import scan_machine, machine_report
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
    commands.add_parser('file-smoke',help='Automatically test disposable file/folder copies and ZIP verification; no desktop or API key needed')
    automatic = commands.add_parser("self-test", help="Automatically test Windows inventory, Calculator and disposable Notepad; save a report")
    automatic.add_argument("--with-cloud", action="store_true", help="Also run AI tasks; prompts securely for a missing API key")
    automatic.add_argument("--with-office", action="store_true", help="Also create and verify fresh Excel/Word test files when installed; no cloud calls")
    commands.add_parser("scan", help="Discover apps and persist installation/version changes")
    commands.add_parser("machine-report", help="Show local Windows, app-interface and installation evidence")
    commands.add_parser("knowledge-map", help="Show the versioned system/app evidence graph")
    query=commands.add_parser("knowledge-query", help="Retrieve local evidence relevant to a task; no provider calls")
    query.add_argument("task")
    commands.add_parser("apps", help="List discovered apps and documentation status")
    commands.add_parser('jobs', help='Show saved goals, progress and recovery states locally')
    resident=commands.add_parser('worker',help='Run authorized saved goals and schedules in this Windows session without the GUI')
    resident.add_argument('--once',action='store_true',help='Run one supervisor cycle then exit')
    commands.add_parser('worker-status',help='Show local background worker state without revealing tasks or credentials')
    commands.add_parser('enable-startup',help='Start the local background worker when this Windows account logs in')
    commands.add_parser('disable-startup',help='Remove this agent current-account login startup')
    commands.add_parser('remember-key',help='Prompt locally and encrypt a provider key for this Windows account')
    commands.add_parser('forget-key',help='Delete the remembered encrypted provider key')
    schedule=commands.add_parser('schedule',help='Schedule a goal; missed recurring slots coalesce into one occurrence')
    schedule.add_argument('task');schedule.add_argument('--at',required=True,help='ISO 8601 time with timezone, e.g. 2026-10-09T09:00:00+08:00')
    schedule.add_argument('--every-minutes',type=float)
    schedule.add_argument('--autonomous',action='store_true');schedule.add_argument('--vision',action='store_true')
    commands.add_parser('schedules',help='List local schedules and outstanding occurrences')
    for verb in ('pause','resume','cancel'):
        entry=commands.add_parser(verb+'-schedule');entry.add_argument('id')
    submit = commands.add_parser('submit', help='Save a goal for the Windows UI to execute; no desktop action here')
    submit.add_argument('task')
    submit.add_argument('--autonomous', action='store_true',help='Authorize automatic actions for this submitted goal')
    submit.add_argument('--vision', action='store_true',help='Authorize selected-window screenshot sharing for this goal')
    commands.add_parser('pause-jobs', help='Pause the queue and fence running tasks before their next action')
    commands.add_parser('resume-jobs', help='Resume safe saved goals; unverified actions still need review')
    cancel_job = commands.add_parser('cancel-job', help='Cancel a saved goal')
    cancel_job.add_argument('id')
    study = commands.add_parser("study-next", help="Research one queued app within the daily background budget")
    study.add_argument("--daily-limit", type=int, default=0, choices=range(0, 10001))
    campaign = commands.add_parser("study-campaign", help="Study queued apps and design capability experiments; no desktop mutations")
    campaign.add_argument("--daily-limit", type=int, default=0, choices=range(0, 10001))
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
        if args.command=='file-smoke':
            from .file_checks import file_smoke
            result=file_smoke(args.data_dir)
            print(json.dumps(result,indent=2))
            if result['status']!='passed':parser.exit(1,'File checks failed or were cancelled. Read the saved report.\n')
            return
        if args.command=='worker':
            from .resident import run_resident
            run_resident(args.data_dir,once=args.once);return
        if args.command=='worker-status':
            path=args.data_dir/'worker-status.json'
            result=json.loads(path.read_text()) if path.exists() else {'state':'not_started'}
        elif args.command in ('remember-key','forget-key'):
            from .local_credentials import save_key,forget_key
            if args.command=='remember-key':
                from getpass import getpass
                save_key(args.data_dir,getpass('Provider API key (encrypted for this Windows account): '))
                result={'remembered':True}
            else:forget_key(args.data_dir);result={'remembered':False}
        elif args.command in ('enable-startup','disable-startup'):
            from .startup import set_startup
            set_startup(args.data_dir,args.command=='enable-startup');result={'login_startup':args.command=='enable-startup'}
        elif args.command in ('schedule','schedules','pause-schedule','resume-schedule','cancel-schedule'):
            from .schedules import Schedules
            schedules=Schedules(args.data_dir)
            try:
                if args.command=='schedule':result={'id':schedules.create(args.task,at=args.at,interval=args.every_minutes*60 if args.every_minutes is not None else None,
                    autonomous=args.autonomous,use_vision=args.vision),'state':'enabled'}
                elif args.command=='schedules':result=schedules.list()
                else:result={args.command:getattr(schedules,args.command.split('-')[0])(args.id)}
            finally:schedules.close()
        else:
            return _command(args,parser)
        print(json.dumps(result,indent=2));return
    except (RuntimeError,KeyError,ValueError,OSError) as error:
        parser.exit(1,f'{error}\n')


def _command(args,parser):
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
                report = self_test(args.data_dir, cloud=cloud,with_office=args.with_office)
                print(json.dumps(report, indent=2))
                if report["status"] in ("failed", "cancelled"):
                    parser.exit(1, "Self-test did not pass; see the saved report.\n")
            finally:
                cleanup()
            return
        if args.command in ('jobs','submit','pause-jobs','resume-jobs','cancel-job'):
            from .jobs import Jobs
            jobs = Jobs(args.data_dir)
            try:
                if args.command == 'submit':
                    result = {'id':jobs.submit(args.task,autonomous=args.autonomous,use_vision=args.vision),'status':'queued'}
                elif args.command == 'pause-jobs':
                    jobs.pause(); result = {'paused':True}
                elif args.command == 'resume-jobs':
                    jobs.resume(); result = {'paused':False}
                elif args.command == 'cancel-job':
                    result = {'cancelled':jobs.cancel(args.id)}
                else:
                    result = [{k:v for k,v in item.items() if k not in ('owner','owner_pid','lease')}
                              for item in jobs.list()]
            finally:
                jobs.close()
        elif args.command == "discover":
            result = installed_apps()
        elif args.command in ("doctor", "windows-smoke"):
            from .windows_checks import doctor, calculator_smoke
            result = doctor() if args.command == "doctor" else calculator_smoke()
        elif args.command in ("scan", "apps", "study-next", "study-campaign", "learning-report", "machine-report", "knowledge-map", "knowledge-query"):
            catalog = Catalog(args.data_dir)
            try:
                if args.command == "scan":
                    result = scan_machine(catalog, scanner=scan_apps)
                elif args.command == "apps":
                    result = [{key: value for key, value in app.items() if key not in ("blueprint", "location")} for app in catalog.apps()]
                elif args.command == "machine-report":
                    result = machine_report(catalog)
                elif args.command in ('knowledge-map','knowledge-query'):
                    from .system_knowledge import graph_report, retrieve
                    result=graph_report(catalog) if args.command=='knowledge-map' else retrieve(catalog,args.task)
                elif args.command == "learning-report":
                    result = {"overview": catalog.learning_overview(), "machine": machine_report(catalog), "campaign": catalog.setting("campaign_state", {})}
                elif args.command == "study-campaign":
                    from .campaign import study_campaign
                    if os.name == "nt":
                        scan_machine(catalog, scanner=scan_apps)
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
