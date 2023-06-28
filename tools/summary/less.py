#!/usr/bin/env python3
import glob
import os
import sys
import subprocess


def less_summary():
    if len(sys.argv) > 1:
        root = sys.argv[1]
    else:
        root = '.'

    paths = []
    if os.path.isdir(root):
        for encoding in ['yaml', 'json']:
            results = glob.glob(os.path.join(root, f'*.{encoding}'))
            if results:
                paths = results
                break
    else:
        paths = [root]

    for path in paths:
        subprocess.call(['less', path])


if __name__ == "__main__":
    less_summary()
