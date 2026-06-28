#!/usr/bin/env python3
"""Render a preview of the HotSOS HTML dashboard from input summary.

This is a developer helper used to iterate on the HTMLFormatter output.
It writes the rendered HTML to a file for visual inspection.
"""
import os
import sys

import yaml
from hotsos.core.config import HotSOSConfig  # noqa: E402
from hotsos.core.formatters import HTMLFormatter  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    """Render the summary file given as argv[1] to an HTML preview."""
    if len(sys.argv) < 2:
        sys.stderr.write(f"usage: {sys.argv[0]} <summary.yaml>\n")
        raise SystemExit(2)

    HotSOSConfig.templates_path = os.path.join(ROOT, 'hotsos', 'templates')
    with open(sys.argv[1], encoding='utf-8') as fd:
        summary = yaml.safe_load(fd) or {}

    html = HTMLFormatter().dump(summary)
    out_path = os.path.join(ROOT, 'examples', 'dashboard-preview.html')
    with open(out_path, 'w', encoding='utf-8') as fd:
        fd.write(html)

    print(f"wrote {out_path} ({len(html)} bytes)")


if __name__ == '__main__':
    main()
