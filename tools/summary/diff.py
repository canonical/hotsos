#!/usr/bin/env python3
import glob
import os
import sys
import subprocess
import tempfile


def diff_summary():
    if len(sys.argv) > 2:
        src = sys.argv[1]
        dst = sys.argv[2]
    else:
        raise ValueError("Not enough args: requires src and dst path.")

    paths = []
    for encoding in ['yaml', 'json']:
        results = glob.glob(os.path.join(src, f'*.{encoding}'))
        if results:
            paths = results
            break

    for path in paths:
        dp = os.path.join(dst, os.path.basename(path))
        out = subprocess.run(['diff', '-y', path, dp], capture_output=True,
                             check=False)
        with tempfile.NamedTemporaryFile() as ftmp:
            with open(ftmp.name, 'wb') as fd:
                fd.write(out.stdout)

            subprocess.call(['less', ftmp.name])


if __name__ == "__main__":
    diff_summary()
