import os
import tempfile
from datetime import datetime

import mock

from . import utils

import hotsos.core.plugins.openstack as openstack_core
from hotsos.core import host_helpers
from hotsos.core.issues import IssuesManager
from hotsos.core.issues.utils import IssuesStore
from hotsos.core.config import setup_config, HotSOSConfig
from hotsos.core.ycheck.scenarios import YScenarioChecker
from hotsos.core.host_helpers.systemd import SystemdService
from hotsos.core.searchtools import FileSearcher
from hotsos.plugin_extensions.openstack import (
    vm_info,
    nova_external_events,
    summary,
    service_network_checks,
    service_features,
    agent_event_checks,
    agent_exceptions,
)

OCTAVIA_UNIT_FILES = """
apache-htcacheclean.service               disabled       
apache-htcacheclean@.service              disabled       
apache2.service                           enabled        
apache2@.service                          disabled       
jujud-unit-octavia-0.service              enabled        
jujud-unit-octavia-hacluster-5.service    enabled        
octavia-api.service                       masked         
octavia-health-manager.service            enabled        
octavia-housekeeping.service              enabled        
octavia-worker.service                    enabled 
"""  # noqa

OCTAVIA_UNIT_FILES_APACHE_MASKED = """
apache-htcacheclean.service               disabled       
apache-htcacheclean@.service              disabled       
apache2.service                           masked        
apache2@.service                          disabled       
jujud-unit-octavia-0.service              enabled        
jujud-unit-octavia-hacluster-5.service    enabled        
octavia-api.service                       masked         
octavia-health-manager.service            enabled        
octavia-housekeeping.service              enabled        
octavia-worker.service                    enabled 
"""  # noqa

NEUTRON_UNIT_FILES_MASKED = """
neutron-dhcp-agent.service             masked          enabled      
neutron-l3-agent.service               masked          enabled      
neutron-metadata-agent.service         masked          enabled      
neutron-metering-agent.service         masked          enabled      
neutron-openvswitch-agent.service      masked          enabled      
neutron-ovs-cleanup.service            enabled         enabled
"""  # noqa


APT_UCA = """
# Ubuntu Cloud Archive
deb http://ubuntu-cloud.archive.canonical.com/ubuntu bionic-updates/{} main
"""

SVC_CONF = """
[DEFAULT]
debug = True
"""

JOURNALCTL_OVS_CLEANUP_GOOD = """
-- Logs begin at Thu 2021-04-29 17:44:42 BST, end at Thu 2021-05-06 09:05:01 BST. --
Apr 29 17:52:37 juju-9c28ce-ubuntu-11 systemd[1]: Starting OpenStack Neutron OVS cleanup...
Apr 29 17:52:39 juju-9c28ce-ubuntu-11 sudo[15179]:  neutron : TTY=unknown ; PWD=/var/lib/neutron ; USER=root ; COMMAND=/usr/bin/neutron-rootwrap /etc/neutron/r
Apr 29 17:52:39 juju-9c28ce-ubuntu-11 sudo[15179]: pam_unix(sudo:session): session opened for user root by (uid=0)
Apr 29 17:52:39 juju-9c28ce-ubuntu-11 ovs-vsctl[15183]: ovs|00001|vsctl|INFO|Called as /usr/bin/ovs-vsctl --timeout=5 --id=@manager -- create Manager "target=\
Apr 29 17:52:39 juju-9c28ce-ubuntu-11 sudo[15179]: pam_unix(sudo:session): session closed for user root
Apr 29 17:52:39 juju-9c28ce-ubuntu-11 systemd[1]: Started OpenStack Neutron OVS cleanup.
May 03 06:17:29 juju-9c28ce-ubuntu-11 systemd[1]: Stopped OpenStack Neutron OVS cleanup.
-- Reboot --
May 04 11:05:56 juju-9c28ce-ubuntu-11 systemd[1]: Starting OpenStack Neutron OVS cleanup...
May 04 11:06:20 juju-9c28ce-ubuntu-11 systemd[1]: Started OpenStack Neutron OVS cleanup.
"""  # noqa

JOURNALCTL_OVS_CLEANUP_GOOD2 = """
-- Logs begin at Thu 2021-04-29 17:44:42 BST, end at Thu 2021-05-06 09:05:01 BST. --
Apr 29 17:52:37 juju-9c28ce-ubuntu-11 systemd[1]: Starting OpenStack Neutron OVS cleanup...
Apr 29 17:52:39 juju-9c28ce-ubuntu-11 sudo[15179]:  neutron : TTY=unknown ; PWD=/var/lib/neutron ; USER=root ; COMMAND=/usr/bin/neutron-rootwrap /etc/neutron/r
Apr 29 17:52:39 juju-9c28ce-ubuntu-11 sudo[15179]: pam_unix(sudo:session): session opened for user root by (uid=0)
Apr 29 17:52:39 juju-9c28ce-ubuntu-11 ovs-vsctl[15183]: ovs|00001|vsctl|INFO|Called as /usr/bin/ovs-vsctl --timeout=5 --id=@manager -- create Manager "target=\
Apr 29 17:52:39 juju-9c28ce-ubuntu-11 sudo[15179]: pam_unix(sudo:session): session closed for user root
Apr 29 17:52:39 juju-9c28ce-ubuntu-11 systemd[1]: Started OpenStack Neutron OVS cleanup.
May 03 06:17:29 juju-9c28ce-ubuntu-11 systemd[1]: Stopped OpenStack Neutron OVS cleanup.
May 04 10:05:56 juju-9c28ce-ubuntu-11 systemd[1]: Starting OpenStack Neutron OVS cleanup...
May 04 10:06:20 juju-9c28ce-ubuntu-11 systemd[1]: Started OpenStack Neutron OVS cleanup.
-- Reboot --
May 04 11:05:56 juju-9c28ce-ubuntu-11 systemd[1]: Starting OpenStack Neutron OVS cleanup...
May 04 11:06:20 juju-9c28ce-ubuntu-11 systemd[1]: Started OpenStack Neutron OVS cleanup.
"""  # noqa

JOURNALCTL_OVS_CLEANUP_BAD = """
-- Logs begin at Thu 2021-04-29 17:44:42 BST, end at Thu 2021-05-06 09:05:01 BST. --
Apr 29 17:52:37 juju-9c28ce-ubuntu-11 systemd[1]: Starting OpenStack Neutron OVS cleanup...
Apr 29 17:52:39 juju-9c28ce-ubuntu-11 sudo[15179]:  neutron : TTY=unknown ; PWD=/var/lib/neutron ; USER=root ; COMMAND=/usr/bin/neutron-rootwrap /etc/neutron/r
Apr 29 17:52:39 juju-9c28ce-ubuntu-11 sudo[15179]: pam_unix(sudo:session): session opened for user root by (uid=0)
Apr 29 17:52:39 juju-9c28ce-ubuntu-11 ovs-vsctl[15183]: ovs|00001|vsctl|INFO|Called as /usr/bin/ovs-vsctl --timeout=5 --id=@manager -- create Manager "target=\
Apr 29 17:52:39 juju-9c28ce-ubuntu-11 sudo[15179]: pam_unix(sudo:session): session closed for user root
Apr 29 17:52:39 juju-9c28ce-ubuntu-11 systemd[1]: Started OpenStack Neutron OVS cleanup.
May 03 06:17:29 juju-9c28ce-ubuntu-11 systemd[1]: Stopped OpenStack Neutron OVS cleanup.
May 04 10:05:56 juju-9c28ce-ubuntu-11 systemd[1]: Starting OpenStack Neutron OVS cleanup...
May 04 10:06:20 juju-9c28ce-ubuntu-11 systemd[1]: Started OpenStack Neutron OVS cleanup.
"""  # noqa

JOURNALCTL_NEUTRON_OPENVSWITCH_AGENT = """
-- Unit neutron-openvswitch-agent.service has begun starting up.
Feb 14 04:31:34 lcpip-hcosw002 systemd[1]: Started Openstack Neutron Open vSwitch Plugin Agent.
-- Subject: Unit neutron-openvswitch-agent.service has finished start-up
-- Defined-By: systemd
-- Support: http://www.ubuntu.com/support
--
-- Unit neutron-openvswitch-agent.service has finished starting up.
"""  # noqa

JOURNALCTL_OPENVSWITCH_SWITCH = """
Feb 21 02:28:15 lcpip-hcosw002 systemd[1]: Started Open vSwitch.
-- Subject: Unit openvswitch-switch.service has finished start-up
-- Defined-By: systemd
-- Support: http://www.ubuntu.com/support
--
-- Unit openvswitch-switch.service has finished starting up.
"""  # noqa

DPKG_L_MIX_RELS = """
ii  nova-common                          2:21.2.1-0ubuntu1                                    all          OpenStack Compute - common files
ii  neutron-common                       2:17.2.0-0ubuntu2                                    all          Neutron is a virtual network service for Openstack - common
"""  # noqa

DPKG_L_CLIENTS_ONLY = """
ii  python3-neutronclient                       2:17.2.0-0ubuntu2                                    all          Neutron is a virtual network service for Openstack - common
"""  # noqa

LP_1929832 = r"""
2021-05-26 18:56:57.344 3457514 ERROR neutron.agent.l3.agent [-] Error while deleting router 8f14f808-c23a-422b-a3a8-7fb747e89676: neutron_lib.exceptions.ProcessExecutionError: Exit code: 99; Stdin: ; Stdout: ; Stderr: /usr/bin/neutron-rootwrap: Unauthorized command: kill -15 365134 (no filter matched)
"""  # noqa
LP_1896506 = r"""
Apr  6 06:36:09 kermath Keepalived_vrrp[23396]: Unknown configuration entry 'no_track' for ip address - ignoring
"""  # noqa
LP_1928031 = r"""
2021-08-26 05:47:20.754 1331249 ERROR neutron.agent.ovn.metadata.server AttributeError: 'MetadataProxyHandler' object has no attribute 'sb_idl'
"""  # noqa
LP_2008099 = r"""
2022-02-28 22:43:06.269 2452 ERROR octavia.amphorae.drivers.haproxy.exceptions [req-517fc350-0d44-49d9-8c42-bf0ee08743cc - 77dd427b317c41bc92306aa341174958 - - -] Amphora agent returned unexpected result code 400 with response {'message': 'Invalid request', 'details': "[ALERT] 058/224306 (1748) : Proxy '2d4fb3e0-d743-48f6-a69a-c37e2c1246f2:8a692eba-7d40-4f8d-8a74-77d8c4f3dba8': unable to find local peer 'xFiQsE9fy1TMp7CDRHT-ClSZOEI' in peers section '3705f8d100144614a7475324946a3a5f_peers'.\n[WARNING] 058/224306 (1748) : Removing incomplete section 'peers 3705f8d100144614a7475324946a3a5f_peers' (no peer named 'xFiQsE9fy1TMp7CDRHT-ClSZOEI').\n[ALERT] 058/224306 (1748) : Fatal errors found in configuration.\n"}
""" # noqa

EVENT_PCIDEVNOTFOUND_LOG = r"""
2021-09-17 13:49:47.257 3060998 WARNING nova.pci.utils [req-f6448047-9a0f-453b-9189-079dd00ab3a3 - - - - -] No net device was found for VF 0000:3b:10.0: nova.exception.PciDeviceNotFoundById: PCI device 0000:3b:10.0 not found
2021-09-17 13:49:47.609 3060998 WARNING nova.pci.utils [req-f6448047-9a0f-453b-9189-079dd00ab3a3 - - - - -] No net device was found for VF 0000:3b:0f.7: nova.exception.PciDeviceNotFoundById: PCI device 0000:3b:0f.7 not found
"""  # noqa

EVENT_APACHE_CONN_REFUSED_LOG = r"""
[Tue Oct 26 17:27:20.477742 2021] [proxy:error] [pid 29484:tid 140230740928256] (111)Connection refused: AH00957: HTTP: attempt to connect to 127.0.0.1:8981 (localhost) failed
[Tue Oct 26 17:29:22.338485 2021] [proxy:error] [pid 29485:tid 140231076472576] (111)Connection refused: AH00957: HTTP: attempt to connect to 127.0.0.1:8981 (localhost) failed
[Tue Oct 26 17:31:18.143966 2021] [proxy:error] [pid 29485:tid 140231219083008] (111)Connection refused: AH00957: HTTP: attempt to connect to 127.0.0.1:8981 (localhost) failed
"""  # noqa

EVENT_OCTAVIA_CHECKS = r"""
2021-03-09 14:53:04.467 9684 INFO octavia.controller.worker.v1.flows.amphora_flows [-] Performing failover for amphora: {'id': 'ac9849a2-f81e-4578-aedf-3637420c97ff', 'load_balancer_id': '7a3b90ed-020e-48f0-ad6f-b28443fa2277', 'lb_network_ip': 'fc00:1f77:9de0:cd56:f816:3eff:fe6c:2963', 'compute_id': 'af04050e-b845-4bca-9e61-ded03039d2c6', 'role': 'master_or_backup'}
2021-03-09 17:44:37.379 9684 INFO octavia.controller.worker.v1.flows.amphora_flows [-] Performing failover for amphora: {'id': '0cd68e26-abb7-4e6b-8272-5ccf017b6de7', 'load_balancer_id': '9cd90142-5501-4362-93ef-1ad219baf45a', 'lb_network_ip': 'fc00:1f77:9de0:cd56:f816:3eff:feae:514c', 'compute_id': '314e4b2f-9c64-41c9-b337-7d0229127d48', 'role': 'master_or_backup'}
2021-03-09 18:19:10.369 9684 INFO octavia.controller.worker.v1.flows.amphora_flows [-] Performing failover for amphora: {'id': 'ddaf13ec-858f-42d1-bdc8-d8b529c7c524', 'load_balancer_id': 'e9cb98af-9c21-4cf6-9661-709179ce5733', 'lb_network_ip': 'fc00:1f77:9de0:cd56:f816:3eff:fe2f:9d58', 'compute_id': 'c71c5eca-c862-49dd-921c-273e51dfb574', 'role': 'master_or_backup'}
2021-03-09 20:01:46.376 9684 INFO octavia.controller.worker.v1.flows.amphora_flows [-] Performing failover for amphora: {'id': 'bbf6107b-86b5-45f5-ace1-e077871860ac', 'load_balancer_id': '98aefcff-60e5-4087-8ca6-5087ae970440', 'lb_network_ip': 'fc00:1f77:9de0:cd56:f816:3eff:fe5b:4afb', 'compute_id': '54061176-61c8-4915-b896-e026c3eeb60f', 'role': 'master_or_backup'}

2021-06-01 23:25:39.223 43076 WARNING octavia.controller.healthmanager.health_drivers.update_db [-] Amphora 3604bf2a-ee51-4135-97e2-ec08ed9321db health message was processed too slowly: 10.550589084625244s! The system may be overloaded or otherwise malfunctioning. This heartbeat has been ignored and no update was made to the amphora health entry. THIS IS NOT GOOD.
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


class TestOpenstackBase(utils.BaseTestCase):

    IP_LINK_SHOW = None

    def fake_ip_link_w_errors_drops(self):
        lines = ''.join(self.IP_LINK_SHOW).format(10000000, 100000000)
        return [line + '\n' for line in lines.split('\n')]

    def fake_ip_link_no_errors_drops(self):
        lines = ''.join(self.IP_LINK_SHOW).format(0, 0)
        return [line + '\n' for line in lines.split('\n')]

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        setup_config(PLUGIN_NAME='openstack')

        if self.IP_LINK_SHOW is None:
            path = os.path.join(HotSOSConfig.DATA_ROOT,
                                "sos_commands/networking/ip_-s_-d_link")
            with open(path) as fd:
                self.IP_LINK_SHOW = fd.readlines()


class TestOpenstackPluginCore(TestOpenstackBase):

    def test_release_name(self):
        base = openstack_core.OpenstackBase()
        self.assertEqual(base.release_name, 'ussuri')

    def test_project_catalog_package_exprs(self):
        c = openstack_core.OSTProjectCatalog()
        core = ['ceilometer',
                'octavia',
                'placement',
                'manila',
                'designate',
                'neutron',
                'glance',
                'masakari',
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
                'nfs--ganesha',
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
                'python3?-heat\\S*',
                'python3?-keystone\\S*',
                'mysql-?\\S+',
                'python3?-neutron\\S*',
                'python3?-gnocchi\\S*',
                'qemu-kvm',
                'conntrack',
                'libvirt-daemon',
                'python3?-placement\\S*',
                'python3?-octavia\\S*',
                'python3?-glance\\S*',
                'dnsmasq',
                'python3?-designate\\S*']

        self.assertEqual(sorted(c.packages_core_exprs), sorted(core))
        self.assertEqual(sorted(c.packages_dep_exprs), sorted(deps))

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
                'mysql-common': '5.8+1.0.5ubuntu2',
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

        self.assertEqual(ost_base.apt_check.core, core)
        _deps = set(ost_base.apt_check.all).symmetric_difference(
                                                       ost_base.apt_check.core)
        _deps = {k: ost_base.apt_check.all[k] for k in _deps}
        self.assertEqual(_deps, deps)

    @mock.patch('hotsos.core.host_helpers.packaging.CLIHelper')
    def test_plugin_not_runnable_clients_only(self, mock_cli):
        mock_cli.return_value = mock.MagicMock()
        mock_cli.return_value.dpkg_l.return_value = \
            ["{}\n".format(line) for line in DPKG_L_CLIENTS_ONLY.split('\n')]

        ost_base = openstack_core.OpenstackChecksBase()
        self.assertFalse(ost_base.plugin_runnable)

    def test_plugin_runnable(self):
        ost_base = openstack_core.OpenstackChecksBase()
        self.assertTrue(ost_base.plugin_runnable)


class TestOpenstackSummary(TestOpenstackBase):

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
                            'nova-compute',
                        ],
                        'indirect': ['vaultlocker-decrypt'],
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
        inst = summary.OpenstackSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual["services"], expected)

    @mock.patch('hotsos.core.plugins.openstack.OSTProject.installed', True)
    @mock.patch('hotsos.core.plugins.openstack.OpenstackServiceChecksBase.'
                'openstack_installed', True)
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
        inst = summary.OpenstackSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual['services']['systemd'], expected)

    def test_get_release_info(self):
        with tempfile.TemporaryDirectory() as dtmp:
            for rel in ["stein", "ussuri", "train"]:
                with open(os.path.join(dtmp,
                                       "cloud-archive-{}.list".format(rel)),
                          'w') as fd:
                    fd.write(APT_UCA.format(rel))

            with mock.patch('hotsos.core.plugins.openstack.OpenstackBase.'
                            'apt_source_path', dtmp):
                inst = summary.OpenstackSummary()
                actual = self.part_output_to_actual(inst.output)
                self.assertEqual(actual["release"], "ussuri")

    def test_get_debug_log_info(self):
        expected = {'neutron': True, 'nova': True}
        with tempfile.TemporaryDirectory() as dtmp:
            for svc in ["nova", "neutron"]:
                conf_path = "etc/{svc}/{svc}.conf".format(svc=svc)
                os.makedirs(os.path.dirname(os.path.join(dtmp, conf_path)))
                with open(os.path.join(dtmp, conf_path), 'w') as fd:
                    fd.write(SVC_CONF)

            setup_config(DATA_ROOT=dtmp)
            inst = summary.OpenstackSummary()
            # fake some core packages
            inst.apt_check._core_packages = {"foo": 1}
            actual = self.part_output_to_actual(inst.output)
            self.assertEqual(actual["debug-logging-enabled"],
                             expected)

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
            'mysql-common 5.8+1.0.5ubuntu2',
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
        inst = summary.OpenstackSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual["dpkg"], expected)

    @mock.patch('hotsos.core.plugins.openstack.host_helpers.CLIHelper')
    def test_run_summary(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.journalctl.return_value = \
            JOURNALCTL_OVS_CLEANUP_GOOD.splitlines(keepends=True)
        inst = openstack_core.NeutronServiceChecks()
        self.assertFalse(inst.ovs_cleanup_run_manually)

    @mock.patch('hotsos.core.plugins.openstack.host_helpers.CLIHelper')
    def test_run_summary2(self, mock_helper):
        """
        Covers scenario where we had manual restart but not after last reboot.
        """
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.journalctl.return_value = \
            JOURNALCTL_OVS_CLEANUP_GOOD2.splitlines(keepends=True)
        inst = openstack_core.NeutronServiceChecks()
        self.assertFalse(inst.ovs_cleanup_run_manually)

    @mock.patch('hotsos.core.plugins.openstack.host_helpers.CLIHelper')
    def test_run_summary_w_issue(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.journalctl.return_value = \
            JOURNALCTL_OVS_CLEANUP_BAD.splitlines(keepends=True)
        inst = openstack_core.NeutronServiceChecks()
        self.assertTrue(inst.ovs_cleanup_run_manually)

    def test_get_neutronl3ha_info(self):
        expected = {'backup': ['984c22fd-64b3-4fa1-8ddd-87090f401ce5']}
        inst = summary.OpenstackSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual['neutron-l3ha'], expected)


class TestOpenstackVmInfo(TestOpenstackBase):

    def test_get_vm_checks(self):
        expected = {"vm-info": {
                        "running": ['d1d75e2f-ada4-49bc-a963-528d89dfda25'],
                        "vcpu-info": {
                            "available-cores": 2,
                            "system-cores": 2,
                            "smt": False,
                            "used": 1,
                            "overcommit-factor": 0.5,
                            }
                        }
                    }
        inst = vm_info.OpenstackInstanceChecks()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual, expected)

    def test_vm_migration_analysis(self):
        expected = {'nova-migrations': {
                        'live-migration': {
                            '359150c9-6f40-416e-b381-185bff09e974': [
                                {'start': '2022-02-10 16:18:28',
                                 'end': '2022-02-10 16:18:28',
                                 'duration': 0.0,
                                 'regressions': {
                                     'memory': 0,
                                     'disk': 0},
                                 'iterations': 1}]
                        }}}
        inst = vm_info.NovaServerMigrationAnalysis()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual, expected)


class TestOpenstackNovaExternalEvents(TestOpenstackBase):

    def test_get_events(self):
        inst = nova_external_events.NovaExternalEventChecks()
        events = {'network-changed':
                  {"succeeded":
                   [{"port": "6a0486f9-823b-4dcf-91fb-8a4663d31855",
                     "instance": "359150c9-6f40-416e-b381-185bff09e974"}]},
                  'network-vif-plugged':
                  {"succeeded":
                   [{"instance": '359150c9-6f40-416e-b381-185bff09e974',
                     "port": "6a0486f9-823b-4dcf-91fb-8a4663d31855"}]}}
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual["os-server-external-events"], events)


class TestOpenstackServiceNetworkChecks(TestOpenstackBase):

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
        self.assertFalse('namespaces' in actual)

    def test_get_network_checker(self):
        expected = {
            'config': {
                'nova': {
                    'my_ip': {
                        'br-ens3': {
                            'addresses': ['10.0.0.128'],
                            'hwaddr': '22:c2:7b:1c:12:1b',
                            'state': 'UP',
                            'speed': 'unknown'}},
                    'live_migration_inbound_addr': {
                        'br-ens3': {
                            'addresses': ['10.0.0.128'],
                            'hwaddr': '22:c2:7b:1c:12:1b',
                            'state': 'UP',
                            'speed': 'unknown'}}},
                'neutron': {'local_ip': {
                    'br-ens3': {
                        'addresses': ['10.0.0.128'],
                        'hwaddr': '22:c2:7b:1c:12:1b',
                        'state': 'UP',
                        'speed': 'unknown'}}}
            },
            'namespaces': {
                'fip': 1,
                'qrouter': 1,
                'snat': 1
            },
        }
        inst = service_network_checks.OpenstackNetworkChecks()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual, expected)


class TestOpenstackServiceFeatures(TestOpenstackBase):

    def test_get_service_features(self):
        inst = service_features.ServiceFeatureChecks()
        expected = {'neutron': {'dhcp-agent': {
                                    'enable_isolated_metadata': True,
                                    'enable_metadata_network': True,
                                    'ovs_use_veth': False},
                                'l3-agent': {
                                    'agent_mode': 'dvr_snat'},
                                'main': {
                                    'availability_zone': 'nova'},
                                'openvswitch-agent': {
                                    'l2_population': True,
                                    'firewall_driver': 'openvswitch'}},
                    'nova': {'main': {
                                'live_migration_permit_auto_converge': False,
                                'live_migration_permit_post_copy': False}}}
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual["features"], expected)


class TestOpenstackCPUPinning(TestOpenstackBase):

    def test_cores_to_list(self):
        ret = host_helpers.ConfigBase.expand_value_ranges("0-4,8,9,28-32")
        self.assertEqual(ret, [0, 1, 2, 3, 4, 8, 9, 28, 29, 30, 31, 32])

    @mock.patch('hotsos.core.plugins.system.NUMAInfo.nodes',
                {0: [1, 3, 5], 1: [0, 2, 4]})
    @mock.patch('hotsos.core.plugins.system.SystemBase.num_cpus', 16)
    @mock.patch('hotsos.core.plugins.kernel.KernelConfig.get',
                lambda *args, **kwargs: range(9, 16))
    @mock.patch('hotsos.core.plugins.kernel.SystemdConfig.get',
                lambda *args, **kwargs: range(2, 9))
    def test_nova_pinning_base(self):
        with mock.patch('hotsos.core.plugins.openstack.NovaCPUPinning.'
                        'vcpu_pin_set', [0, 1, 2]):
            inst = openstack_core.NovaCPUPinning()
            self.assertEqual(inst.cpu_dedicated_set_name, 'vcpu_pin_set')

        inst = openstack_core.NovaCPUPinning()
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
        with mock.patch('hotsos.core.plugins.openstack.NovaCPUPinning.'
                        'cpu_dedicated_set', [0, 1, 4]):
            self.assertEqual(inst.nova_pinning_from_multi_numa_nodes, True)


class TestOpenstackAgentEventChecks(TestOpenstackBase):

    def test_process_rpc_loop_results(self):
        expected = {'rpc-loop': {
                        'stats': {
                            'avg': 0.0,
                            'max': 0.02,
                            'min': 0.0,
                            'samples': 2500,
                            'stdev': 0.0},
                        'top': {
                            '2100': {
                                'duration': 0.01,
                                'end': '2022-02-10 00:00:19.864000',
                                'start': '2022-02-10 00:00:19.854000'},
                            '2101': {
                                'duration': 0.01,
                                'end': '2022-02-10 00:00:21.867000',
                                'start': '2022-02-10 00:00:21.856000'},
                            '3152': {
                                'duration': 0.02,
                                'end': '2022-02-10 00:35:24.916000',
                                'start': '2022-02-10 00:35:24.896000'},
                            '3302': {
                                'duration': 0.02,
                                'end': '2022-02-10 00:40:25.068000',
                                'start': '2022-02-10 00:40:25.051000'},
                            '3693': {
                                'duration': 0.02,
                                'end': '2022-02-10 00:53:27.452000',
                                'start': '2022-02-10 00:53:27.434000'}}}}

        section_key = "neutron-ovs-agent"
        inst = agent_event_checks.NeutronAgentEventChecks(
                                                      searchobj=FileSearcher())
        inst.run_checks()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual.get(section_key), expected)

    def test_get_router_event_stats(self):
        expected = {'router-spawn-events': {
                        'stats': {
                            'avg': 578.02,
                            'max': 578.02,
                            'min': 578.02,
                            'samples': 1,
                            'stdev': 0.0},
                        'top': {
                            '984c22fd-64b3-4fa1-8ddd-87090f401ce5': {
                                'duration': 578.02,
                                'end': '2022-02-10 '
                                       '16:19:00.697000',
                                'start': '2022-02-10 '
                                         '16:09:22.679000'}}},
                    'router-updates': {
                        'stats': {
                            'avg': 28.29,
                            'max': 63.39,
                            'min': 12.96,
                            'samples': 10,
                            'stdev': 16.18},
                        'top': {
                            '964fd5e1-430e-4102-91a4-a0f2930f89b6': {
                                'duration': 22.37,
                                'end': '2022-02-10 16:14:07.813000',
                                'router':
                                    '984c22fd-64b3-4fa1-8ddd-87090f401ce5',
                                'start': '2022-02-10 16:13:45.442000'},
                            '96a22135-d383-4546-a385-cb683166c7d4': {
                                'duration': 33.41,
                                'end': '2022-02-10 16:10:35.710000',
                                'router':
                                    '984c22fd-64b3-4fa1-8ddd-87090f401ce5',
                                'start': '2022-02-10 16:10:02.303000'},
                            '97310a6f-5261-45d2-9e3b-1dcfeb534886': {
                                'duration': 63.39,
                                'end': '2022-02-10 16:10:02.302000',
                                'router':
                                    '984c22fd-64b3-4fa1-8ddd-87090f401ce5',
                                'start': '2022-02-10 16:08:58.916000'},
                            'b259b6d5-5ef3-4ed6-964d-a7f648a0b1f4': {
                                'duration': 31.44,
                                'end': '2022-02-10 16:13:45.440000',
                                'router':
                                    '984c22fd-64b3-4fa1-8ddd-87090f401ce5',
                                'start': '2022-02-10 16:13:13.997000'},
                            'b7eb99ad-b5d3-4e82-9ce8-47c66f014b77': {
                                'duration': 51.71,
                                'end': '2022-02-10 16:11:27.417000',
                                'router':
                                    '984c22fd-64b3-4fa1-8ddd-87090f401ce5',
                                'start': '2022-02-10 16:10:35.711000'}}}}

        section_key = "neutron-l3-agent"
        inst = agent_event_checks.NeutronAgentEventChecks(
                                                      searchobj=FileSearcher())
        inst.run_checks()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual.get(section_key), expected)

    def test_run_octavia_checks(self):
        with tempfile.TemporaryDirectory() as dtmp:
            setup_config(DATA_ROOT=dtmp)
            logfile = os.path.join(dtmp, ('var/log/octavia/'
                                          'octavia-health-manager.log'))
            os.makedirs(os.path.dirname(logfile))
            with open(logfile, 'w') as fd:
                fd.write(EVENT_OCTAVIA_CHECKS)

            expected = {'amp-missed-heartbeats': {
                         '2021-06-01': {
                          '3604bf2a-ee51-4135-97e2-ec08ed9321db': 1,
                          }},
                        'lb-failovers': {
                         'auto': {
                          '2021-03-09': {
                              '7a3b90ed-020e-48f0-ad6f-b28443fa2277': 1,
                              '98aefcff-60e5-4087-8ca6-5087ae970440': 1,
                              '9cd90142-5501-4362-93ef-1ad219baf45a': 1,
                              'e9cb98af-9c21-4cf6-9661-709179ce5733': 1,
                            }
                          }
                         }
                        }
            for section_key in ["octavia-worker", "octavia-health-manager"]:
                sobj = FileSearcher()
                inst = agent_event_checks.OctaviaAgentEventChecks(
                                                                searchobj=sobj)
                inst.run_checks()
                actual = self.part_output_to_actual(inst.output)
                self.assertEqual(actual["octavia"].get(section_key),
                                 expected.get(section_key))

    def test_run_apache_checks(self):
        with tempfile.TemporaryDirectory() as dtmp:
            setup_config(DATA_ROOT=dtmp)
            logfile = os.path.join(dtmp, 'var/log/apache2/error.log')
            os.makedirs(os.path.dirname(logfile))
            with open(logfile, 'w') as fd:
                fd.write(EVENT_APACHE_CONN_REFUSED_LOG)

            expected = {'connection-refused': {
                            '2021-10-26': {'127.0.0.1:8981': 3}}}
            for section_key in ['connection-refused']:
                sobj = FileSearcher()
                inst = agent_event_checks.ApacheEventChecks(searchobj=sobj)
                inst.run_checks()
                actual = self.part_output_to_actual(inst.output)
                self.assertEqual(actual['apache'].get(section_key),
                                 expected.get(section_key))

    def test_run_nova_checks(self):
        with tempfile.TemporaryDirectory() as dtmp:
            setup_config(DATA_ROOT=dtmp)
            logfile = os.path.join(dtmp, 'var/log/nova/nova-compute.log')
            os.makedirs(os.path.dirname(logfile))
            with open(logfile, 'w') as fd:
                fd.write(EVENT_PCIDEVNOTFOUND_LOG)

            expected = {'PciDeviceNotFoundById': {
                            '2021-09-17': {'0000:3b:0f.7': 1,
                                           '0000:3b:10.0': 1}}}
            sobj = FileSearcher()
            inst = agent_event_checks.NovaAgentEventChecks(searchobj=sobj)
            inst.run_checks()
            actual = self.part_output_to_actual(inst.output)
            self.assertEqual(actual["nova"], expected)

    def test_run_neutron_l3ha_checks(self):
        expected = {'keepalived': {
                     'transitions': {
                      '984c22fd-64b3-4fa1-8ddd-87090f401ce5': {
                          '2022-02-10': 1}}}}
        sobj = FileSearcher()
        inst = agent_event_checks.NeutronL3HAEventChecks(searchobj=sobj)
        inst.run_checks()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual["neutron-l3ha"], expected)

    @mock.patch.object(agent_event_checks, "VRRP_TRANSITION_WARN_THRESHOLD", 0)
    def test_run_neutron_l3ha_checks_w_issue(self):
        setup_config(USE_ALL_LOGS=False)
        expected = {'keepalived': {
                     'transitions': {
                      '984c22fd-64b3-4fa1-8ddd-87090f401ce5': {
                       '2022-02-10': 1}}}}
        sobj = FileSearcher()
        inst = agent_event_checks.NeutronL3HAEventChecks(searchobj=sobj)
        inst.run_checks()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual["neutron-l3ha"], expected)
        issues = list(IssuesStore().load().values())[0]
        msg = ('1 router(s) have had more than 0 vrrp transitions (max=1) in '
               'the last 24 hours.')
        self.assertEqual([issue['desc'] for issue in issues], [msg])


class TestOpenstackAgentExceptions(TestOpenstackBase):

    def test_get_agent_exceptions(self):
        neutron_expected = {
            'neutron-openvswitch-agent': {
                'oslo_messaging.exceptions.MessagingTimeout': {
                    '2022-02-04': 88,
                    '2022-02-09': 9
                    }},
            'neutron-dhcp-agent': {
                'oslo_messaging.exceptions.MessagingTimeout': {
                    '2022-02-04': 126,
                    '2022-02-09': 18
                    }},
            'neutron-l3-agent': {
                'oslo_messaging.exceptions.MessagingTimeout': {
                    '2022-02-04': 82,
                    '2022-02-09': 9
                    }},
            'neutron-metadata-agent': {
                'oslo_messaging.exceptions.MessagingTimeout': {
                    '2022-02-04': 48,
                    '2022-02-09': 14}},
            }

        nova_expected = {
            'nova-compute': {
                'oslo_messaging.exceptions.MessagingTimeout': {
                    '2022-02-04': 123,
                    '2022-02-09': 3,
                    },
                'nova.exception.ResourceProviderRetrievalFailed': {
                    '2022-02-04': 6
                    },
                'nova.exception.ResourceProviderAllocationRetrievalFailed': {
                    '2022-02-04': 2
                    }},
            'nova-api-metadata': {
                'oslo_messaging.exceptions.MessagingTimeout': {
                    '2022-02-04': 110,
                    '2022-02-09': 56}}}

        expected = {"nova": nova_expected, "neutron": neutron_expected}
        inst = agent_exceptions.AgentExceptionChecks()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual['agent-exceptions'], expected)


class TestOpenstackScenarioChecks(TestOpenstackBase):

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('neutron/bugs.yaml'))
    def test_1929832(self):
        with tempfile.TemporaryDirectory() as dtmp:
            setup_config(DATA_ROOT=dtmp)
            logfile = os.path.join(dtmp,
                                   'var/log/neutron/neutron-l3-agent.log')
            os.makedirs(os.path.dirname(logfile))
            with open(logfile, 'w') as fd:
                fd.write(LP_1929832)

            YScenarioChecker()()
            expected = {'bugs-detected':
                        [{'id': 'https://bugs.launchpad.net/bugs/1929832',
                          'desc': ('Known neutron l3-agent bug identified '
                                   'that impacts deletion of neutron '
                                   'routers.'),
                          'origin': 'openstack.01part'}]}
            self.assertEqual(IssuesManager().load_bugs(), expected)

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('neutron/bugs.yaml'))
    def test_1896506(self):
        with tempfile.TemporaryDirectory() as dtmp:
            setup_config(DATA_ROOT=dtmp)
            logfile = os.path.join(dtmp, 'var/log/syslog')
            os.makedirs(os.path.dirname(logfile))
            with open(logfile, 'w') as fd:
                fd.write(LP_1896506)

            YScenarioChecker()()
            expected = {'bugs-detected':
                        [{'id': 'https://bugs.launchpad.net/bugs/1896506',
                          'desc': ('Known neutron l3-agent bug identified '
                                   'that critically impacts keepalived.'),
                          'origin': 'openstack.01part'}]}
            self.assertEqual(IssuesManager().load_bugs(), expected)

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('neutron/bugs.yaml'))
    def test_1928031(self):
        with tempfile.TemporaryDirectory() as dtmp:
            setup_config(DATA_ROOT=dtmp)
            logfile = os.path.join(
                        dtmp, 'var/log/neutron/neutron-ovn-metadata-agent.log')
            os.makedirs(os.path.dirname(logfile))
            with open(logfile, 'w') as fd:
                fd.write(LP_1928031)

            YScenarioChecker()()
            expected = {'bugs-detected':
                        [{'id': 'https://bugs.launchpad.net/bugs/1928031',
                          'desc': ('Known neutron-ovn bug identified that '
                                   'impacts OVN sbdb connections.'),
                          'origin': 'openstack.01part'}]}
            self.assertEqual(IssuesManager().load_bugs(), expected)

    @mock.patch('hotsos.core.host_helpers.packaging.CLIHelper')
    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('neutron/bugs.yaml'))
    def test_1927868(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.dpkg_l.return_value = \
            ["ii neutron-common 2:16.4.0-0ubuntu2 all"]

        YScenarioChecker()()
        expected = {'bugs-detected':
                    [{'id': 'https://bugs.launchpad.net/bugs/1927868',
                      'desc': ("Installed package 'neutron-common' with "
                               "version 2:16.4.0-0ubuntu2 has a known "
                               "critical bug. If this environment is "
                               "using Neutron ML2 OVS (i.e. not OVN) it "
                               "should be upgraded asap."),
                      'origin': 'openstack.01part'}]}
        self.assertEqual(IssuesManager().load_bugs(), expected)

    @mock.patch('hotsos.core.host_helpers.packaging.CLIHelper')
    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('octavia/bugs.yaml'))
    def test_2008099(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.dpkg_l.return_value = \
            ["ii octavia-common 6.1.0-0ubuntu1~cloud0 all"]

        with tempfile.TemporaryDirectory() as dtmp:
            setup_config(DATA_ROOT=dtmp)
            logfile = os.path.join(
                        dtmp, 'var/log/octavia/octavia-worker.log')
            os.makedirs(os.path.dirname(logfile))
            with open(logfile, 'w') as fd:
                fd.write(LP_2008099)

            YScenarioChecker()()
            expected = {'bugs-detected':
                        [{'id':
                          'https://storyboard.openstack.org/#!/story/2008099',
                          'desc': ('A known octavia bug has been identified. '
                                   'Due to this bug, LB failover '
                                   'fails when session persistence is set on '
                                   'a LB pool. The fix is available in '
                                   'latest octavia packages in UCA ussuri '
                                   'and above.'),
                          'origin': 'openstack.01part'}]}
            self.assertEqual(IssuesManager().load_bugs(), expected)

    @mock.patch('hotsos.core.issues.IssuesManager.add')
    def test_scenarios_none(self, mock_add_issue):
        YScenarioChecker()()
        self.assertFalse(mock_add_issue.called)

    @mock.patch('hotsos.core.plugins.kernel.CPU.cpufreq_scaling_governor_all',
                'powersave')
    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('system_cpufreq_mode.yaml'))
    def test_scenarios_cpufreq(self):
        YScenarioChecker()()
        msg = ('This node is used as an Openstack hypervisor but is not using '
               'cpufreq scaling_governor in "performance" mode '
               '(actual=powersave). This is not recommended and can result '
               'in performance degradation. To fix this you can install '
               'cpufrequtils, set "GOVERNOR=performance" in '
               '/etc/default/cpufrequtils and run systemctl restart '
               'cpufrequtils. You will also need to stop and disable the '
               'ondemand systemd service in order for changes to persist.')
        issues = list(IssuesStore().load().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])

    @mock.patch('hotsos.core.plugins.system.NUMAInfo.nodes',
                {0: [1, 3, 5], 1: [0, 2, 4]})
    @mock.patch('hotsos.core.plugins.openstack.OpenstackConfig')
    @mock.patch('hotsos.core.plugins.openstack.OpenstackChecksBase.'
                'release_name', 'train')
    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('nova/cpu_pinning.yaml'))
    def test_scenario_pinning_invalid_config(self, mock_config):
        config = {}

        def fake_get(key, **_kwargs):
            return config.get(key)

        mock_config.return_value = mock.MagicMock()
        mock_config.return_value.get.side_effect = fake_get

        config = {'vcpu_pin_set': [1, 2, 3],
                  'cpu_dedicated_set': [1, 2, 3]}
        YScenarioChecker()()
        msg1 = ("Nova config options 'vcpu_pin_set' and "
                "'cpu_dedicated_set' are both set/configured which is not "
                "allowed for >= Train.")
        msg2 = ("Nova config option 'vcpu_pin_set' is configured with "
                "cores from more than one numa node. This can have "
                "performance implications and should be checked.")
        issues = list(IssuesStore().load().values())[0]
        self.assertEqual(sorted([issue['desc'] for issue in issues]),
                         sorted([msg1, msg2]))

        os.unlink(IssuesStore().store_path)
        config = {'cpu_dedicated_set': [1, 2, 3]}
        YScenarioChecker()()
        msg = ("Nova config option 'cpu_dedicated_set' is configured with "
               "cores from more than one numa node. This can have "
               "performance implications and should be checked.")
        issues = list(IssuesStore().load().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])

        os.unlink(IssuesStore().store_path)
        config = {'vcpu_pin_set': [1, 2, 3]}
        YScenarioChecker()()
        msg1 = ("Nova config option 'vcpu_pin_set' is configured with "
                "cores from more than one numa node. This can have "
                "performance implications and should be checked.")
        msg2 = ("Nova config option 'vcpu_pin_set' is configured yet it "
                "is deprecated as of the Train release and may be "
                "ignored. Recommendation is to switch to using "
                "cpu_dedicated_set and/or cpu_shared_set (see upstream "
                "docs).")
        issues = list(IssuesStore().load().values())[0]
        self.assertEqual(sorted([issue['desc'] for issue in issues]),
                         sorted([msg1, msg2]))

    @mock.patch('hotsos.core.plugins.openstack.OSTProject.installed', True)
    @mock.patch('hotsos.core.host_helpers.systemd.CLIHelper')
    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('systemd_masked_services.yaml'))
    def test_scenario_masked_services(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        masked_services = OCTAVIA_UNIT_FILES_APACHE_MASKED + \
            NEUTRON_UNIT_FILES_MASKED
        mock_helper.return_value.systemctl_list_unit_files.return_value = \
            masked_services.splitlines(keepends=True)
        YScenarioChecker()()
        msg = ('The following Openstack systemd services are masked: '
               'neutron-dhcp-agent, neutron-metering-agent, '
               'neutron-metadata-agent, apache2, neutron-openvswitch-agent, '
               'neutron-l3-agent. Please ensure that this is intended '
               'otherwise these services may be unavailable.')
        issues = list(IssuesStore().load().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])

    @mock.patch('hotsos.core.plugins.openstack.host_helpers.CLIHelper')
    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('neutron_ovs_cleanup.yaml'))
    def test_neutron_ovs_cleanup(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.journalctl.return_value = \
            JOURNALCTL_OVS_CLEANUP_BAD.splitlines(keepends=True)
        YScenarioChecker()()
        msg = ('The neutron-ovs-cleanup systemd service has been manually run '
               'on this host. This is not recommended and can have unintended '
               'side-effects.')
        issues = list(IssuesStore().load().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('nova/config_checks.yaml'))
    @mock.patch('hotsos.core.host_helpers.packaging.CLIHelper')
    def test_nova_config_checks(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.dpkg_l.return_value = \
            ["ii  openvswitch-switch-dpdk 2.13.3-0ubuntu0.20.04.2 amd64"]
        # no need to mock the config since the fact it doesnt exist will
        # trigger the alert.
        YScenarioChecker()()
        issues = list(IssuesStore().load().values())[0]
        msg = ('DPDK is enabled but rx_queue_size/tx_queue_size set '
               'incorrectly in nova.conf (expect both to be >= 1024).')
        self.assertEqual([issue['desc'] for issue in issues], [msg])

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('pkgs_from_mixed_releases_found.yaml'))
    @mock.patch('hotsos.core.host_helpers.packaging.CLIHelper')
    def test_pkgs_from_mixed_releases_found(self, mock_cli):
        mock_cli.return_value = mock.MagicMock()
        mock_cli.return_value.dpkg_l.return_value = \
            ["{}\n".format(line) for line in DPKG_L_MIX_RELS.split('\n')]

        YScenarioChecker()()
        msg = ("Openstack packages from a more than one release identified: "
               "ussuri, victoria.")
        issues = list(IssuesStore().load().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('openstack_apache2_certificates.yaml'))
    @mock.patch('hotsos.core.host_helpers.ssl.datetime')
    def test_apache2_ssl_certificate_expiring(self, mock_datetime):
        mocked_today = datetime(2023, 4, 12)
        mock_datetime.return_value = mock.MagicMock()
        mock_datetime.today.return_value = mocked_today
        with tempfile.TemporaryDirectory() as dtmp:
            setup_config(DATA_ROOT=dtmp)
            conf = "etc/apache2/sites-enabled/openstack_https_frontend.conf"
            certificate_path = "etc/apache2/ssl/keystone/cert_10.5.100.2"
            full_certificate_path = os.path.join(dtmp, certificate_path)
            os.makedirs(os.path.dirname(os.path.join(dtmp, conf)))
            os.makedirs(os.path.dirname(full_certificate_path))
            with open(os.path.join(dtmp, conf), 'w') as fd:
                fd.write(APACHE2_SSL_CONF)
            with open(os.path.join(dtmp, certificate_path), 'w') as fd:
                fd.write(CERTIFICATE_FILE)
            base = openstack_core.OpenstackBase()
            YScenarioChecker()()
            msg = ("The following certificates will expire in less than {0} "
                   "days: {1}".format(base.certificate_expire_days,
                                      full_certificate_path))
            issues = list(IssuesStore().load().values())[0]
            self.assertEqual([issue['desc'] for issue in issues], [msg])

    @mock.patch(
        'hotsos.core.host_helpers.systemd.ServiceChecksBase.services', {
            'neutron-openvswitch-agent':
            SystemdService('neutron-openvswitch-agent', 'enabled'),
            'openvswitch-switch':
            SystemdService('openvswitch-switch', 'enabled')
        })
    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('neutron/bugs.yaml'))
    @mock.patch('hotsos.core.host_helpers.systemd.CLIHelper')
    def test_1794991(self, mock_cli):
        mock_cli.return_value = mock.MagicMock()
        mock_cli.return_value.journalctl.side_effect = [
            JOURNALCTL_NEUTRON_OPENVSWITCH_AGENT.splitlines(keepends=True),
            JOURNALCTL_OPENVSWITCH_SWITCH.splitlines(keepends=True)
        ]

        YScenarioChecker()()
        msg = ('This host may be affected by a bug in Openstack Neutron ML2'
               ' whereby if the neutron-openvswitch-agent service is not '
               'restarted after a restart of openvswitch-switch this can '
               'lead to inconsistent l2pop flows. If you think this node '
               'is impacted you can fix this with a restart of '
               'neutron-openvswitch-agent.')
        expected = {'bugs-detected':
                    [{'id': 'https://bugs.launchpad.net/bugs/1794991',
                      'desc': msg,
                      'origin': 'openstack.01part'}]}
        self.assertEqual(IssuesManager().load_bugs(), expected)


class TestOpenstackApache2SSL(TestOpenstackBase):

    def test_ssl_enabled(self):
        with tempfile.TemporaryDirectory() as dtmp:
            conf = "etc/apache2/sites-enabled/openstack_https_frontend.conf"
            os.makedirs(os.path.dirname(os.path.join(dtmp, conf)))
            with open(os.path.join(dtmp, conf), 'w') as fd:
                fd.write(APACHE2_SSL_CONF)
            setup_config(DATA_ROOT=dtmp)
            base = openstack_core.OpenstackBase()
            self.assertTrue(base.ssl_enabled)

    def test_ssl_disabled(self):
        base = openstack_core.OpenstackBase()
        self.assertFalse(base.ssl_enabled)

    def test_ssl_certificate_list(self):
        with tempfile.TemporaryDirectory() as dtmp:
            setup_config(DATA_ROOT=dtmp)
            conf = "etc/apache2/sites-enabled/openstack_https_frontend.conf"
            certificate_path = "etc/apache2/ssl/keystone/cert_10.5.100.2"
            os.makedirs(os.path.dirname(os.path.join(dtmp, conf)))
            os.makedirs(os.path.dirname(os.path.join(dtmp, certificate_path)))
            with open(os.path.join(dtmp, conf), 'w') as fd:
                fd.write(APACHE2_SSL_CONF)
            with open(os.path.join(dtmp, certificate_path), 'w') as fd:
                fd.write(CERTIFICATE_FILE)
            base = openstack_core.OpenstackBase()
            self.assertTrue(len(base.apache2_certificates_list), 1)

    @mock.patch('hotsos.core.host_helpers.ssl.datetime')
    def test_ssl_expiration_false(self, mock_datetime):
        mocked_today = datetime(2022, 4, 12)
        mock_datetime.return_value = mock.MagicMock()
        mock_datetime.today.return_value = mocked_today
        with tempfile.TemporaryDirectory() as dtmp:
            setup_config(DATA_ROOT=dtmp)
            conf = "etc/apache2/sites-enabled/openstack_https_frontend.conf"
            certificate_path = "etc/apache2/ssl/keystone/cert_10.5.100.2"
            os.makedirs(os.path.dirname(os.path.join(dtmp, conf)))
            os.makedirs(os.path.dirname(os.path.join(dtmp, certificate_path)))
            with open(os.path.join(dtmp, conf), 'w') as fd:
                fd.write(APACHE2_SSL_CONF)
            with open(os.path.join(dtmp, certificate_path), 'w') as cfd:
                cfd.write(CERTIFICATE_FILE)
            base = openstack_core.OpenstackBase()
            self.assertEqual(len(base.apache2_certificates_expiring), 0)

    @mock.patch('hotsos.core.host_helpers.ssl.datetime')
    def test_ssl_expiration_true(self, mock_datetime):
        mocked_today = datetime(2023, 4, 12)
        mock_datetime.return_value = mock.MagicMock()
        mock_datetime.today.return_value = mocked_today
        with tempfile.TemporaryDirectory() as dtmp:
            setup_config(DATA_ROOT=dtmp)
            conf = "etc/apache2/sites-enabled/openstack_https_frontend.conf"
            certificate_path = "etc/apache2/ssl/keystone/cert_10.5.100.2"
            os.makedirs(os.path.dirname(os.path.join(dtmp, conf)))
            os.makedirs(os.path.dirname(os.path.join(dtmp, certificate_path)))
            with open(os.path.join(dtmp, conf), 'w') as fd:
                fd.write(APACHE2_SSL_CONF)
            with open(os.path.join(dtmp, certificate_path), 'w') as cfd:
                cfd.write(CERTIFICATE_FILE)
            base = openstack_core.OpenstackBase()
            self.assertTrue(len(base.apache2_certificates_expiring), 1)
