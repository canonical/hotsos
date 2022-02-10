from charms.reactive import (
    toggle_flag,
    ResponderEndpoint,
)

from .common import ImportRequest


class GrafanaDashboardRequires(ResponderEndpoint):
    REQUEST_CLASS = ImportRequest

    def manage_flags(self):
        super().manage_flags()
        toggle_flag(self.expand_name('endpoint.{endpoint_name}.requests'),
                    self.is_joined and self.new_requests)
