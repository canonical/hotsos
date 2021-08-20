from common import checks


class JujuBugChecks(checks.BugChecksBase):

    def __init__(self):
        super().__init__(yaml_defs_label="common")

    def __call__(self):
        self.register_search_terms()
        results = self.searchobj.search()
        self.process_results(results)
