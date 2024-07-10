import os
from datetime import datetime, timezone

from cryptography.hazmat.backends import default_backend
from cryptography import x509
from hotsos.core.config import HotSOSConfig
from hotsos.core.factory import FactoryBase
from hotsos.core.host_helpers.cli import CLIHelper
from hotsos.core.log import log


class SSLCertificate():
    """ Representation of an SSL certificate. """
    def __init__(self, certificate_path):
        self.path = os.path.join(HotSOSConfig.data_root, certificate_path)
        try:
            with open(self.path, "rb") as fd:
                self.certificate = fd.read()
        except OSError as e:
            log.warning("Unable to read SSL certificate file %s: %s",
                        self.path, e)
            raise

    @property
    def expiry_date(self):
        """
        Return datetime() of when the certificate expires
        """

        cert = x509.load_pem_x509_certificate(self.certificate,
                                              default_backend())
        if hasattr(cert, 'not_valid_after_utc'):
            return cert.not_valid_after_utc
        return cert.not_valid_after.replace(tzinfo=timezone.utc)

    @property
    def days_to_expire(self):
        """
        Return int(days) remaining until the certificate expires
        """
        fmt = '%Y-%m-%d %H:%M:%S'
        today = datetime.strptime(
            CLIHelper().date(format='+' + fmt), fmt
                ).replace(tzinfo=timezone.utc)
        days = self.expiry_date - today
        return int(days.days)


class SSLCertificatesHelper():
    """ Set of methods to help analyse an SSL cert. """
    def __init__(self, certificate, expire_days):
        """
        @param certificate: SSLCertificate object.
        @param expire_days: int(expire_days) used to check the
                            days that remain until certificate expiration.
        """
        self.certificate = certificate
        self.expire_days = expire_days

    @property
    def certificate_expires_soon(self):
        """
        @return: True if certificate expires in less than int(self.expire_days)
        """
        return self.certificate.days_to_expire <= self.expire_days


class SSLCertificatesFactory(FactoryBase):
    """
    Factory to dynamically create SSLCertificate objects for given paths.

    SSLCertificate objects are returned when a getattr() is done on this object
    using cert path as the attr name.
    """

    def __getattr__(self, path):
        log.debug("creating SSLCertificate object for %s", path)
        return SSLCertificate(path)
