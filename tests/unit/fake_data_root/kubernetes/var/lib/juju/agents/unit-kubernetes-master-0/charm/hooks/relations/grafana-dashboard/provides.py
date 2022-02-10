from charms.reactive import (
    toggle_flag,
    RequesterEndpoint,
)

from .common import ImportRequest


class GrafanaDashboardProvides(RequesterEndpoint):
    REQUEST_CLASS = ImportRequest

    def manage_flags(self):
        super().manage_flags()
        toggle_flag(self.expand_name('endpoint.{endpoint_name}.failed'),
                    self.is_joined and self.failed_imports)

    @property
    def failed_imports(self):
        """
        A list of requests that failed to import.
        """
        return [response
                for response in self.responses
                if not response.success]

    def register_dashboard(self, name, dashboard):
        """
        Request a dashboard to be imported.

        :param name: Name of dashboard. Informational only, so that you can
            tell which dashboard request this was, e.g. to check for success or
            failure.
        :param dashboard: Data structure defining the dashboard. Must be JSON
            serializable.  (Note: This should *not* be pre-serialized JSON.)
        """
        # we might be connected to multiple grafanas for some strange
        # reason, so just send the dashboard to all of them
        for relation in self.relations:
            ImportRequest.create_or_update(match_fields=['name'],
                                           relation=relation,
                                           name=name,
                                           dashboard=dashboard)
