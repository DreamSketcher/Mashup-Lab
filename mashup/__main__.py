"""Validate and inspect a project without producing audio."""
import argparse
import json
import sys
from pathlib import Path
from .build_manifest import ManifestError, load_manifest
from .model import ProjectError, load_project, plan_project
from .plan_validation import load_plan, validate_plan
from .trust_policy import PolicyError, load_policy, compare_policy


def main():
    parser = argparse.ArgumentParser(prog='python -m mashup')
    parser.add_argument('command', choices=['validate', 'plan', 'validate-plan', 'inspect-manifest', 'compare-policy'])
    parser.add_argument('project', type=Path)
    parser.add_argument('policy', type=Path, nargs='?')
    args = parser.parse_args()
    if (args.command == 'compare-policy') != (args.policy is not None):
        parser.error('compare-policy requires a policy path; other commands do not accept one')
    try:
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
