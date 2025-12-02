from dataclasses import dataclass

# NOTE: this is date only no time
APACHE_DATE_EXPR = r'(\d{2}/\w{3,5}/\d{4})'
PYWSGI_DATE = r'([\d-]+) [\d:]+\.\d{3}'

HTTP_REQ_EXPR = r'"(GET|POST|PUT|DELETE)'
APACHE_REQ_COMMON: str = f'.+{APACHE_DATE_EXPR}.+ {HTTP_REQ_EXPR}'

WSGI_HTTP_STATUS_EXPR = r'HTTP/\d\.\d" status: (\d+)'
HTTP_STATUS_EXPR = r'HTTP/\d\.\d" (\d+)'
APACHE_STATUS_COMMON: str = f'.+{APACHE_DATE_EXPR}.+ {HTTP_STATUS_EXPR}'


@dataclass(frozen=True)
class HTTPRequestExprs:  # pylint: disable=too-many-instance-attributes
    """
    Search expressions for HTTP request type in OpenStack api logs.
    """
    # apache
    apache_common: str = APACHE_REQ_COMMON
    # python wsgi neutron
    wsgi_neutron: str = f'{PYWSGI_DATE} .+ neutron.wsgi .+{HTTP_REQ_EXPR}'
    # sunbeam
    sunbeam_cinder: str = r'.+ \[wsgi-cinder-api\]' + APACHE_REQ_COMMON
    sunbeam_glance: str = (r'.+ \[glance-api\] ' + PYWSGI_DATE +
                           f' .+ eventlet.wsgi.server .+ {HTTP_REQ_EXPR}')
    sunbeam_keystone: str = r'.+ \[wsgi-keystone\]' + APACHE_REQ_COMMON
    sunbeam_neutron: str = (f'.+ {PYWSGI_DATE} .+ neutron.wsgi .+'
                            f'{HTTP_REQ_EXPR}')
    sunbeam_nova: str = r'.+ \[wsgi-nova-api\]' + APACHE_REQ_COMMON
    sunbeam_octavia: str = r'.+ \[wsgi-octavia-api\]' + APACHE_REQ_COMMON
    sunbeam_placement: str = r'.+ \[wsgi-placement-api\]' + APACHE_REQ_COMMON


@dataclass(frozen=True)
class HTTPStatusExprs:  # pylint: disable=too-many-instance-attributes
    """
    Search expressions for HTTP return status in OpenStack api logs.
    """
    # apache
    apache_common: str = APACHE_STATUS_COMMON
    # python wsgi neutron
    wsgi_neutron: str = (r'([\d-]+) [\d:]+\.\d{3} .+ neutron.wsgi .+'
                         f'{WSGI_HTTP_STATUS_EXPR}')
    # sunbeam
    sunbeam_cinder: str = r'.+ \[wsgi-cinder-api\]' + APACHE_STATUS_COMMON
    sunbeam_glance: str = (r'.+ \[glance-api\] ' + PYWSGI_DATE +
                           f' .+ eventlet.wsgi.server .+ {HTTP_STATUS_EXPR}')
    sunbeam_keystone: str = r'.+ \[wsgi-keystone\]' + APACHE_STATUS_COMMON
    sunbeam_nova: str = r'.+ \[wsgi-nova-api\]' + APACHE_STATUS_COMMON
    sunbeam_neutron: str = (f'.+ {PYWSGI_DATE} .+ neutron.wsgi .+'
                            f'{WSGI_HTTP_STATUS_EXPR}')
    sunbeam_octavia: str = r'.+ \[wsgi-octavia-api\]' + APACHE_STATUS_COMMON
    sunbeam_placement: str = (r'.+ \[wsgi-placement-api\]' +
                              APACHE_STATUS_COMMON)
