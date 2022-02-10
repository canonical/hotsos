from charms.reactive import (
    toggle_flag,
    ResponderEndpoint,
)

from .common import JobRequest


class PrometheusManualRequires(ResponderEndpoint):
    REQUEST_CLASS = JobRequest

    def manage_flags(self):
        super().manage_flags()
        toggle_flag(self.expand_name('endpoint.{endpoint_name}.has_jobs'),
                    self.is_joined and self.jobs)
        toggle_flag(self.expand_name('endpoint.{endpoint_name}.new_jobs'),
                    self.is_joined and self.new_jobs)

    @property
    def jobs(self):
        """
        Return a list of all jobs to be registered.
        """
        return self.all_requests

    @property
    def new_jobs(self):
        """
        Return a list of new jobs to be registered.
        """
        return self.new_requests
