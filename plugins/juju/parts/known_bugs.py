#!/usr/bin/python3
from common import (
    constants,
)
from common.searchtools import (
    FileSearcher,
)
from common.known_bugs_utils import (
    add_known_bug,
    BugSearchDef,
)
from juju_common import (
    JUJU_LOG_PATH
)

# NOTE: only LP bugs supported for now
BUG_SEARCHES = [
    BugSearchDef(
        (r'.* manifold worker .+ error: failed to initialize uniter for '
         r'"(\S+)": cannot create relation state tracker: cannot remove '
         r'persisted state, relation (\d+) has members'),
        bug_id="1910958",
        hint="manifold worker returned unexpected error",
        reason=("Unit {} failed to start due to members in relation {} that "
                "cannot be removed."),
        reason_value_render_indexes=[1, 2],
        ),
]


def detect_known_bugs():
    """Unit fails to start complaining there are members in the relation."""
    data_source = f"{JUJU_LOG_PATH}/*.log"
    if constants.USE_ALL_LOGS:
        data_source = f"{data_source}*"

    s = FileSearcher()
    for bugdef in BUG_SEARCHES:
        s.add_search_term(bugdef, data_source)

    results = s.search()

    for bugdef in BUG_SEARCHES:
        bug_results = results.find_by_tag(bugdef.tag)
        if bug_results:
            reason = bugdef.render_reason(bug_results[0])
            add_known_bug(bugdef.tag, reason)


if __name__ == "__main__":
    detect_known_bugs()
