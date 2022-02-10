import json
from copy import deepcopy

from charms.reactive import BaseRequest, BaseResponse, Field


class JobResponse(BaseResponse):
    success = Field('Whether or not the registration succeeded')
    reason = Field('If failed, a description of why')


class JobRequest(BaseRequest):
    RESPONSE_CLASS = JobResponse

    job_name = Field('Desired name for the job.  To ensure uniqueness, the '
                     'the request ID will be appended to the final job name.')

    job_data = Field('Config data for the job.')

    ca_cert = Field('Cert data for the CA used to validate connections.')

    def to_json(self, ca_file=None):
        """
        Render the job request to JSON string which can be included directly
        into Prometheus config.

        Keys will be sorted in the rendering to ensure a stable ordering for
        comparisons to detect changes.

        If `ca_file` is given, it will be used to replace the value of any
        `ca_file` fields in the job.  The charm should ensure that the
        request's `ca_cert` data is writen to that path prior to calling this
        method.
        """
        job_data = deepcopy(self.job_data)  # make a copy we can modify
        job_data['job_name'] = '{}-{}'.format(self.job_name, self.request_id)

        if ca_file:
            for key, value in job_data.items():
                # update the cert path at the job level
                if key == 'tls_config':
                    value['ca_file'] = str(ca_file)

                # update the cert path at the SD config level
                if key.endswith('_sd_configs'):
                    for sd_config in value:
                        if 'ca_file' in sd_config.get('tls_config', {}):
                            sd_config['tls_config']['ca_file'] = str(ca_file)

        return json.dumps(job_data, sort_keys=True)

    def respond(self, success, reason=None):
        """
        Acknowledge this request, and indicate success or failure with an
        optional explanation.
        """
        super().respond(success=success, reason=reason)
