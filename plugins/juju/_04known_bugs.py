#!/usr/bin/python3
from common import searchtools
from common.known_bugs_utils import add_known_bug
from juju_common import (
    JUJU_LOG_PATH
)

# maximum number of chars to print when a matching text is detected.
MAX_MATCH_CHARS = 200


def detect_known_bugs():
    """Unit fails to start complaining there are members in the relation."""
    known_bugs = {
        1910958: {
            "description": ("Unit fails to start complaining there are "
                            "members in the relation."),
            "pattern": (
                r'.* manifold worker returned unexpected error: failed to '
                r'initialize uniter for "[A-Za-z0-9-]+": cannot create '
                r'relation state tracker: cannot remove persisted state, '
                r'relation \d+ has members')
            }
        }

    s = searchtools.FileSearcher()
    for bug in known_bugs:
        s.add_search_term(known_bugs[bug]["pattern"],
                          f"{JUJU_LOG_PATH}/*", tag=bug)

    results = s.search()

    for bug in known_bugs:
        if results.find_by_tag(bug):
            add_known_bug(bug, known_bugs.get("description"))


if __name__ == "__main__":
    detect_known_bugs()
