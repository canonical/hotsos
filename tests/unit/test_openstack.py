import os
from unittest import mock

from hotsos.core.config import HotSOSConfig
from hotsos.core import host_helpers
from hotsos.core.host_helpers.cli.common import CmdOutput
import hotsos.core.plugins.openstack as openstack_core
import hotsos.core.plugins.openstack.nova as nova_core
import hotsos.core.plugins.openstack.neutron as neutron_core
from hotsos.core.plugins.openstack import sunbeam
from hotsos.plugin_extensions.openstack import (
    vm_info,
    nova_external_events,
    summary,
    service_network_checks,
    service_features,
)
from hotsos.core.ycheck.common import GlobalSearcher
from hotsos.core.issues import IssuesManager


# pylint: disable=duplicate-code


from . import utils

OCTAVIA_UNIT_FILES = """
 apache-htcacheclean.service               disabled    enabled       
 apache-htcacheclean@.service              disabled    enabled       
 apache2.service                           enabled     enabled
 apache2@.service                          disabled    enabled
 jujud-unit-octavia-0.service              enabled     enabled
 jujud-unit-octavia-hacluster-5.service    enabled     enabled      
 octavia-api.service                       masked      enabled      
 octavia-health-manager.service            enabled     enabled      
 octavia-housekeeping.service              enabled     enabled      
 octavia-worker.service                    enabled     enabled
"""  # noqa

APT_SOURCE_PATH = 'etc/apt/sources.list.d/cloud-archive-{}.list'

APT_UCA = """
# Ubuntu Cloud Archive
deb http://ubuntu-cloud.archive.canonical.com/ubuntu bionic-updates/{} main
"""

JOURNALCTL_OVS_CLEANUP_GOOD = """
-- Logs begin at Thu 2021-04-29 17:44:42 BST, end at Thu 2021-05-06 09:05:01 BST. --
2022-04-29T17:52:37+0100 juju-9c28ce-ubuntu-11 systemd[1]: Starting OpenStack Neutron OVS cleanup...
2022-04-29T17:52:39+0100 juju-9c28ce-ubuntu-11 sudo[15179]:  neutron : TTY=unknown ; PWD=/var/lib/neutron ; USER=root ; COMMAND=/usr/bin/neutron-rootwrap /etc/neutron/r
2022-04-29T17:52:39+0100 juju-9c28ce-ubuntu-11 sudo[15179]: pam_unix(sudo:session): session opened for user root by (uid=0)
2022-04-29T17:52:39+0100 juju-9c28ce-ubuntu-11 ovs-vsctl[15183]: ovs|00001|vsctl|INFO|Called as /usr/bin/ovs-vsctl --timeout=5 --id=@manager -- create Manager "target=\
2022-04-29T17:52:39+0100 juju-9c28ce-ubuntu-11 sudo[15179]: pam_unix(sudo:session): session closed for user root
2022-04-29T17:52:39+0100 juju-9c28ce-ubuntu-11 systemd[1]: Started OpenStack Neutron OVS cleanup.
2022-05-03T06:17:29+0100 juju-9c28ce-ubuntu-11 systemd[1]: Stopped OpenStack Neutron OVS cleanup.
-- Reboot --
2022-05-04T11:05:56+0100 juju-9c28ce-ubuntu-11 systemd[1]: Starting OpenStack Neutron OVS cleanup...
2022-05-04T11:06:20+0100 juju-9c28ce-ubuntu-11 systemd[1]: Started OpenStack Neutron OVS cleanup.
"""  # noqa

JOURNALCTL_OVS_CLEANUP_GOOD2 = """
-- Logs begin at Thu 2021-04-29 17:44:42 BST, end at Thu 2021-05-06 09:05:01 BST. --
2022-04-29T17:52:37+0100 juju-9c28ce-ubuntu-11 systemd[1]: Starting OpenStack Neutron OVS cleanup...
2022-04-29T17:52:39+0100 juju-9c28ce-ubuntu-11 sudo[15179]:  neutron : TTY=unknown ; PWD=/var/lib/neutron ; USER=root ; COMMAND=/usr/bin/neutron-rootwrap /etc/neutron/r
2022-04-29T17:52:39+0100 juju-9c28ce-ubuntu-11 sudo[15179]: pam_unix(sudo:session): session opened for user root by (uid=0)
2022-04-29T17:52:39+0100 juju-9c28ce-ubuntu-11 ovs-vsctl[15183]: ovs|00001|vsctl|INFO|Called as /usr/bin/ovs-vsctl --timeout=5 --id=@manager -- create Manager "target=\
2022-04-29T17:52:39+0100 juju-9c28ce-ubuntu-11 sudo[15179]: pam_unix(sudo:session): session closed for user root
2022-04-29T17:52:39+0100 juju-9c28ce-ubuntu-11 systemd[1]: Started OpenStack Neutron OVS cleanup.
2022-05-03T06:17:29+0100 juju-9c28ce-ubuntu-11 systemd[1]: Stopped OpenStack Neutron OVS cleanup.
2022-05-04T10:05:56+0100 juju-9c28ce-ubuntu-11 systemd[1]: Starting OpenStack Neutron OVS cleanup...
2022-05-04T10:06:20+0100 juju-9c28ce-ubuntu-11 systemd[1]: Started OpenStack Neutron OVS cleanup.
-- Reboot --
2022-05-04T11:05:56+0100 juju-9c28ce-ubuntu-11 systemd[1]: Starting OpenStack Neutron OVS cleanup...
2022-05-04T11:06:20+0100 juju-9c28ce-ubuntu-11 systemd[1]: Started OpenStack Neutron OVS cleanup.
"""  # noqa

JOURNALCTL_OVS_CLEANUP_BAD = """
-- Logs begin at Thu 2021-04-29 17:44:42 BST, end at Thu 2021-05-06 09:05:01 BST. --
2022-04-29T17:52:37+0100 juju-9c28ce-ubuntu-11 systemd[1]: Starting OpenStack Neutron OVS cleanup...
2022-04-29T17:52:39+0100 juju-9c28ce-ubuntu-11 sudo[15179]:  neutron : TTY=unknown ; PWD=/var/lib/neutron ; USER=root ; COMMAND=/usr/bin/neutron-rootwrap /etc/neutron/r
2022-04-29T17:52:39+0100 juju-9c28ce-ubuntu-11 sudo[15179]: pam_unix(sudo:session): session opened for user root by (uid=0)
2022-04-29T17:52:39+0100 juju-9c28ce-ubuntu-11 ovs-vsctl[15183]: ovs|00001|vsctl|INFO|Called as /usr/bin/ovs-vsctl --timeout=5 --id=@manager -- create Manager "target=\
2022-04-29T17:52:39+0100 juju-9c28ce-ubuntu-11 sudo[15179]: pam_unix(sudo:session): session closed for user root
2022-04-29T17:52:39+0100 juju-9c28ce-ubuntu-11 systemd[1]: Started OpenStack Neutron OVS cleanup.
2022-05-03T06:17:29+0100 juju-9c28ce-ubuntu-11 systemd[1]: Stopped OpenStack Neutron OVS cleanup.
2022-05-04T10:05:56+0100 juju-9c28ce-ubuntu-11 systemd[1]: Starting OpenStack Neutron OVS cleanup...
2022-05-04T10:06:20+0100 juju-9c28ce-ubuntu-11 systemd[1]: Started OpenStack Neutron OVS cleanup.
"""  # noqa

DPKG_L_CLIENTS_ONLY = """
ii  python3-neutronclient                       2:17.2.0-0ubuntu2                                    all          Neutron is a virtual network service for Openstack - common
"""  # noqa

APACHE2_SSL_CONF = """
Listen 4990
Listen 35347
<VirtualHost 10.5.2.135:4990>
    ServerName 10.5.100.2
    SSLEngine on
    SSLCertificateFile /etc/apache2/ssl/keystone/cert_10.5.100.2
    SSLCertificateChainFile /etc/apache2/ssl/keystone/cert_10.5.100.2
    SSLCertificateKeyFile /etc/apache2/ssl/keystone/key_10.5.100.2
</VirtualHost>
<VirtualHost 10.5.2.135:35347>
    ServerName 10.5.100.2
    SSLEngine on
    SSLCertificateFile /etc/apache2/ssl/keystone/cert_10.5.100.2
    SSLCertificateChainFile /etc/apache2/ssl/keystone/cert_10.5.100.2
    SSLCertificateKeyFile /etc/apache2/ssl/keystone/key_10.5.100.2
</VirtualHost>
"""

APACHE2_SSL_CONF_RGW = """
Listen 433
<VirtualHost 10.5.2.135:433>
    ServerName 10.5.100.2
    SSLEngine on
    SSLCertificateFile /etc/apache2/ssl/keystone/cert_10.5.100.2
    SSLCertificateChainFile /etc/apache2/ssl/keystone/cert_10.5.100.2
    SSLCertificateKeyFile /etc/apache2/ssl/keystone/key_10.5.100.2
    AllowEncodedSlashes On
</VirtualHost>
"""

CERTIFICATE_FILE = """
Certificate:
    Data:
        Version: 3 (0x2)
        Serial Number: 1 (0x1)
        Signature Algorithm: sha256WithRSAEncryption
        Issuer: C=GB, ST=England, L=London, O=Ubuntu Cloud, OU=Cloud
        Validity
            Not Before: Mar 18 19:42:50 2022 GMT
            Not After : Mar 18 19:42:50 2023 GMT
        Subject: C=GB, ST=England, L=London, O=Ubuntu Cloud, OU=Cloud, CN=10.5.100.0
        Subject Public Key Info:
            Public Key Algorithm: rsaEncryption
                RSA Public-Key: (2048 bit)
                Modulus:
                    00:da:82:86:7a:6a:32:f7:96:f9:7b:70:a3:88:56:
                    ee:8f:5e:d8:3b:b2:3e:30:1d:c4:bd:43:a4:ee:f6:
                    48:cf:22:60:ca:8c:62:21:6a:31:86:bd:d1:3b:30:
                    19:96:3b:bd:12:4e:4f:3a:72:25:bf:45:05:92:45:
                    8c:0b:9f:73:f1:bd:11:c4:7d:d0:3c:fe:4c:fd:46:
                    aa:53:e4:87:c9:0d:33:d2:a5:6d:86:ea:1c:0d:51:
                    90:28:32:00:de:91:28:73:0e:45:be:7e:19:d4:c1:
                    15:86:6d:c4:18:f0:83:b2:84:22:51:2c:48:8c:0b:
                    5b:61:08:59:3d:78:c6:1f:aa:c9:d6:26:cd:2a:2f:
                    93:ca:4b:ae:b8:5a:9b:39:5c:c6:d8:66:fe:ea:21:
                    cb:a2:c4:75:e3:77:ee:84:9a:2a:0a:49:db:bd:f0:
                    87:5d:68:65:90:b9:d5:00:ab:e6:24:2e:e4:5f:9c:
                    33:4a:90:1d:27:33:54:0c:7f:9d:6b:20:9f:06:0b:
                    b7:38:74:eb:e0:9c:e3:ba:b0:83:f8:ea:57:d5:f5:
                    cc:ec:52:48:5e:81:8d:ab:80:56:e5:88:c7:1a:4f:
                    0f:d8:cb:97:c6:ba:cf:d9:e3:c3:f7:aa:b3:6c:81:
                    06:da:72:e9:84:9a:2e:db:45:d1:3d:3f:35:7d:4a:
                    ef:cf
                Exponent: 65537 (0x10001)
        X509v3 extensions:
            X509v3 Subject Key Identifier:
                12:03:19:E3:A8:06:66:9D:8C:DA:1A:4B:D5:F7:B5:57:00:E2:02:F8
            X509v3 Authority Key Identifier:
                keyid:43:98:EC:D7:CF:58:53:23:24:48:08:61:87:3E:3B:DA:36:CC:0D:27

            X509v3 Basic Constraints:
                CA:FALSE
            X509v3 Key Usage:
                Digital Signature, Key Encipherment
            X509v3 Subject Alternative Name:
                IP Address:10.5.100.0, IP Address:10.5.100.1, IP Address:10.5.100.2, IP Address:10.5.100.3, IP Address:10.5.100.4, IP Address:10.5.100.5, IP Address:10.5.100.6, IP Address:10.5.100.7, IP Address:10.5.100.8, IP Address:10.5.100.9, IP Address:10.5.100.10, IP Address:10.5.100.11, IP Address:10.5.100.12, IP Address:10.5.100.13, IP Address:10.5.100.14, IP Address:10.5.100.15, IP Address:10.5.100.16, IP Address:10.5.100.17, IP Address:10.5.100.18, IP Address:10.5.100.19
            Netscape Comment:
                OpenSSL Generated Certificate
    Signature Algorithm: sha256WithRSAEncryption
         16:e4:8f:02:93:7c:17:d9:79:b1:28:86:65:ca:a9:1a:f7:b5:
         23:72:fb:1b:7e:2c:da:ac:37:9d:db:7f:93:e1:60:c2:e9:ae:
         b9:b7:60:29:74:11:50:47:bb:24:66:58:f2:2e:c3:b1:18:68:
         f3:4c:75:92:17:d0:5a:0f:ba:f4:ba:26:a6:d6:22:18:79:e1:
         1e:04:83:10:4c:ed:fb:be:c3:45:65:37:a0:4c:1e:e6:68:f3:
         5c:1d:46:75:84:20:e8:cc:6c:a2:06:66:92:10:0f:83:7f:7e:
         bc:de:3d:6e:a3:39:16:c1:c4:fc:80:5d:64:ea:4f:e9:b0:1a:
         b1:5a:a9:30:11:fb:6b:6a:8a:2d:b9:61:4f:32:a2:d1:61:e3:
         ec:4e:a2:af:09:54:6a:d2:e7:12:50:c4:28:08:2c:07:ce:8a:
         4f:1c:6b:cd:52:76:ca:cd:cd:b7:e7:6c:06:6e:a7:97:27:db:
         e8:a2:af:42:35:01:e3:2c:90:31:bd:55:9c:fd:74:9b:45:f8:
         5c:73:02:c1:8f:ac:a1:3a:b1:17:15:df:dc:6c:38:43:52:bc:
         a7:af:0f:19:4f:26:6f:87:f4:f9:01:04:8d:94:2a:a6:26:98:
         7a:67:3d:ae:a6:d5:a2:4a:19:9d:02:7d:05:c2:c1:0b:a9:79:
         4c:f8:6f:3e:ac:bb:c0:0f:6a:33:37:74:19:62:b6:ae:f4:4a:
         3a:1d:7c:35:08:dc:cf:9c:fa:b4:b2:3e:c8:e3:eb:90:12:5a:
         d3:51:ca:47:27:93:fb:f3:f4:24:a3:33:11:09:58:4e:5d:ec:
         ae:b4:19:3a:23:68:67:5a:36:d0:f0:52:5a:73:8f:03:6e:eb:
         a7:9c:64:b7:ba:0a:72:76:fc:69:5c:dd:d6:09:ad:87:94:eb:
         af:11:27:73:e2:ac:bc:eb:2d:62:d0:3b:b3:d7:0d:fe:94:e6:
         1e:53:ec:ea:02:8b:f2:03:dc:0f:7b:47:82:73:09:76:61:17:
         53:9e:e5:e3:85:94:05:e2:c3:f9:f3:66:c7:b8:4d:73:68:75:
         af:d1:95:50:e3:54:e8:30:51:56:0c:87:30:6e:c5:d3:ba:be:
         5a:02:6b:28:dc:4d:da:43:8d:4c:b7:85:a3:8d:51:2c:c1:69:
         d8:84:73:43:14:2b:49:e4:63:76:a4:de:96:f6:26:20:45:8f:
         bf:ac:c7:fc:07:80:b1:1a:3d:7d:56:7e:00:42:68:a1:61:6b:
         3f:74:0a:51:0c:00:97:c0:42:7a:63:0c:35:ac:2e:5a:15:0f:
         00:91:d7:29:77:10:ef:bf:99:34:ec:db:72:c5:5d:7a:8e:4d:
         5c:68:9d:c0:ea:6b:42:18
-----BEGIN CERTIFICATE-----
MIIFTjCCAzagAwIBAgIBATANBgkqhkiG9w0BAQsFADBXMQswCQYDVQQGEwJHQjEQ
MA4GA1UECAwHRW5nbGFuZDEPMA0GA1UEBwwGTG9uZG9uMRUwEwYDVQQKDAxVYnVu
dHUgQ2xvdWQxDjAMBgNVBAsMBUNsb3VkMB4XDTIyMDMxODE5NDI1MFoXDTIzMDMx
ODE5NDI1MFowbDELMAkGA1UEBhMCR0IxEDAOBgNVBAgMB0VuZ2xhbmQxDzANBgNV
BAcMBkxvbmRvbjEVMBMGA1UECgwMVWJ1bnR1IENsb3VkMQ4wDAYDVQQLDAVDbG91
ZDETMBEGA1UEAwwKMTAuNS4xMDAuMDCCASIwDQYJKoZIhvcNAQEBBQADggEPADCC
AQoCggEBANqChnpqMveW+Xtwo4hW7o9e2DuyPjAdxL1DpO72SM8iYMqMYiFqMYa9
0TswGZY7vRJOTzpyJb9FBZJFjAufc/G9EcR90Dz+TP1GqlPkh8kNM9KlbYbqHA1R
kCgyAN6RKHMORb5+GdTBFYZtxBjwg7KEIlEsSIwLW2EIWT14xh+qydYmzSovk8pL
rrhamzlcxthm/uohy6LEdeN37oSaKgpJ273wh11oZZC51QCr5iQu5F+cM0qQHScz
VAx/nWsgnwYLtzh06+Cc47qwg/jqV9X1zOxSSF6BjauAVuWIxxpPD9jLl8a6z9nj
w/eqs2yBBtpy6YSaLttF0T0/NX1K788CAwEAAaOCAQ4wggEKMB0GA1UdDgQWBBQS
AxnjqAZmnYzaGkvV97VXAOIC+DAfBgNVHSMEGDAWgBRDmOzXz1hTIyRICGGHPjva
NswNJzAJBgNVHRMEAjAAMAsGA1UdDwQEAwIFoDCBgQYDVR0RBHoweIcECgVkAIcE
CgVkAYcECgVkAocECgVkA4cECgVkBIcECgVkBYcECgVkBocECgVkB4cECgVkCIcE
CgVkCYcECgVkCocECgVkC4cECgVkDIcECgVkDYcECgVkDocECgVkD4cECgVkEIcE
CgVkEYcECgVkEocECgVkEzAsBglghkgBhvhCAQ0EHxYdT3BlblNTTCBHZW5lcmF0
ZWQgQ2VydGlmaWNhdGUwDQYJKoZIhvcNAQELBQADggIBABbkjwKTfBfZebEohmXK
qRr3tSNy+xt+LNqsN53bf5PhYMLprrm3YCl0EVBHuyRmWPIuw7EYaPNMdZIX0FoP
uvS6JqbWIhh54R4EgxBM7fu+w0VlN6BMHuZo81wdRnWEIOjMbKIGZpIQD4N/frze
PW6jORbBxPyAXWTqT+mwGrFaqTAR+2tqii25YU8yotFh4+xOoq8JVGrS5xJQxCgI
LAfOik8ca81SdsrNzbfnbAZup5cn2+iir0I1AeMskDG9VZz9dJtF+FxzAsGPrKE6
sRcV39xsOENSvKevDxlPJm+H9PkBBI2UKqYmmHpnPa6m1aJKGZ0CfQXCwQupeUz4
bz6su8APajM3dBlitq70SjodfDUI3M+c+rSyPsjj65ASWtNRykcnk/vz9CSjMxEJ
WE5d7K60GTojaGdaNtDwUlpzjwNu66ecZLe6CnJ2/Glc3dYJrYeU668RJ3PirLzr
LWLQO7PXDf6U5h5T7OoCi/ID3A97R4JzCXZhF1Oe5eOFlAXiw/nzZse4TXNoda/R
lVDjVOgwUVYMhzBuxdO6vloCayjcTdpDjUy3haONUSzBadiEc0MUK0nkY3ak3pb2
JiBFj7+sx/wHgLEaPX1WfgBCaKFhaz90ClEMAJfAQnpjDDWsLloVDwCR1yl3EO+/
mTTs23LFXXqOTVxoncDqa0IY
-----END CERTIFICATE-----"""  # noqa

ARM_QEMU_PS_OUT = """libvirt+   23849  6.8  0.0 6083100 1237380 ?     -    Apr29 670:43 /usr/bin/qemu-system-aarch64 -name guest=instance-00037cd9,debug-threads=on -S -object {"qom-type":"secret","id":"masterKey0","format":"raw","file":"/var/lib/libvirt/qemu/domain-1-instance-00037cd9/master-key.aes"} -blockdev {"driver":"file","filename":"/usr/share/AAVMF/AAVMF_CODE.fd","node-name":"libvirt-pflash0-storage","auto-read-only":true,"discard":"unmap"} -blockdev {"node-name":"libvirt-pflash0-format","read-only":true,"driver":"raw","file":"libvirt-pflash0-storage"} -blockdev {"driver":"file","filename":"/var/lib/libvirt/qemu/nvram/instance-00037cd9_VARS.fd","node-name":"libvirt-pflash1-storage","auto-read-only":true,"discard":"unmap"} -blockdev {"node-name":"libvirt-pflash1-format","read-only":false,"driver":"raw","file":"libvirt-pflash1-storage"} -machine virt-6.2,usb=off,dump-guest-core=off,gic-version=3,pflash0=libvirt-pflash0-format,pflash1=libvirt-pflash1-format,memory-backend=mach-virt.ram -accel kvm -cpu host -m 1024 -object {"qom-type":"memory-backend-ram","id":"mach-virt.ram","size":1073741824} -overcommit mem-lock=off -smp 1,sockets=1,dies=1,cores=1,threads=1 -uuid 66a20f33-f273-49bc-b738-936eebfbd8c5 -no-user-config -nodefaults -chardev socket,id=charmonitor,fd=33,server=on,wait=off -mon chardev=charmonitor,id=monitor,mode=control -rtc base=utc,driftfix=slew -no-shutdown -boot strict=on -device pcie-root-port,port=8,chassis=1,id=pci.1,bus=pcie.0,multifunction=on,addr=0x1 -device pcie-root-port,port=9,chassis=2,id=pci.2,bus=pcie.0,addr=0x1.0x1 -device pcie-root-port,port=10,chassis=3,id=pci.3,bus=pcie.0,addr=0x1.0x2 -device pcie-root-port,port=11,chassis=4,id=pci.4,bus=pcie.0,addr=0x1.0x3 -device pcie-root-port,port=12,chassis=5,id=pci.5,bus=pcie.0,addr=0x1.0x4 -device pcie-root-port,port=13,chassis=6,id=pci.6,bus=pcie.0,addr=0x1.0x5 -device pcie-root-port,port=14,chassis=7,id=pci.7,bus=pcie.0,addr=0x1.0x6 -device pcie-root-port,port=15,chassis=8,id=pci.8,bus=pcie.0,addr=0x1.0x7 -device qemu-xhci,id=usb,bus=pci.2,addr=0x0 -device virtio-serial-pci,id=virtio-serial0,bus=pci.3,addr=0x0 -blockdev {"driver":"file","filename":"/var/lib/nova/instances/_base/5b9f93fbfce101950757660101d52f139dcbdeb1","node-name":"libvirt-2-storage","cache":{"direct":true,"no-flush":false},"auto-read-only":true,"discard":"unmap"} -blockdev {"node-name":"libvirt-2-format","read-only":true,"discard":"unmap","cache":{"direct":true,"no-flush":false},"driver":"raw","file":"libvirt-2-storage"} -blockdev {"driver":"file","filename":"/var/lib/nova/instances/66a20f33-f273-49bc-b738-936eebfbd8c5/disk","node-name":"libvirt-1-storage","cache":{"direct":true,"no-flush":false},"auto-read-only":true,"discard":"unmap"} -blockdev {"node-name":"libvirt-1-format","read-only":false,"discard":"unmap","cache":{"direct":true,"no-flush":false},"driver":"qcow2","file":"libvirt-1-storage","backing":"libvirt-2-format"} -device virtio-blk-pci,bus=pci.4,addr=0x0,drive=libvirt-1-format,id=virtio-disk0,bootindex=1,write-cache=on -netdev tap,fd=35,id=hostnet0,vhost=on,vhostfd=37 -device virtio-net-pci,host_mtu=1500,netdev=hostnet0,id=net0,mac=fa:16:5d:40:33:0d,bus=pci.1,addr=0x0 -add-fd set=3,fd=34 -chardev pty,id=charserial0,logfile=/dev/fdset/3,logappend=on -serial chardev:charserial0 -chardev spicevmc,id=charchannel0,name=vdagent -device virtserialport,bus=virtio-serial0.0,nr=1,chardev=charchannel0,id=channel0,name=com.redhat.spice.0 -device usb-kbd,id=input0,bus=usb.0,port=1 -audiodev {"id":"audio1","driver":"spice"} -spice port=5900,addr=10.140.52.133,disable-ticketing=on,seamless-migration=on -device virtio-vga,id=video0,max_outputs=1,bus=pci.7,addr=0x0 -device virtio-balloon-pci,id=balloon0,bus=pci.5,addr=0x0 -object {"qom-type":"rng-random","id":"objrng0","filename":"/dev/urandom"} -device virtio-rng-pci,rng=objrng0,id=rng0,bus=pci.6,addr=0x0 -device vmcoreinfo -sandbox on,obsolete=deny,elevateprivileges=deny,spawn=deny,resourcecontrol=deny -msg timestamp=on"""  # noqa,pylint: disable=line-too-long


class TestOpenstackBase(utils.BaseTestCase):
    """ Custom base testcase that sets openstack plugin context. """
    ip_link_show = None

    def fake_ip_link_w_errors_drops(self):
        lines = ''.join(self.ip_link_show).format(10000000, 100000000)
        return [line + '\n' for line in lines.split('\n')]

    def fake_ip_link_no_errors_drops(self):
        lines = ''.join(self.ip_link_show).format(0, 0)
        return [line + '\n' for line in lines.split('\n')]

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        HotSOSConfig.plugin_name = 'openstack'

        if self.ip_link_show is None:
            path = os.path.join(HotSOSConfig.data_root,
                                "sos_commands/networking/ip_-s_-d_link")
            with open(path, encoding='utf-8') as fd:
                self.ip_link_show = fd.readlines()


class TestOpenstackSunbeam(TestOpenstackBase):
    """ Unit tests for OpenStack Sunbeam . """

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        HotSOSConfig.data_root = 'tests/unit/fake_data_root/sunbeam'

    def test_not_controller(self):
        HotSOSConfig.data_root = 'tests/unit/fake_data_root/openstack'
        sunbeaminfo = sunbeam.SunbeamInfo()
        self.assertFalse(sunbeaminfo.is_controller)
        self.assertDictEqual(sunbeaminfo.pods, {})
        self.assertDictEqual(sunbeaminfo.statefulsets, {})

    def test_pods(self):
        sunbeaminfo = sunbeam.SunbeamInfo()
        expected = {'Running': ['certificate-authority-0',
                                'cinder-0',
                                'cinder-mysql-router-0',
                                'glance-0',
                                'glance-mysql-router-0',
                                'horizon-0',
                                'horizon-mysql-router-0',
                                'keystone-0',
                                'keystone-mysql-router-0',
                                'modeloperator-6f8f4577b4-9zhvc',
                                'mysql-0',
                                'neutron-0',
                                'neutron-mysql-router-0',
                                'nova-0',
                                'nova-api-mysql-router-0',
                                'nova-cell-mysql-router-0',
                                'nova-mysql-router-0',
                                'ovn-central-0',
                                'ovn-relay-0',
                                'placement-0',
                                'placement-mysql-router-0',
                                'rabbitmq-0',
                                'traefik-0',
                                'traefik-public-0']}
        self.assertDictEqual(sunbeaminfo.pods, expected)

    def test_statefulsets(self):
        sunbeaminfo = sunbeam.SunbeamInfo()
        expected = {'complete': ['certificate-authority',
                                 'cinder',
                                 'cinder-mysql-router',
                                 'glance',
                                 'glance-mysql-router',
                                 'horizon',
                                 'horizon-mysql-router',
                                 'keystone',
                                 'keystone-mysql-router',
                                 'mysql',
                                 'neutron',
                                 'neutron-mysql-router',
                                 'nova',
                                 'nova-api-mysql-router',
                                 'nova-cell-mysql-router',
                                 'nova-mysql-router',
                                 'ovn-central',
                                 'ovn-relay',
                                 'placement',
                                 'placement-mysql-router',
                                 'rabbitmq',
                                 'traefik',
                                 'traefik-public'],
                    'incomplete': []}
        self.assertDictEqual(sunbeaminfo.statefulsets, expected)

    @utils.create_data_root(
        {'sos_commands/kubernetes/cluster-info/openstack/'
         'k8s_kubectl_get_-o_json_--namespace_openstack_statefulsets':
         '{"apiVersion": "v1","items": [{"metadata": '
         '{"name": "traefik-public"},"status": '
         '{"readyReplicas": 1,"replicas": 1}}]}'})
    def test_statefulsets_w_complete(self):
        sunbeaminfo = sunbeam.SunbeamInfo()
        with mock.patch.object(sunbeaminfo, 'is_controller',
                               return_value=True):
            expected = {'complete': ['traefik-public'],
                        'incomplete': []}
            self.assertDictEqual(sunbeaminfo.statefulsets, expected)

    @utils.create_data_root(
        {'sos_commands/kubernetes/cluster-info/openstack/'
         'k8s_kubectl_get_-o_json_--namespace_openstack_statefulsets':
         '{"apiVersion": "v1","items": [{"metadata": '
         '{"name": "traefik-public"},"status": '
         '{"readyReplicas": 0,"replicas": 1}}]}'})
    def test_statefulsets_w_incomplete(self):
        sunbeaminfo = sunbeam.SunbeamInfo()
        with mock.patch.object(sunbeaminfo, 'is_controller',
                               return_value=True):
            expected = {'complete': [],
                        'incomplete': ['traefik-public']}
            self.assertDictEqual(sunbeaminfo.statefulsets, expected)

    @utils.create_data_root(
        {'sos_commands/kubernetes/cluster-info/openstack/'
         'k8s_kubectl_get_-o_json_--namespace_openstack_statefulsets':
         '{"apiVersion": "v1","items": [{"metadata": '
         '{"name": "traefik-public"},"status": '
         '{"replicas": 1}}]}'})
    def test_statefulsets_w_missing_readreplicas_key(self):
        sunbeaminfo = sunbeam.SunbeamInfo()
        with mock.patch.object(sunbeaminfo, 'is_controller',
                               return_value=True):
            expected = {'complete': [],
                        'incomplete': ['traefik-public']}
            self.assertDictEqual(sunbeaminfo.statefulsets, expected)


class TestOpenstackPluginCore(TestOpenstackBase):
    """ Unit tests for OpenStack plugin core. """
    def test_release_name(self):
        base = openstack_core.OpenstackBase()
        self.assertEqual(base.release_name, 'ussuri')

    @utils.create_data_root({'etc/openstack-release':
                             'OPENSTACK_CODENAME=yoga'})
    def test_release_name_from_file(self):
        base = openstack_core.OpenstackBase()
        with mock.patch.object(base, 'installed_pkg_release_names', None):
            self.assertEqual(base.release_name, 'yoga')

    @mock.patch('hotsos.core.host_helpers.cli.catalog.DateFileCmd.format_date')
    def test_get_release_eol(self, mock_date):
        # 2030-04-30
        mock_date.return_value = CmdOutput('1903748400')

        inst = openstack_core.OpenstackBase()
        self.assertEqual(inst.release_name, 'ussuri')

        self.assertLessEqual(inst.days_to_eol, 0)

    @mock.patch('hotsos.core.host_helpers.cli.catalog.DateFileCmd.format_date')
    def test_get_release_not_eol(self, mock_date):
        # 2030-01-01
        mock_date.return_value = CmdOutput('1893466800')

        inst = openstack_core.OpenstackBase()
        self.assertEqual(inst.release_name, 'ussuri')

        self.assertGreater(inst.days_to_eol, 0)

    def test_project_catalog_apt_exprs(self):
        c = openstack_core.openstack.OSTProjectCatalog()
        core = ['ceilometer',
                'octavia',
                'placement',
                'manila',
                'designate',
                'neutron',
                'glance',
                'masakari',
                'ironic',
                'amphora-\\S+',
                'gnocchi',
                'openstack-dashboard',
                'horizon',
                'keystone',
                'swift',
                'aodh',
                'heat',
                'nova',
                'barbican',
                'cinder']

        deps = ['keepalived',
                'python3?-amphora-\\S+\\S*',
                'python3?-openstack-dashboard\\S*',
                'libvirt-bin',
                'python3?-aodh\\S*',
                'python3?-nova\\S*',
                'python3?-swift\\S*',
                'python3?-ceilometer\\S*',
                'radvd',
                'python3?-horizon\\S*',
                'haproxy',
                'python3?-masakari\\S*',
                'python3?-barbican\\S*',
                'python3?-cinder\\S*',
                'python3?-oslo[.-]',
                'python3?-manila\\S*',
                'python3?-ironic\\S*',
                'python3?-heat\\S*',
                'python3?-keystone\\S*',
                'python3?-neutron\\S*',
                'python3?-gnocchi\\S*',
                'qemu-kvm',
                'conntrack',
                'libvirt-daemon',
                'nfs-ganesha\\S*',
                'python3?-placement\\S*',
                'python3?-octavia\\S*',
                'python3?-glance\\S*',
                'dnsmasq',
                'python3?-designate\\S*']

        self.assertEqual(sorted(c.apt_core_exprs), sorted(core))
        self.assertEqual(sorted(c.apt_dep_exprs), sorted(deps))

    def test_project_catalog_snap_exprs(self):
        c = openstack_core.openstack.OSTProjectCatalog()
        core = [r'openstack\S*']
        self.assertEqual(sorted(c.snap_core_exprs), sorted(core))

    def test_project_catalog_snap_packages(self):
        HotSOSConfig.data_root = 'tests/unit/fake_data_root/sunbeam'
        ost_base = openstack_core.OpenstackBase()
        core = {'openstack':
                {'version': '2024.1', 'channel': '2024.1/stable'},
                'openstack-hypervisor':
                {'version': '2024.1', 'channel': '2024.1/stable'}}
        self.assertEqual(ost_base.snaps.core, core)

    def test_project_catalog_packages(self):
        ost_base = openstack_core.OpenstackBase()
        core = {'keystone-common': '2:17.0.1-0ubuntu1',
                'neutron-common': '2:16.4.1-0ubuntu2',
                'neutron-dhcp-agent': '2:16.4.1-0ubuntu2',
                'neutron-fwaas-common': '1:16.0.0-0ubuntu0.20.04.1',
                'neutron-l3-agent': '2:16.4.1-0ubuntu2',
                'neutron-metadata-agent': '2:16.4.1-0ubuntu2',
                'neutron-openvswitch-agent': '2:16.4.1-0ubuntu2',
                'nova-api-metadata': '2:21.2.3-0ubuntu1',
                'nova-common': '2:21.2.3-0ubuntu1',
                'nova-compute': '2:21.2.3-0ubuntu1',
                'nova-compute-kvm': '2:21.2.3-0ubuntu1',
                'nova-compute-libvirt': '2:21.2.3-0ubuntu1'}

        deps = {'conntrack': '1:1.4.5-2',
                'dnsmasq-base': '2.80-1.1ubuntu1.4',
                'dnsmasq-utils': '2.80-1.1ubuntu1.4',
                'haproxy': '2.0.13-2ubuntu0.3',
                'keepalived': '1:2.0.19-2ubuntu0.1',
                'libvirt-daemon': '6.0.0-0ubuntu8.15',
                'libvirt-daemon-driver-qemu': '6.0.0-0ubuntu8.15',
                'libvirt-daemon-driver-storage-rbd': '6.0.0-0ubuntu8.15',
                'libvirt-daemon-system': '6.0.0-0ubuntu8.15',
                'libvirt-daemon-system-systemd': '6.0.0-0ubuntu8.15',
                'python3-barbicanclient': '4.10.0-0ubuntu1',
                'python3-cinderclient': '1:7.0.0-0ubuntu1',
                'python3-designateclient': '2.11.0-0ubuntu2',
                'python3-glanceclient': '1:3.1.1-0ubuntu1',
                'python3-keystone': '2:17.0.1-0ubuntu1',
                'python3-keystoneauth1': '4.0.0-0ubuntu1',
                'python3-keystoneclient': '1:4.0.0-0ubuntu1',
                'python3-keystonemiddleware': '9.0.0-0ubuntu1',
                'python3-neutron': '2:16.4.1-0ubuntu2',
                'python3-neutron-fwaas': '1:16.0.0-0ubuntu0.20.04.1',
                'python3-neutron-lib': '2.3.0-0ubuntu1',
                'python3-neutronclient': '1:7.1.1-0ubuntu1',
                'python3-nova': '2:21.2.3-0ubuntu1',
                'python3-novaclient': '2:17.0.0-0ubuntu1',
                'python3-oslo.cache': '2.3.0-0ubuntu1',
                'python3-oslo.concurrency': '4.0.2-0ubuntu1',
                'python3-oslo.config': '1:8.0.2-0ubuntu1',
                'python3-oslo.context': '1:3.0.2-0ubuntu1',
                'python3-oslo.db': '8.1.0-0ubuntu1',
                'python3-oslo.i18n': '4.0.1-0ubuntu1',
                'python3-oslo.log': '4.1.1-0ubuntu1',
                'python3-oslo.messaging': '12.1.6-0ubuntu1',
                'python3-oslo.middleware': '4.0.2-0ubuntu1',
                'python3-oslo.policy': '3.1.0-0ubuntu1.1',
                'python3-oslo.privsep': '2.1.1-0ubuntu1',
                'python3-oslo.reports': '2.0.1-0ubuntu1',
                'python3-oslo.rootwrap': '6.0.2-0ubuntu1',
                'python3-oslo.serialization': '3.1.1-0ubuntu1',
                'python3-oslo.service': '2.1.1-0ubuntu1.1',
                'python3-oslo.upgradecheck': '1.0.1-0ubuntu1',
                'python3-oslo.utils': '4.1.1-0ubuntu1',
                'python3-oslo.versionedobjects': '2.0.1-0ubuntu1',
                'python3-oslo.vmware': '3.3.1-0ubuntu1',
                'qemu-kvm': '1:4.2-3ubuntu6.19',
                'radvd': '1:2.17-2'}

        self.assertEqual(ost_base.apt.core, core)
        _deps = set(ost_base.apt.all).symmetric_difference(ost_base.apt.core)
        _deps = {k: ost_base.apt.all[k] for k in _deps}
        self.assertEqual(_deps, deps)

    @mock.patch('hotsos.core.host_helpers.packaging.CLIHelper')
    def test_plugin_not_runnable_clients_only(self, mock_cli):
        mock_cli.return_value = mock.MagicMock()
        mock_cli.return_value.dpkg_l.return_value = \
            [f"{line}\n" for line in DPKG_L_CLIENTS_ONLY.split('\n')]

        ost_base = openstack_core.OpenStackChecks()
        self.assertFalse(ost_base.is_runnable())

    def test_is_runnable(self):
        ost_base = openstack_core.OpenStackChecks()
        self.assertTrue(ost_base.is_runnable())


class TestOpenstackPluginNova(TestOpenstackBase):
    """
    Unit tests for Openstack nova plugin.
    """
    def test_nova_instances(self):
        self.assertEqual(list(nova_core.NovaBase().instances.keys()),
                         ['d1d75e2f-ada4-49bc-a963-528d89dfda25'])

    @utils.create_data_root({'ps': ARM_QEMU_PS_OUT})
    def test_nova_instances_arm(self):
        self.assertEqual(list(nova_core.NovaBase().instances.keys()),
                         ['66a20f33-f273-49bc-b738-936eebfbd8c5'])


class TestOpenStackSummary(TestOpenstackBase):
    """ Unit tests for OpenStack summary. """
    def test_get_summary(self):
        expected = {'systemd': {
                        'disabled': ['radvd'],
                        'enabled': [
                            'haproxy',
                            'keepalived',
                            'neutron-dhcp-agent',
                            'neutron-l3-agent',
                            'neutron-metadata-agent',
                            'neutron-openvswitch-agent',
                            'neutron-ovs-cleanup',
                            'nova-api-metadata',
                            'nova-compute'],
                    },
                    'ps': [
                        'haproxy (3)',
                        'keepalived (2)',
                        'neutron-dhcp-agent (1)',
                        'neutron-keepalived-state-change (2)',
                        'neutron-l3-agent (1)',
                        'neutron-metadata-agent (5)',
                        'neutron-openvswitch-agent (1)',
                        'nova-api-metadata (5)',
                        'nova-compute (1)']}
        inst = summary.OpenStackSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual["services"], expected)

    @mock.patch('hotsos.core.plugins.openstack.openstack.OSTProject.installed',
                True)
    @mock.patch('hotsos.core.plugins.openstack.OpenStackChecks.'
                'is_runnable', True)
    @mock.patch('hotsos.core.host_helpers.systemd.CLIHelper')
    def test_get_summary_apache_service(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.systemctl_list_unit_files.return_value = \
            OCTAVIA_UNIT_FILES.splitlines(keepends=True)
        expected = {'enabled': [
                        'apache2',
                        'octavia-health-manager',
                        'octavia-housekeeping',
                        'octavia-worker'],
                    'masked': [
                        'octavia-api']
                    }
        inst = summary.OpenStackSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual['services']['systemd'], expected)

    @mock.patch('hotsos.core.plugins.openstack.common.OpenstackBase.'
                'days_to_eol', 3000)
    @utils.create_data_root({os.path.join(APT_SOURCE_PATH.format(r)):
                             APT_UCA.format(r) for r in
                             ["stein", "ussuri", "train"]})
    def test_get_release_info(self):
        release_info = {'name': 'ussuri', 'days-to-eol': 3000}
        inst = summary.OpenStackSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual["release"], release_info)

    def test_get_pkg_info(self):
        expected = [
            'conntrack 1:1.4.5-2',
            'dnsmasq-base 2.80-1.1ubuntu1.4',
            'dnsmasq-utils 2.80-1.1ubuntu1.4',
            'haproxy 2.0.13-2ubuntu0.3',
            'keepalived 1:2.0.19-2ubuntu0.1',
            'keystone-common 2:17.0.1-0ubuntu1',
            'libvirt-daemon 6.0.0-0ubuntu8.15',
            'libvirt-daemon-driver-qemu 6.0.0-0ubuntu8.15',
            'libvirt-daemon-driver-storage-rbd 6.0.0-0ubuntu8.15',
            'libvirt-daemon-system 6.0.0-0ubuntu8.15',
            'libvirt-daemon-system-systemd 6.0.0-0ubuntu8.15',
            'neutron-common 2:16.4.1-0ubuntu2',
            'neutron-dhcp-agent 2:16.4.1-0ubuntu2',
            'neutron-fwaas-common 1:16.0.0-0ubuntu0.20.04.1',
            'neutron-l3-agent 2:16.4.1-0ubuntu2',
            'neutron-metadata-agent 2:16.4.1-0ubuntu2',
            'neutron-openvswitch-agent 2:16.4.1-0ubuntu2',
            'nova-api-metadata 2:21.2.3-0ubuntu1',
            'nova-common 2:21.2.3-0ubuntu1',
            'nova-compute 2:21.2.3-0ubuntu1',
            'nova-compute-kvm 2:21.2.3-0ubuntu1',
            'nova-compute-libvirt 2:21.2.3-0ubuntu1',
            'python3-barbicanclient 4.10.0-0ubuntu1',
            'python3-cinderclient 1:7.0.0-0ubuntu1',
            'python3-designateclient 2.11.0-0ubuntu2',
            'python3-glanceclient 1:3.1.1-0ubuntu1',
            'python3-keystone 2:17.0.1-0ubuntu1',
            'python3-keystoneauth1 4.0.0-0ubuntu1',
            'python3-keystoneclient 1:4.0.0-0ubuntu1',
            'python3-keystonemiddleware 9.0.0-0ubuntu1',
            'python3-neutron 2:16.4.1-0ubuntu2',
            'python3-neutron-fwaas 1:16.0.0-0ubuntu0.20.04.1',
            'python3-neutron-lib 2.3.0-0ubuntu1',
            'python3-neutronclient 1:7.1.1-0ubuntu1',
            'python3-nova 2:21.2.3-0ubuntu1',
            'python3-novaclient 2:17.0.0-0ubuntu1',
            'python3-oslo.cache 2.3.0-0ubuntu1',
            'python3-oslo.concurrency 4.0.2-0ubuntu1',
            'python3-oslo.config 1:8.0.2-0ubuntu1',
            'python3-oslo.context 1:3.0.2-0ubuntu1',
            'python3-oslo.db 8.1.0-0ubuntu1',
            'python3-oslo.i18n 4.0.1-0ubuntu1',
            'python3-oslo.log 4.1.1-0ubuntu1',
            'python3-oslo.messaging 12.1.6-0ubuntu1',
            'python3-oslo.middleware 4.0.2-0ubuntu1',
            'python3-oslo.policy 3.1.0-0ubuntu1.1',
            'python3-oslo.privsep 2.1.1-0ubuntu1',
            'python3-oslo.reports 2.0.1-0ubuntu1',
            'python3-oslo.rootwrap 6.0.2-0ubuntu1',
            'python3-oslo.serialization 3.1.1-0ubuntu1',
            'python3-oslo.service 2.1.1-0ubuntu1.1',
            'python3-oslo.upgradecheck 1.0.1-0ubuntu1',
            'python3-oslo.utils 4.1.1-0ubuntu1',
            'python3-oslo.versionedobjects 2.0.1-0ubuntu1',
            'python3-oslo.vmware 3.3.1-0ubuntu1',
            'qemu-kvm 1:4.2-3ubuntu6.19',
            'radvd 1:2.17-2'
        ]
        inst = summary.OpenStackSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual["dpkg"], expected)

    @mock.patch.object(neutron_core, 'CLIHelper')
    def test_run_summary(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.journalctl.return_value = \
            JOURNALCTL_OVS_CLEANUP_GOOD.splitlines(keepends=True)
        inst = neutron_core.ServiceChecks()
        self.assertFalse(inst.ovs_cleanup_run_manually)

    @mock.patch.object(neutron_core, 'CLIHelper')
    def test_run_summary2(self, mock_helper):
        """
        Covers scenario where we had manual restart but not after last reboot.
        """
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.journalctl.return_value = \
            JOURNALCTL_OVS_CLEANUP_GOOD2.splitlines(keepends=True)
        inst = neutron_core.ServiceChecks()
        self.assertFalse(inst.ovs_cleanup_run_manually)

    @mock.patch.object(neutron_core, 'CLIHelper')
    def test_run_summary_w_issue(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.journalctl.return_value = \
            JOURNALCTL_OVS_CLEANUP_BAD.splitlines(keepends=True)
        inst = neutron_core.ServiceChecks()
        self.assertTrue(inst.ovs_cleanup_run_manually)

    def test_get_neutronl3ha_info(self):
        expected = {'backup': 1}
        inst = summary.OpenStackSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual['neutron-l3ha'], expected)


class TestOpenstackVmInfo(TestOpenstackBase):
    """ Unit tests for OpenStack vm info. """
    def test_get_vm_checks(self):
        expected = {"running": {
                        'count': 1,
                        'uuids': ['d1d75e2f-ada4-49bc-a963-528d89dfda25']},
                    "cpu-models": {'Skylake-Client-IBRS': 1},
                    "vcpu-info": {
                        "available-cores": 2,
                        "system-cores": 2,
                        "smt": False,
                        "used": 1,
                        "overcommit-factor": 0.5}}
        inst = vm_info.OpenstackInstanceChecks()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual['vm-info'], expected)

    def test_vm_migration_analysis(self):
        expected = {'live-migration': {
                        '359150c9-6f40-416e-b381-185bff09e974': [
                            {'start': '2022-02-10 16:18:28',
                             'end': '2022-02-10 16:18:28',
                             'duration': 0.0,
                             'regressions': {
                                 'memory': 0,
                                 'disk': 0},
                             'iterations': 1}]
                    }}
        with GlobalSearcher() as searcher:
            inst = vm_info.NovaServerMigrationAnalysis(searcher)
            actual = self.part_output_to_actual(inst.output)

        self.assertEqual(actual['nova-migrations'], expected)


class TestOpenstackNovaExternalEvents(TestOpenstackBase):
    """ Unit tests for OpenStack Nova external events. """
    def test_get_events(self):
        with GlobalSearcher() as searcher:
            inst = nova_external_events.NovaExternalEventChecks(searcher)
            events = {'network-changed': {"succeeded": 1},
                      'network-vif-plugged': {"succeeded": 1}}
            actual = self.part_output_to_actual(inst.output)
            self.assertEqual(actual["os-server-external-events"], events)


class TestOpenstackServiceNetworkChecks(TestOpenstackBase):
    """ Unit tests for OpenStack service network checks. """
    def test_get_ns_info(self):
        ns_info = {'qrouter': 1, 'fip': 1, 'snat': 1}
        inst = service_network_checks.OpenstackNetworkChecks()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual["namespaces"], ns_info)

    @mock.patch.object(service_network_checks, 'CLIHelper')
    def test_get_ns_info_none(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.ip_link.return_value = []
        inst = service_network_checks.OpenstackNetworkChecks()
        actual = self.part_output_to_actual(inst.output)
        self.assertNotIn('namespaces', actual)

    def test_get_network_checker(self):
        expected = {
            'config': {
                'nova': {
                    'my_ip': {
                        'br-ens3': {
                            'addresses': ['10.0.0.128'],
                            'hwaddr': '22:c2:7b:1c:12:1b',
                            'mtu': 1500,
                            'state': 'UP',
                            'speed': 'unknown'}},
                    'live_migration_inbound_addr': {
                        'br-ens3': {
                            'addresses': ['10.0.0.128'],
                            'hwaddr': '22:c2:7b:1c:12:1b',
                            'mtu': 1500,
                            'state': 'UP',
                            'speed': 'unknown'}}},
                'neutron': {'local_ip': {
                    'br-ens3': {
                        'addresses': ['10.0.0.128'],
                        'hwaddr': '22:c2:7b:1c:12:1b',
                        'mtu': 1500,
                        'state': 'UP',
                        'speed': 'unknown'}}}
            },
            'router-port-mtus': {'qr': [1450], 'sg': [1450]},
            'namespaces': {
                'fip': 1,
                'qrouter': 1,
                'snat': 1
            },
        }
        inst = service_network_checks.OpenstackNetworkChecks()
        actual = self.part_output_to_actual(inst.output)
        for key, value in expected.items():
            self.assertEqual(actual[key], value)

        self.assertEqual(IssuesManager().load_issues(), {})

    @mock.patch.object(service_network_checks, 'VXLAN_HEADER_BYTES', 31)
    def test_get_network_checker_w_mtu_issue(self):
        inst = service_network_checks.OpenstackNetworkChecks()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual['router-port-mtus'], {'qr': [1450],
                                                      'sg': [1450]})
        issues = {'potential-issues': [{
                    'message': ('This Neutron L3 agent host has one or more '
                                'router ports with mtu=1450 which is greater '
                                'or equal to the smallest allowed (1449) on '
                                'the physical network. This will result in '
                                'dropped packets or unexpected fragmentation '
                                'in overlay networks.'),
                    'origin': 'openstack.testpart',
                    'type': 'OpenstackWarning'}]}
        self.assertEqual(IssuesManager().load_issues(), issues)


class TestOpenstackServiceFeatures(TestOpenstackBase):
    """ Unit tests for OpenStack service features. """
    def test_get_service_features(self):
        inst = service_features.ServiceFeatureChecks()
        expected = {'neutron': {'dhcp-agent': {
                                    'enable_isolated_metadata': True,
                                    'enable_metadata_network': True,
                                    'ovs_use_veth': False},
                                'l3-agent': {
                                    'agent_mode': 'dvr_snat'},
                                'main': {
                                    'debug': True,
                                    'availability_zone': 'nova'},
                                'openvswitch-agent': {
                                    'l2_population': True,
                                    'firewall_driver': 'openvswitch'}},
                    'nova': {'main': {
                                'debug': True,
                                'live_migration_permit_auto_converge': False,
                                'live_migration_permit_post_copy': False}},
                    'api-ssl': False}
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual["features"], expected)

    @utils.create_data_root({'etc/neutron/neutron.conf': '',
                             'etc/neutron/ovn.ini':
                             ('[DEFAULT]\n'
                              'enable_distributed_floating_ip = true')})
    def test_get_service_features_ovn(self):
        inst = service_features.ServiceFeatureChecks()
        actual = self.part_output_to_actual(inst.output)
        expected = {'api-ssl': False,
                    'neutron': {'main': {'debug': False},
                                'ovn': {'enable_distributed_floating_ip':
                                        True}}}
        self.assertEqual(actual["features"], expected)


class TestOpenstackCPUPinning(TestOpenstackBase):
    """ Unit tests for OpenStack Nova cpu pinning. """
    def test_cores_to_list(self):
        ret = host_helpers.ConfigBase.expand_value_ranges("0-4,8,9,28-32")
        self.assertEqual(ret, [0, 1, 2, 3, 4, 8, 9, 28, 29, 30, 31, 32])

    @mock.patch('hotsos.core.plugins.system.system.NUMAInfo.nodes',
                {0: [1, 3, 5], 1: [0, 2, 4]})
    @mock.patch('hotsos.core.plugins.system.system.SystemBase.num_cpus', 16)
    @mock.patch('hotsos.core.plugins.kernel.config.KernelConfig.get',
                lambda *args, **kwargs: range(9, 16))
    @mock.patch('hotsos.core.plugins.kernel.config.SystemdConfig.get',
                lambda *args, **kwargs: range(2, 9))
    def test_nova_pinning_base(self):
        with mock.patch('hotsos.core.plugins.openstack.nova.CPUPinning.'
                        'vcpu_pin_set', [0, 1, 2]):
            inst = nova_core.CPUPinning()
            self.assertEqual(inst.cpu_dedicated_set_name, 'vcpu_pin_set')

        inst = nova_core.CPUPinning()
        self.assertEqual(inst.cpu_shared_set, [])
        self.assertEqual(inst.cpu_dedicated_set, [])
        self.assertEqual(inst.vcpu_pin_set, [])
        self.assertEqual(inst.cpu_dedicated_set_name, 'cpu_dedicated_set')
        self.assertEqual(inst.cpu_dedicated_set_intersection_isolcpus, [])
        self.assertEqual(inst.cpu_dedicated_set_intersection_cpuaffinity, [])
        self.assertEqual(inst.cpu_shared_set_intersection_isolcpus, [])
        self.assertEqual(inst.cpuaffinity_intersection_isolcpus, [])
        self.assertEqual(inst.unpinned_cpus_pcent, 12)
        self.assertEqual(inst.num_unpinned_cpus, 2)
        self.assertEqual(inst.nova_pinning_from_multi_numa_nodes, False)
        inst = nova_core.CPUPinning()
        with mock.patch('hotsos.core.plugins.openstack.nova.CPUPinning.'
                        'cpu_dedicated_set', [0, 1, 4]):
            self.assertEqual(inst.nova_pinning_from_multi_numa_nodes, True)


@utils.load_templated_tests('scenarios/openstack')
class TestOpenstackScenarios(TestOpenstackBase):
    """
    Scenario tests can be written using YAML templates that are auto-loaded
    into this test runner. This is the recommended way to write tests for
    scenarios. It is however still possible to write the tests in Python if
    required. See https://hotsos.readthedocs.io/en/latest/contrib/testing.html
    for more information.
    """


class TestOpenstackApache2SSL(TestOpenstackBase):
    """ Unit tests for OpenStack apache ssl configs. """
    @utils.create_data_root(
        {'etc/apache2/sites-enabled/openstack_https_frontend.conf':
         APACHE2_SSL_CONF})
    def test_ssl_enabled(self):
        base = openstack_core.OpenstackBase()
        self.assertTrue(base.ssl_enabled)

    def test_ssl_disabled(self):
        base = openstack_core.OpenstackBase()
        self.assertFalse(base.ssl_enabled)

    @utils.create_data_root(
        {'etc/apache2/sites-enabled/openstack_https_frontend.conf':
         APACHE2_SSL_CONF,
         'etc/apache2/ssl/keystone/cert_10.5.100.2': CERTIFICATE_FILE})
    def test_ssl_certificate_list(self):
        base = openstack_core.OpenstackBase()
        self.assertTrue(len(base._apache2_certificates), 1)  # noqa,pylint: disable=protected-access
        self.assertEqual(base._apache2_certificates,  # noqa,pylint: disable=protected-access
                         ['etc/apache2/ssl/keystone/cert_10.5.100.2'])

    @utils.create_data_root(
        {'etc/apache2/sites-enabled/openstack_https_frontend.conf':
         APACHE2_SSL_CONF,
         'etc/apache2/ssl/keystone/cert_10.5.100.2': CERTIFICATE_FILE,
         'sos_commands/date/date': 'Thu Apr 12 16:19:17 UTC 2022'})
    def test_ssl_expiration_false(self):
        base = openstack_core.OpenstackBase()
        self.assertEqual(len(base.apache2_certificates_expiring), 0)

    @utils.create_data_root(
        {'etc/apache2/sites-enabled/openstack_https_frontend.conf':
         APACHE2_SSL_CONF,
         'etc/apache2/ssl/keystone/cert_10.5.100.2': CERTIFICATE_FILE,
         'sos_commands/date/date': 'Thu Apr 12 16:19:17 UTC 2023'})
    def test_ssl_expiration_true(self):
        base = openstack_core.OpenstackBase()
        self.assertTrue(len(base.apache2_certificates_expiring), 1)

    @utils.create_data_root(
        {'etc/apache2/sites-enabled/openstack_https_frontend.conf':
         APACHE2_SSL_CONF_RGW})
    def test_1974138_apache2_allow_encoded_slashes_true(self):
        base = openstack_core.OpenstackBase()
        self.assertTrue(base.apache2_allow_encoded_slashes_on)

    @utils.create_data_root(
        {'etc/apache2/sites-enabled/openstack_https_frontend.conf':
         APACHE2_SSL_CONF})
    def test_lp1974138_apache2_allow_encoded_slashes_false(self):
        base = openstack_core.OpenstackBase()
        self.assertFalse(base.apache2_allow_encoded_slashes_on)
