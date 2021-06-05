#!/usr/bin/python3
from common import checks
from common.searchtools import FileSearcher


class JujuBugChecks(checks.BugChecksBase):

    def __call__(self):
        self.register_search_terms()
        results = self.searchobj.search()
        self.process_results(results)


def get_bug_checker():
    return JujuBugChecks(FileSearcher(), "juju")


if __name__ == "__main__":
    get_bug_checker()()
