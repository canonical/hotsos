from charms.reactive import BaseRequest, BaseResponse, Field


class ImportResponse(BaseResponse):
    success = Field(description='Whether or not the import succeeded')
    reason = Field(description='If failed, a description of why')

    @property
    def name(self):
        """
        The name given when the import was requested.
        """
        return self.request.name


class ImportRequest(BaseRequest):
    RESPONSE_CLASS = ImportResponse

    name = Field(description="""
                 Name of the dashboard to import. Informational only, so that
                 you can tell which dashboard request this was, e.g. to check
                 for success or failure.
                 """)

    dashboard = Field(description="""
                      Data structure defining the dashboard. Must be JSON
                      serializable.  (Note: This should *not* be pre-serialized
                      JSON.)
                      """)

    def respond(self, success, reason=None):
        """
        Acknowledge this request, and indicate success or failure with an
        optional explanation.
        """
        # wrap the base respond method to make the success field required and
        # positional, as well as to provide a better doc string
        super().respond(success=success, reason=reason)
