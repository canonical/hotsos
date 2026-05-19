#!/usr/bin/env python3

import os
import argparse
import yaml
import logging as log
from contextlib import suppress

def is_log_file(path):
    """Check if the path (or any in a list) points to a log file."""
    if isinstance(path, list):
        return any(is_log_file(p) for p in path)
    return 'log' in os.path.basename(path).lower()

def analyze_yaml_files(base_path):
    """Analyze YAML files for input checks with log file paths."""
    input_checks = []
    files_with_input = {}
    files_analyzed = 0

    for root, _, files in os.walk(base_path):
        log.debug(f"Analyzing scenarios in: {root}")
        for file in files:
            if file.endswith('.yaml'):
                file_path = os.path.join(root, file)
                log.debug(f"Analyzing scenario file: {file_path}")
                with suppress(Exception):
                    with open(file_path, 'r') as f:
                        data = yaml.safe_load(f)
                        files_analyzed += 1
                        checks = data.get('checks', {})
                        for check_name, check in checks.items():
                            input_check = check.get('input') if isinstance(check, dict) else None
                            if input_check and 'path' in input_check:
                                if is_log_file(input_check['path']):
                                    input_checks.append((file_path, check_name))
                                    files_with_input.setdefault(file_path, []).append(check_name)
                            elif input_check and 'command' in input_check:
                                if input_check['command'] == 'journalctl':
                                    input_checks.append((file_path, check_name))
                                    files_with_input.setdefault(file_path, []).append(check_name)
                            else:
                                log.debug(f"Not an input check, skipping: {check_name}")

    return input_checks, files_with_input, files_analyzed

def print_short_report(input_checks, files_with_input, files_analyzed):
    print(f"Number of 'input' checks: {len(input_checks)}")
    print(f"Number of scenario files with 'input' checks: {len(files_with_input)}")
    print(f"Number of scenario files analyzed: {files_analyzed}")

def print_full_report(files_with_input):
    print(f"===================================================")
    print("Files with 'input' checks (log files):")
    for file, checks in files_with_input.items():
        print(f"- {file.removeprefix("../../")}:")
        for check in checks:
            print(f"    - {check}")
    print(f"===================================================")

def main():
    parser = argparse.ArgumentParser(description="Generate a report of scenario files with the 'input' checks "
                                                 "which relay on log messages.")
    parser.add_argument('--scenario-path', default='../../hotsos/defs/scenarios',
                        help="Location of the scenario definitions (default: ../../hotsos/defs/scenarios)")
    parser.add_argument('--report', choices=['short', 'full'], default='short',
                        help="Type of report to generate (default: short)")
    parser.add_argument('--debug', action='store_true', help="Enable debug output")
    args = parser.parse_args()

    log.basicConfig(
        level=log.DEBUG if args.debug else log.WARNING,
        format='%(levelname)s: %(message)s'
    )

    base_path = args.scenario_path
    input_checks, files_with_input, files_analyzed = analyze_yaml_files(base_path)

    if args.report == 'full':
        print_full_report(files_with_input)
    print_short_report(input_checks, files_with_input, files_analyzed)

main()
