import re


def get_agent_exceptions(results, include_time_in_key=False):
    """Search results and determine frequency of occurrences of the given
    exception types.

    @param include_time_in_key: (bool) whether to include time of exception in
                                output. Default is to only show date.
    """
    agent_exceptions = {}
    for result in results:
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
