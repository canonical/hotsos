# <a id="jobrequest"></a>`class JobRequest(BaseRequest)`

Base class for requests using the request / response pattern.

Subclasses **must** set the ``RESPONSE_CLASS`` attribute to a subclass of
the :class:`BaseResponse` which defines the fields that the response will
use.  They must also define additional attributes as :class:`Field`s.

For example::

    class TLSResponse(BaseResponse):
        key = Field('Private key for the cert')
        cert = Field('Public cert info')


    class TLSRequest(BaseRequest):
        RESPONSE_CLASS = TLSResponse

        common_name = Field('Common Name (CN) for the cert to be created')
        sans = Field('List of Subject Alternative Names (SANs)')

## <a id="jobrequest-egress_subnets"></a>`egress_subnets`

Subnets over which network traffic to the requester will flow.

## <a id="jobrequest-fromkeys"></a>`None`

Returns a new dict with keys from iterable and values equal to value.

## <a id="jobrequest-ingress_address"></a>`ingress_address`

Address to use if a connection to the requester is required.

## <a id="jobrequest-is_created"></a>`is_created`

Whether this request was created by this side of the relation.

## <a id="jobrequest-is_received"></a>`is_received`

Whether this request was received by the other side of the relation.

## <a id="jobrequest-respond"></a>`def respond(self, success, reason=None)`

Acknowledge this request, and indicate success or failure with an
optional explanation.

## <a id="jobrequest-to_json"></a>`def to_json(self)`

Render the job request to JSON string which can be included directly
into Prometheus config.

Keys will be sorted in the rendering to ensure a stable ordering for
comparisons to detect changes.

# <a id="jobresponse"></a>`class JobResponse(BaseResponse)`

Base class for responses using the request / response pattern.

## <a id="jobresponse-fromkeys"></a>`None`

Returns a new dict with keys from iterable and values equal to value.

