"""Validate, inspect and experimentally render projects."""
import argparse
import json
import os
import platform
import sys
import traceback
from pathlib import Path
from .build_manifest import ManifestError, load_manifest
from .model import ProjectError, load_project, plan_project
from .plan_validation import load_plan, validate_plan
from .trust_policy import PolicyError, load_policy, compare_policy


def main():
    if len(sys.argv) > 1 and sys.argv[1] == 'gui':
        if len(sys.argv) > 2:
            print('usage: python -m mashup gui', file=sys.stderr)
            return 2
        from .session_trace import SessionTrace
        trace = SessionTrace()
        trace.emit('application.start', python=sys.version, platform=platform.platform(), argv=sys.argv, cwd=os.getcwd())
        try:
            from .gui import main as gui_main
        except ImportError as exc:
            trace.emit('application.import_error', error=str(exc), traceback=traceback.format_exc())
            if exc.name == 'PySide6':
                print('error: PySide6 не установлен. Выберите пункт 8 в лаунчере или установите requirements-gui.txt.', file=sys.stderr)
            else:
                print(f'error: cannot load GUI: {exc}. Install requirements-gui.txt and check system Qt dependencies.', file=sys.stderr)
            if trace.path:
                print(f'trace: {trace.path}', file=sys.stderr)
            return 1
        return gui_main(trace)
    if len(sys.argv) > 1 and sys.argv[1] == 'quick-mashup':
        from .quick_mashup import main as quick_mashup_main
        return quick_mashup_main(sys.argv[2:])
    parser = argparse.ArgumentParser(prog='python -m mashup', epilog='For the desktop interface: python -m mashup gui; two-audio CLI: python -m mashup quick-mashup --help')
    parser.add_argument('command', choices=['validate', 'plan', 'validate-plan', 'inspect-manifest', 'compare-policy', 'render', 'quick-mashup', 'gui'])
    parser.add_argument('project', type=Path)
    parser.add_argument('policy', type=Path, nargs='?')
    parser.add_argument('-o', '--output', type=Path, help='new output WAV path (render only)')
    args = parser.parse_args()
    if (args.command == 'render') != (args.output is not None):
        parser.error('render requires --output; other commands do not accept it')
    if (args.command == 'compare-policy') != (args.policy is not None):
        parser.error('compare-policy requires a policy path; other commands do not accept one')
    try:
        if args.command == 'render':
            from .render import render
            print(json.dumps(render(args.project, args.output), indent=2))
            return 0
        if args.command == 'compare-policy':
            identity = load_manifest(args.project)
            try:
                status = compare_policy(identity, load_policy(args.policy))
            except PolicyError as exc:
                print(json.dumps({'comparison': 'UNAVAILABLE', 'trust': 'not_checked',
                                  'execution': 'not_checked', 'detail': str(exc)}))
                return 2
            print(json.dumps({'comparison': status, 'trust': 'not_checked', 'execution': 'not_checked'}))
            return 0 if status == 'MATCH' else 1
        if args.command == 'inspect-manifest':
            identity = load_manifest(args.project)
            print(json.dumps({'planner_id': identity.planner_id, 'sha256': identity.sha256,
                              'trust': 'not_checked', 'execution': 'not_checked'}, indent=2))
            return 0
        if args.command == 'validate-plan':
            validate_plan(load_plan(args.project))
            print('Plan geometry valid (project and sources not checked).')
            return 0
        plan = plan_project(load_project(args.project), args.project.parent)
    except (ProjectError, ManifestError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 1
    if args.command == 'plan':
        print(json.dumps(plan.to_dict(), indent=2, ensure_ascii=True))
    else:
        print('Project and sources valid (render backend not checked).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
