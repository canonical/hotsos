import os
import re

from common import (
    constants,
    searchtools,
)


def get_agent_exceptions(agent, logs_path, exc_types,
                         include_time_in_key=False):
    """Search agent logs and determine frequency of occurrences of the given
    exception types.

    @param agent: (str) name of agent whose logs we want to search.
    @param logs_path: (str) path to logs directory
    @param exc_types: (list) list of exceptions we want to search for
    @param include_time_in_key: (bool) whether to include time of exception in
                                output. Default is to only show date.
    """
    s = searchtools.FileSearcher()
    if constants.USE_ALL_LOGS:
        data_source = os.path.join(constants.DATA_ROOT, logs_path,
                                   '{}.log*'.format(agent))
    else:
        data_source = os.path.join(constants.DATA_ROOT, logs_path,
                                   '{}.log'.format(agent))

    for exc_type in exc_types:
        s.add_search_term(r"^([0-9\-]+) (\S+) .+({}).*".format(exc_type),
                          [1, 2, 3], data_source)

    results = s.search()

    agent_exceptions = {}
    for path, _results in results:
        for result in _results:
            exc_tag = result.get(3)
            if exc_tag not in agent_exceptions:
                agent_exceptions[exc_tag] = {}

            if include_time_in_key:
                # use hours and minutes only
                time = re.compile("([0-9]+:[0-9]+).+").search(result.get(2))[1]
                key = "{}_{}".format(result.get(1), time)
            else:
                key = str(result.get(1))

            if key not in agent_exceptions[exc_tag]:
                agent_exceptions[exc_tag][key] = 0

            agent_exceptions[exc_tag][key] += 1

    if not agent_exceptions:
        return

    for exc_type in agent_exceptions:
        agent_exceptions_sorted = {}
        for k, v in sorted(agent_exceptions[exc_type].items(),
                           key=lambda x: x[0]):
            agent_exceptions_sorted[k] = v

        agent_exceptions[exc_type] = agent_exceptions_sorted

    return agent_exceptions
