from charms.reactive import (
    toggle_flag,
    RequesterEndpoint,
)

from .common import JobRequest


class PrometheusManualProvides(RequesterEndpoint):
    REQUEST_CLASS = JobRequest

    def manage_flags(self):
        super().manage_flags()
        toggle_flag(self.expand_name('endpoint.{endpoint_name}.available'),
                    self.is_joined and self.requests)

    def register_job(self, job_name, job_data, ca_cert=None, relation=None):
        """
        Register a manual job.

        The job data should be the (unserialized) data defining the job.

        To ensure uniqueness, a UUID will be added to the job name, and it will
        be injected into the job data.

        If a CA cert is given, the value of any ca_file field in the job data
        will be replaced with a filename after the CA cert data is written, so
        a placeholder value should be used.

        If a specific relation is not given, the job will be registered with
        every related Prometheus.
        """
        # we might be connected to multiple prometheuses for some strange
        # reason, so just send the job to all of them
        relations = [relation] if relation is not None else self.relations
        for relation in relations:
            JobRequest.create_or_update(match_fields=['job_name'],
                                        relation=relation,
                                        job_name=job_name,
                                        job_data=job_data,
                                        ca_cert=ca_cert)
