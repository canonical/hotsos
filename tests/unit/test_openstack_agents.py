import os
from unittest import mock

from hotsos.core.config import HotSOSConfig
from hotsos.core.issues.utils import IssuesStore
from hotsos.plugin_extensions.openstack import (
    agent,
)
from hotsos.core.ycheck.common import GlobalSearcher
from tests.unit.test_openstack import TestOpenstackBase

from . import utils

EVENT_PCIDEVNOTFOUND_LOG = r"""
2022-09-17 13:49:47.257 3060998 WARNING nova.pci.utils [req-f6448047-9a0f-453b-9189-079dd00ab3a3 - - - - -] No net device was found for VF 0000:3b:10.0: nova.exception.PciDeviceNotFoundById: PCI device 0000:3b:10.0 not found
2022-09-17 13:49:47.609 3060998 WARNING nova.pci.utils [req-f6448047-9a0f-453b-9189-079dd00ab3a3 - - - - -] No net device was found for VF 0000:3b:0f.7: nova.exception.PciDeviceNotFoundById: PCI device 0000:3b:0f.7 not found
"""  # noqa

EVENT_APACHE_CONN_REFUSED_LOG = r"""
[Tue Oct 26 17:27:20.477742 2021] [proxy:error] [pid 29484:tid 140230740928256] (111)Connection refused: AH00957: HTTP: attempt to connect to 127.0.0.1:8981 (localhost) failed
[Tue Oct 26 17:29:22.338485 2021] [proxy:error] [pid 29485:tid 140231076472576] (111)Connection refused: AH00957: HTTP: attempt to connect to 127.0.0.1:8981 (localhost) failed
[Tue Oct 26 17:31:18.143966 2021] [proxy:error] [pid 29485:tid 140231219083008] (111)Connection refused: AH00957: HTTP: attempt to connect to 127.0.0.1:8981 (localhost) failed
"""  # noqa

EVENT_OCTAVIA_CHECKS = r"""
2022-03-09 14:53:04.467 9684 INFO octavia.controller.worker.v1.flows.amphora_flows [-] Performing failover for amphora: {'id': 'ac9849a2-f81e-4578-aedf-3637420c97ff', 'load_balancer_id': '7a3b90ed-020e-48f0-ad6f-b28443fa2277', 'lb_network_ip': 'fc00:1f77:9de0:cd56:f816:3eff:fe6c:2963', 'compute_id': 'af04050e-b845-4bca-9e61-ded03039d2c6', 'role': 'master_or_backup'}
2022-03-09 17:44:37.379 9684 INFO octavia.controller.worker.v1.flows.amphora_flows [-] Performing failover for amphora: {'id': '0cd68e26-abb7-4e6b-8272-5ccf017b6de7', 'load_balancer_id': '9cd90142-5501-4362-93ef-1ad219baf45a', 'lb_network_ip': 'fc00:1f77:9de0:cd56:f816:3eff:feae:514c', 'compute_id': '314e4b2f-9c64-41c9-b337-7d0229127d48', 'role': 'master_or_backup'}
2022-03-09 18:19:10.369 9684 INFO octavia.controller.worker.v1.flows.amphora_flows [-] Performing failover for amphora: {'id': 'ddaf13ec-858f-42d1-bdc8-d8b529c7c524', 'load_balancer_id': 'e9cb98af-9c21-4cf6-9661-709179ce5733', 'lb_network_ip': 'fc00:1f77:9de0:cd56:f816:3eff:fe2f:9d58', 'compute_id': 'c71c5eca-c862-49dd-921c-273e51dfb574', 'role': 'master_or_backup'}
2022-03-09 20:01:46.376 9684 INFO octavia.controller.worker.v1.flows.amphora_flows [-] Performing failover for amphora: {'id': 'bbf6107b-86b5-45f5-ace1-e077871860ac', 'load_balancer_id': '98aefcff-60e5-4087-8ca6-5087ae970440', 'lb_network_ip': 'fc00:1f77:9de0:cd56:f816:3eff:fe5b:4afb', 'compute_id': '54061176-61c8-4915-b896-e026c3eeb60f', 'role': 'master_or_backup'}

2022-06-01 23:25:39.223 43076 WARNING octavia.controller.healthmanager.health_drivers.update_db [-] Amphora 3604bf2a-ee51-4135-97e2-ec08ed9321db health message was processed too slowly: 10.550589084625244s! The system may be overloaded or otherwise malfunctioning. This heartbeat has been ignored and no update was made to the amphora health entry. THIS IS NOT GOOD.
"""  # noqa

AA_MSGS = """
Mar  3 22:57:11 compute4 kernel: [1381807.338196] audit: type=1400 audit(1646348231.139:38839): apparmor="DENIED" operation="open" profile="/usr/bin/neutron-l3-agent" name="/proc/3178525/fd/" pid=3178525 comm="/usr/bin/python" requested_mask="r" denied_mask="r" fsuid=118 ouid=118
Mar  3 22:57:11 compute4 kernel: [1381807.714508] audit: type=1400 audit(1646348231.515:38840): apparmor="DENIED" operation="open" profile="/usr/bin/neutron-dhcp-agent" name="/proc/3178712/fd/" pid=3178712 comm="/usr/bin/python" requested_mask="r" denied_mask="r" fsuid=118 ouid=118
Mar  3 22:57:11 compute4 kernel: [1381807.843795] audit: type=1400 audit(1646348231.643:38841): apparmor="DENIED" operation="open" profile="/usr/bin/neutron-openvswitch-agent" name="/proc/3178790/fd/" pid=3178790 comm="/usr/bin/python" requested_mask="r" denied_mask="r" fsuid=118 ouid=118
Mar  3 22:57:22 compute4 kernel: [1381818.448855] audit: type=1400 audit(1646348242.252:38857): apparmor="DENIED" operation="open" profile="/usr/bin/neutron-openvswitch-agent" name="/proc/3181986/fd/" pid=3181986 comm="/usr/bin/python" requested_mask="r" denied_mask="r" fsuid=118 ouid=118
Mar  3 22:57:23 compute4 kernel: [1381819.715713] audit: type=1400 audit(1646348243.520:38859): apparmor="DENIED" operation="open" profile="/usr/bin/neutron-dhcp-agent" name="/proc/3182175/fd/" pid=3182175 comm="/usr/bin/python" requested_mask="r" denied_mask="r" fsuid=118 ouid=118
Mar  3 22:57:24 compute4 kernel: [1381820.269384] audit: type=1400 audit(1646348244.072:38860): apparmor="DENIED" operation="open" profile="/usr/bin/neutron-openvswitch-agent" name="/proc/3182207/fd/" pid=3182207 comm="/usr/bin/python" requested_mask="r" denied_mask="r" fsuid=118 ouid=118
Mar  3 22:57:24 compute4 kernel: [1381820.499397] audit: type=1400 audit(1646348244.300:38861): apparmor="DENIED" operation="open" profile="/usr/bin/neutron-openvswitch-agent" name="/proc/3182352/fd/" pid=3182352 comm="/usr/bin/python" requested_mask="r" denied_mask="r" fsuid=118 ouid=118
"""  # noqa


NEUTRON_HTTP = """
2022-05-11 16:19:55.704 27285 INFO neutron.wsgi [req-4e357374-8d66-4a11-b13f-b073bae102da 0122338208ab123efa5f69ba30a470c41561d7d3438f8fbb46d09ba32211d99f 42774781002541059577441343bef15d - c13f73c6835d43b1b7572644e5b3ae72 c13f73c6835d43b1b7572644e5b3ae72] 10.55.12.152,127.0.0.1 "POST /v2.0/floatingips HTTP/1.1" status: 201  len: 1022 time: 8.7183912
2022-05-11 16:19:55.920 27285 INFO neutron.wsgi [req-fe7e1062-1d9e-4bd8-85be-18e592688ced 0122338208ab123efa5f69ba30a470c41561d7d3438f8fbb46d09ba32211d99f 42774781002541059577441343bef15d - c13f73c6835d43b1b7572644e5b3ae72 c13f73c6835d43b1b7572644e5b3ae72] 10.55.12.152,127.0.0.1 "POST /v2.0/floatingips HTTP/1.1" status: 201  len: 1022 time: 8.3476303
2022-05-11 16:19:56.119 27285 INFO neutron.wsgi [req-a621d456-8ce7-4bf4-b4b6-6fe8f2a4fb94 0122338208ab123efa5f69ba30a470c41561d7d3438f8fbb46d09ba32211d99f 42774781002541059577441343bef15d - c13f73c6835d43b1b7572644e5b3ae72 c13f73c6835d43b1b7572644e5b3ae72] 10.55.12.152,127.0.0.1 "POST /v2.0/floatingips HTTP/1.1" status: 201  len: 1021 time: 7.9349949
2022-05-11 16:19:58.795 27292 INFO neutron.wsgi [req-0b503592-92d9-4774-ac95-e6f8dd940fc5 0122338208ab123efa5f69ba30a470c41561d7d3438f8fbb46d09ba32211d99f 42774781002541059577441343bef15d - c13f73c6835d43b1b7572644e5b3ae72 c13f73c6835d43b1b7572644e5b3ae72] 10.55.12.152,127.0.0.1 "POST /v2.0/floatingips HTTP/1.1" status: 201  len: 1022 time: 4.8702903
2022-05-11 16:18:50.709 27285 INFO neutron.wsgi [req-074e20aa-4aa9-437a-a284-023954181cba 0122338208ab123efa5f69ba30a470c41561d7d3438f8fbb46d09ba32211d99f 42774781002541059577441343bef15d - c13f73c6835d43b1b7572644e5b3ae72 c13f73c6835d43b1b7572644e5b3ae72] 10.55.12.152,127.0.0.1 "DELETE /v2.0/security-group-rules/6b1be7e7-d467-4fcb-8694-430505b76e09 HTTP/1.1" status: 204  len: 173 time: 0.0725079
2022-05-11 16:18:50.784 27285 INFO neutron.wsgi [req-2f6a3185-c34c-4beb-aa5f-744a8f45edea 0122338208ab123efa5f69ba30a470c41561d7d3438f8fbb46d09ba32211d99f 42774781002541059577441343bef15d - c13f73c6835d43b1b7572644e5b3ae72 c13f73c6835d43b1b7572644e5b3ae72] 10.55.12.152,127.0.0.1 "DELETE /v2.0/security-group-rules/f38bc751-3870-4ded-b089-6200c8adcc2b HTTP/1.1" status: 204  len: 173 time: 0.0680902
2022-05-11 16:18:50.880 27285 INFO neutron.wsgi [req-a5126037-0914-4cab-bde5-c3bfa91000a7 0122338208ab123efa5f69ba30a470c41561d7d3438f8fbb46d09ba32211d99f 42774781002541059577441343bef15d - c13f73c6835d43b1b7572644e5b3ae72 c13f73c6835d43b1b7572644e5b3ae72] 10.55.12.152,127.0.0.1 "DELETE /v2.0/security-groups/3bb35887-ca9f-4eb5-b87f-51c787b3ad39 HTTP/1.1" status: 204  len: 173 time: 0.0903349
2022-05-11 16:18:56.660 27292 INFO neutron.wsgi [req-d3e7918d-4032-43f2-a09f-e6e42a42b7e0 0122338208ab123efa5f69ba30a470c41561d7d3438f8fbb46d09ba32211d99f 42774781002541059577441343bef15d - c13f73c6835d43b1b7572644e5b3ae72 c13f73c6835d43b1b7572644e5b3ae72] 10.55.12.152,127.0.0.1 "DELETE /v2.0/networks/595f1f1d-c55c-4943-9957-d7f6d8eabd96 HTTP/1.1" status: 204  len: 173 time: 1.9860468
2022-05-11 16:18:56.750 27285 INFO neutron.wsgi [req-354f29eb-f8ff-4ed7-9d68-f62e4d9d8e4a 0122338208ab123efa5f69ba30a470c41561d7d3438f8fbb46d09ba32211d99f 42774781002541059577441343bef15d - c13f73c6835d43b1b7572644e5b3ae72 c13f73c6835d43b1b7572644e5b3ae72] 10.55.12.152,127.0.0.1 "DELETE /v2.0/routers/14aa18e0-bd2d-407c-94ee-b3ddeb24a2f5 HTTP/1.1" status: 204  len: 173 time: 2.9382973
2022-05-11 16:20:12.770 27288 INFO neutron.wsgi [req-ce744853-29bc-470d-b364-7e350fb995af b09bc7f6ea1a491ebefaef515aa41858 c80a5b62cfe6435ab44315de3d670b2f - 3ef3cedadd5a4331a11118211060834e 3ef3cedadd5a4331a11118211060834e] 10.55.12.152,127.0.0.1 "PUT /v2.0/ports/9f37b531-5e7c-46d7-ba59-3e5c806b7374 HTTP/1.1" status: 200  len: 1523 time: 1.4883997
2022-05-11 16:20:13.213 27285 INFO neutron.wsgi [req-2d760321-3668-43e0-89b8-ce355437ee62 b09bc7f6ea1a491ebefaef515aa41858 c80a5b62cfe6435ab44315de3d670b2f - 3ef3cedadd5a4331a11118211060834e 3ef3cedadd5a4331a11118211060834e] 10.55.12.152,127.0.0.1 "PUT /v2.0/ports/5b5fdb5a-1403-4ddf-9bb5-296a6f419408 HTTP/1.1" status: 200  len: 1523 time: 2.4935267
2022-05-11 16:20:15.852 27292 INFO neutron.wsgi [req-524ef875-14f7-4d0a-976e-75de19ddea22 b09bc7f6ea1a491ebefaef515aa41858 c80a5b62cfe6435ab44315de3d670b2f - 3ef3cedadd5a4331a11118211060834e 3ef3cedadd5a4331a11118211060834e] 10.55.12.152,127.0.0.1 "PUT /v2.0/ports/aec74f93-6844-4dd9-912d-8d652852a7a3 HTTP/1.1" status: 200  len: 1536 time: 2.0487440
2022-05-11 18:03:04.042 27285 INFO neutron.wsgi [req-cf288f23-c933-4852-a9f9-aece83c9059f b09bc7f6ea1a491ebefaef515aa41858 c80a5b62cfe6435ab44315de3d670b2f - 3ef3cedadd5a4331a11118211060834e 3ef3cedadd5a4331a11118211060834e] 10.55.12.152,127.0.0.1 "GET /v2.0/ports?device_id=e4f6196e-ac55-440b-94cb-9b2af98ac5bd HTTP/1.1" status: 200  len: 1589 time: 0.0551665
2022-05-11 18:03:04.079 27285 INFO neutron.wsgi [req-3817bf2e-b023-4f81-9223-bc75bb468a16 b09bc7f6ea1a491ebefaef515aa41858 c80a5b62cfe6435ab44315de3d670b2f - 3ef3cedadd5a4331a11118211060834e 3ef3cedadd5a4331a11118211060834e] 10.55.12.152,127.0.0.1 "GET /v2.0/security-groups?id=9146f70d-2882-4ddc-9d55-dd325ee3fb90&id=ab4ac2c0-93b9-4b9e-b241-4c121738a26a&id=513a6430-7941-4518-bc1b-04174895a375&id=2643b274-78f1-4a74-a551-ad8676e423be&fields=id&fields=name HTTP/1.1" status: 200  len: 578 time: 0.0304003
"""  # noqa

NC_LOGS = """
2022-02-04 10:58:39.233 396832 WARNING nova.servicegroup.drivers.db [-] Lost connection to nova-conductor for reporting service status.: oslo_messaging.exceptions.MessagingTimeout: Timed out waiting for a reply to message ID 38469b4f29c143f8933e4e55ac13f431
2022-02-09 22:59:47.029 53085 WARNING nova.servicegroup.drivers.db [-] Lost connection to nova-conductor for reporting service status.: oslo_messaging.exceptions.MessagingTimeout: Timed out waiting for a reply to message ID 8ff3787c74564ecf893faf92bdcf2305
2022-02-09 23:00:12.155 53085 ERROR oslo_service.periodic_task [req-4215634a-130e-4473-b9a3-045c25aa4e96 - - - - -] Error during ComputeManager.update_available_resource: oslo_messaging.exceptions.MessagingTimeout: Timed out waiting for a reply to message ID 900f3db832cb4c5b95f21a421d5dcffa
2022-02-09 23:00:12.155 53085 ERROR oslo_service.periodic_task oslo_messaging.exceptions.MessagingTimeout: Timed out waiting for a reply to message ID 900f3db832cb4c5b95f21a421d5dcffa
""" # noqa

OVSDBAPP_LEADER_CHANGING = """
2023-11-23 02:53:18.415 5567 INFO ovsdbapp.backend.ovs_idl.vlog [-] ssl:10.22.0.244:6641: clustered database server is not cluster leader; trying another server
2023-11-23 02:53:18.437 5547 INFO ovsdbapp.backend.ovs_idl.vlog [-] ssl:10.22.0.244:6641: clustered database server is not cluster leader; trying another server
2023-11-23 04:54:52.122 5620 INFO ovsdbapp.backend.ovs_idl.vlog [-] ssl:10.22.0.244:16642: clustered database server is not cluster leader; trying another server
2023-11-23 04:55:40.020 5620 INFO ovsdbapp.backend.ovs_idl.vlog [-] ssl:10.22.0.243:16642: clustered database server is not cluster leader; trying another server
2023-11-23 04:55:40.076 5620 INFO ovsdbapp.backend.ovs_idl.vlog [-] ssl:10.22.0.242:16642: clustered database server is not cluster leader; trying another server
""" # noqa

OVN_RESOURCE_VERSION_BUMP_EVENTS = """
2023-12-09 07:47:51.292 1380560 INFO neutron.db.ovn_revision_numbers_db [req-d714b598-190d-4c47-ad2d-b4e97352e2ce - - - - -] Successfully bumped revision number for resource d82ce545-ccdf-4784-9cc7-ba10f8051d1a (type: router_ports) to 19344
2023-12-09 07:47:51.567 1380560 INFO neutron.db.ovn_revision_numbers_db [req-d714b598-190d-4c47-ad2d-b4e97352e2ce - - - - -] Successfully bumped revision number for resource d82ce545-ccdf-4784-9cc7-ba10f8051d1a (type: ports) to 19343
2023-12-09 07:47:51.682 1380557 INFO neutron.db.ovn_revision_numbers_db [req-9d803205-fec7-459f-bb6b-9c5f2b446427 - - - - -] Successfully bumped revision number for resource 4dedf9dd-ff5e-4b71-bebb-9d168b83c0b8 (type: ports) to 31477
2023-12-09 07:47:51.859 1380559 INFO neutron.db.ovn_revision_numbers_db [req-19a5f512-8e5b-4530-912f-e812f82cb6db - - - - -] Successfully bumped revision number for resource ed43f1b0-c11c-46dc-9c1a-9654d450a010 (type: router_ports) to 53482
2023-12-09 07:47:52.150 1380559 INFO neutron.db.ovn_revision_numbers_db [req-19a5f512-8e5b-4530-912f-e812f82cb6db - - - - -] Successfully bumped revision number for resource ed43f1b0-c11c-46dc-9c1a-9654d450a010 (type: ports) to 53482
2023-12-09 07:47:52.371 1380557 INFO neutron.db.ovn_revision_numbers_db [req-9d803205-fec7-459f-bb6b-9c5f2b446427 - - - - -] Successfully bumped revision number for resource 4dedf9dd-ff5e-4b71-bebb-9d168b83c0b8 (type: router_ports) to 31477
""" # noqa

OVN_OVSDB_ABORTED_TRANSACTIONS = """
2023-12-12 22:55:09.584 3607986 INFO neutron.plugins.ml2.drivers.ovn.mech_driver.ovsdb.impl_idl_ovn [req-c0daac60-b52f-4fd8-8bb3-32ff982f4078 - - - - -] Transaction aborted. Reason: OVN revision number for 8c3bd483-f06e-479b-84d1-cee91b1969e4 (type: ports) is equal or higher than the given resource. Skipping update
2023-12-12 23:00:06.226 3607985 INFO neutron.plugins.ml2.drivers.ovn.mech_driver.ovsdb.impl_idl_ovn [req-5a3bbb53-2e72-483f-b921-ddf9fcc9032e - - - - -] Transaction aborted. Reason: OVN revision number for c3b33b44-2339-4193-ae15-678a8ca1008e (type: ports) is equal or higher than the given resource. Skipping update
2023-12-12 23:39:28.376 3607984 INFO neutron.plugins.ml2.drivers.ovn.mech_driver.ovsdb.impl_idl_ovn [req-ec21f612-a85f-4f7b-aef8-4cd81cc372b8 - - - - -] Transaction aborted. Reason: OVN revision number for 28db1807-5fdf-4e9e-9c19-8d3be7be299e (type: ports) is equal or higher than the given resource. Skipping update
2023-12-12 23:40:11.605 3607984 INFO neutron.plugins.ml2.drivers.ovn.mech_driver.ovsdb.impl_idl_ovn [req-ec21f612-a85f-4f7b-aef8-4cd81cc372b8 - - - - -] Transaction aborted. Reason: OVN revision number for lrp-28db1807-5fdf-4e9e-9c19-8d3be7be299e (type: router_ports) is equal or higher than the given resource. Skipping update
2023-12-12 23:45:05.716 3607984 INFO neutron.plugins.ml2.drivers.ovn.mech_driver.ovsdb.impl_idl_ovn [req-ec21f612-a85f-4f7b-aef8-4cd81cc372b8 - - - - -] Transaction aborted. Reason: OVN revision number for 28db1807-5fdf-4e9e-9c19-8d3be7be299e (type: ports) is equal or higher than the given resource. Skipping update
""" # noqa

# NOTE: first log line is intentionally old so that constraint filters it out.
NOVA_REST_API = """
127.0.0.1 - - [27/Dec/2021:00:00:10 +0000] "GET /v2.1/servers/detail?name=juju-.%2A HTTP/1.1" 200 40168 "-" "goose (0.1.0)"
127.0.0.1 - - [25/Dec/2024:00:00:15 +0000] "GET /v2.1/flavors/511b3962-e5fd-4f34-a342-adf51c388d4a/os-flavor-access HTTP/1.1" 200 1100 "-" "HashiCorp Terraform/1.9.5 (+https://www.terraform.io) Terraform Plugin SDK/v2.30.0 Terraform Provider OpenStack/3.0.0 HashiCorp-terraform-exec/0.16.1 gophercloud/v2.1.1"
127.0.0.1 - - [26/Dec/2024:00:00:11 +0000] "POST /v2.1/os-server-external-events HTTP/1.1" 200 641 "-" "python-novaclient"
127.0.0.1 - - [27/Dec/2024:00:00:15 +0000] "GET /v2.1/flavors/9af6e698-fd0d-4687-aa47-d53ebf80efc5/os-flavor-access HTTP/1.1" 200 1101 "-" "HashiCorp Terraform/1.9.5 (+https://www.terraform.io) Terraform Plugin SDK/v2.30.0 Terraform Provider OpenStack/3.0.0 HashiCorp-terraform-exec/0.16.1 gophercloud/v2.1.1"
127.0.0.1 - - [27/Dec/2024:00:00:16 +0000] "GET /v2.1/flavors/a7317d1a-247e-4509-8a53-9a20b9c91be1/os-flavor-access HTTP/1.1" 200 2453 "-" "HashiCorp Terraform/1.9.5 (+https://www.terraform.io) Terraform Plugin SDK/v2.30.0 Terraform Provider OpenStack/3.0.0 HashiCorp-terraform-exec/0.16.1 gophercloud/v2.1.1"
127.0.0.1 - - [27/Dec/2024:00:00:11 +0000] "GET /v2.1/servers/cd3fb57b-9f28-422f-9a0c-d56dfb89ee94 HTTP/1.1" 200 3984 "-" "python-novaclient"
127.0.0.1 - - [27/Dec/2024:00:00:12 +0000] "GET /v2.1/os-quota-sets/ebb09221230f4d3eb0969d2755046fe1 HTTP/1.1" 200 829 "-" "HashiCorp Terraform/1.9.5 (+https://www.terraform.io) Terraform Plugin SDK/v2.30.0 Terraform Provider OpenStack/3.0.0 HashiCorp-terraform-exec/0.16.1 gophercloud/v2.1.1"
""".split('\n')[1:]  # noqa


NOVA_VM_BUILD_TIME = """
2025-02-06 13:25:34.660 3070789 INFO nova.compute.manager [req-cf1f5fee-ff91-4a23-b832-58dd43ad483d 50bbc907c4114c5fb6eb28fdaf64a477 1d7753cbc6244d25aeccd8addfbb7b0b - default default] [instance: ec16f413-9352-499c-b4e2-989dad016691] Took 323.71 seconds to build instance.
2025-02-06 13:25:34.866 3070789 INFO nova.compute.manager [req-6b5f44f9-219c-4fca-a94e-6b663b8c5fa8 338da029e0a84bdea68aaf46adbb2b6a ae101b218e8b4baca86c2abf9c8fda6d - default default] [instance: c7bab001-4cd9-459b-a160-b715d5e037e4] Took 210.26 seconds to build instance.
2025-02-06 13:25:34.922 3070789 INFO nova.compute.manager [req-2b17d390-2287-492d-9ec4-c3501cbd6879 50bbc907c4114c5fb6eb28fdaf64a477 1d7753cbc6244d25aeccd8addfbb7b0b - default default] [instance: bdae3038-89e4-40b3-84ce-1381d3eca7d6] Took 111.96 seconds to build instance.
2025-02-06 13:26:14.623 3070789 INFO nova.compute.manager [req-5f197892-f9d5-4625-bff9-587ab91744b8 50bbc907c4114c5fb6eb28fdaf64a477 1d7753cbc6244d25aeccd8addfbb7b0b - default default] [instance: 461d206e-993e-4ada-bfc8-adb3910717fc] Took 27.79 seconds to build instance.
2025-02-06 13:27:17.662 3070789 INFO nova.compute.manager [req-1915e36f-27e1-40e1-9528-70f309be1952 338da029e0a84bdea68aaf46adbb2b6a ae101b218e8b4baca86c2abf9c8fda6d - default default] [instance: dceffed5-c6ae-4eec-8800-9b28aa6cdbbd] Took 78.80 seconds to build instance.
2025-02-06 13:27:17.662 3070789 INFO nova.compute.manager [req-1915e36f-27e1-40e1-9528-70f309be1952 338da029e0a84bdea68aaf46adbb2b6a ae101b218e8b4baca86c2abf9c8fda6d - default default] [instance: dceffed5-c6ae-4eec-8800-9b28aa6cdbbd] Took 78.60 seconds to build instance.
2025-02-06 13:28:13.020 3070789 INFO nova.compute.manager [req-3ca74933-c23e-4ccf-a8e0-a7d130e3ad75 39656a4e94d140279666b3398a5d36e3 6804bfca484f4f559c01edaf5615dc5f - default default] [instance: 5da6c1a4-0608-402c-8856-5b38a061bf66] Took 72.22 seconds to build instance.
2025-02-06 13:28:13.803 3070789 INFO nova.compute.manager [req-872f741a-c886-4464-86ec-efbd7f9a8843 50bbc907c4114c5fb6eb28fdaf64a477 1d7753cbc6244d25aeccd8addfbb7b0b - default default] [instance: 7da734a9-c393-4763-b0a7-dfbaac0aa331] Took 61.66 seconds to build instance.
2025-02-06 13:28:13.897 3070789 INFO nova.compute.manager [req-a1903088-e68e-4071-a93d-9b1e12525acf 50bbc907c4114c5fb6eb28fdaf64a477 1d7753cbc6244d25aeccd8addfbb7b0b - default default] [instance: d4d18888-5aac-492e-b1ea-3cb590c537d0] Took 10.73 seconds to build instance.
""".strip('\n')  # noqa

NOVA_LOCK_HELD = """
2025-02-28 11:00:14.750 1566099 DEBUG oslo_concurrency.lockutils [-] Lock "3726526a-c14d-4ddd-8392-89a47da5c046" "released" by "nova.compute.manager.ComputeManager._sync_power_states.<locals>._sync.<locals>.query_driver_power_state_and_sync" :: held 18.945s inner /usr/lib/python3/dist-packages/oslo_concurrency/lockutils.py:400
2025-02-28 11:00:14.791 1566099 DEBUG oslo_concurrency.lockutils [-] Lock "bfdb3972-b470-4980-9832-a42d82b92a1c" "released" by "nova.compute.manager.ComputeManager._sync_power_states.<locals>._sync.<locals>.query_driver_power_state_and_sync" :: held 18.985s inner /usr/lib/python3/dist-packages/oslo_concurrency/lockutils.py:400
2025-02-28 11:00:14.904 1566099 DEBUG oslo_concurrency.lockutils [-] Lock "d201206e-cccf-4fcc-9ddf-fd33249a4cb7" "released" by "nova.compute.manager.ComputeManager._sync_power_states.<locals>._sync.<locals>.query_driver_power_state_and_sync" :: held 19.098s inner /usr/lib/python3/dist-packages/oslo_concurrency/lockutils.py:400
2025-02-28 11:00:14.924 1566099 DEBUG oslo_concurrency.lockutils [-] Lock "de3b0feb-8d6e-43cf-a380-1267ee5a64f9" "released" by "nova.compute.manager.ComputeManager._sync_power_states.<locals>._sync.<locals>.query_driver_power_state_and_sync" :: held 19.119s inner /usr/lib/python3/dist-packages/oslo_concurrency/lockutils.py:400
2025-02-28 11:00:15.029 1566099 DEBUG oslo_concurrency.lockutils [req-98e9d691-5eaf-48ef-9bf2-e4fede9c5ae3 - - - - -] Lock "compute_resources" acquired by "nova.compute.resource_tracker.ResourceTracker.clean_compute_node_cache" :: waited 0.000s inner /usr/lib/python3/dist-packages/oslo_concurrency/lockutils.py:386
2025-02-28 11:00:15.030 1566099 DEBUG oslo_concurrency.lockutils [req-98e9d691-5eaf-48ef-9bf2-e4fede9c5ae3 - - - - -] Lock "compute_resources" "released" by "nova.compute.resource_tracker.ResourceTracker.clean_compute_node_cache" :: held 0.000s inner /usr/lib/python3/dist-packages/oslo_concurrency/lockutils.py:400
2025-02-28 11:00:15.048 1566099 DEBUG oslo_concurrency.lockutils [-] Lock "b6e6114b-dba8-4065-b213-97f8afb5e91e" "released" by "nova.compute.manager.ComputeManager._sync_power_states.<locals>._sync.<locals>.query_driver_power_state_and_sync" :: held 19.242s inner /usr/lib/python3/dist-packages/oslo_concurrency/lockutils.py:400
""".strip('\n')  # noqa


class TestOpenstackAgentEvents(TestOpenstackBase):
    """ Unit tests for OpenStack agent event checks. """
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
        with GlobalSearcher() as searcher:
            inst = agent.events.NeutronAgentEventChecks(searcher)
            inst.run()
            actual = self.part_output_to_actual(inst.output)
            self.assertEqual(actual['agent-checks'][section_key], expected)

    def test_get_router_event_stats(self):
        expected = {'router-spawn-events': {
                        'stats': {
                            'avg': 72.09,
                            'max': 72.09,
                            'min': 72.09,
                            'samples': 1,
                            'stdev': 0.0},
                        'top': {
                            '984c22fd-64b3-4fa1-8ddd-87090f401ce5': {
                                'duration': 72.09,
                                'start': '2022-02-10 '
                                         '16:09:22.679000',
                                'end': '2022-02-10 '
                                       '16:10:34.767000'}}},
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
        with GlobalSearcher() as searcher:
            inst = agent.events.NeutronAgentEventChecks(searcher)
            inst.run()
            actual = self.part_output_to_actual(inst.output)

        self.assertEqual(actual['agent-checks'][section_key], expected)

    @utils.create_data_root({'var/log/octavia/octavia-health-manager.log':
                             EVENT_OCTAVIA_CHECKS})
    def test_run_octavia_checks(self):
        expected = {'amp-missed-heartbeats': {
                        '3604bf2a-ee51-4135-97e2-ec08ed9321db': {
                            '2022-06-01': 1}},
                    'lb-failovers': {
                        'auto': {
                            '7a3b90ed-020e-48f0-ad6f-b28443fa2277': {
                                '2022-03-09': 1},
                            '98aefcff-60e5-4087-8ca6-5087ae970440': {
                                '2022-03-09': 1},
                            '9cd90142-5501-4362-93ef-1ad219baf45a': {
                                '2022-03-09': 1},
                            'e9cb98af-9c21-4cf6-9661-709179ce5733': {
                                '2022-03-09': 1}}
                     }
                    }
        with GlobalSearcher() as searcher:
            inst = agent.events.OctaviaAgentEventChecks(searcher)
            inst.run()
            actual = self.part_output_to_actual(inst.output)

        for section_key in ['amp-missed-heartbeats', 'lb-failovers']:
            self.assertEqual(actual['agent-checks']["octavia"][section_key],
                             expected[section_key])

    @utils.create_data_root({'var/log/apache2/error.log':
                             EVENT_APACHE_CONN_REFUSED_LOG})
    def test_run_apache_checks(self):
        expected = {'connection-refused': {
                        '2021-10-26': {'127.0.0.1:8981': 3}}}

        with GlobalSearcher() as searcher:
            inst = agent.events.ApacheEventChecks(searcher)
            inst.run()
            actual = self.part_output_to_actual(inst.output)

        for section_key in ['connection-refused']:
            self.assertEqual(actual['agent-checks']['apache'][section_key],
                             expected[section_key])

    @utils.create_data_root({'var/log/kern.log': AA_MSGS})
    def test_run_apparmor_checks(self):
        expected = {'denials': {
                        'neutron': {
                            '/usr/bin/neutron-dhcp-agent': {
                                'Mar 3': 2},
                            '/usr/bin/neutron-l3-agent': {
                                'Mar 3': 1},
                            '/usr/bin/neutron-openvswitch-agent': {
                                'Mar 3': 4}}}}
        with GlobalSearcher() as searcher:
            inst = agent.events.AgentApparmorChecks(searcher)
            inst.run()
            actual = self.part_output_to_actual(inst.output)

        self.assertEqual(actual['agent-checks']['apparmor'], expected)

    @utils.create_data_root({'var/log/kern.log': AA_MSGS})
    def test_run_apparmor_checks_w_time_granularity(self):
        HotSOSConfig.event_tally_granularity = 'time'
        expected = {'denials': {
                        'neutron': {
                            '/usr/bin/neutron-dhcp-agent': {
                                'Mar 3': {
                                    '22:57:11': 1,
                                    '22:57:23': 1}},
                            '/usr/bin/neutron-l3-agent': {
                                'Mar 3': {
                                    '22:57:11': 1}},
                            '/usr/bin/neutron-openvswitch-agent': {
                                'Mar 3': {
                                    '22:57:11': 1,
                                    '22:57:22': 1,
                                    '22:57:24': 2}}}}}
        with GlobalSearcher() as searcher:
            inst = agent.events.AgentApparmorChecks(searcher)
            inst.run()
            actual = self.part_output_to_actual(inst.output)

        self.assertEqual(actual['agent-checks']['apparmor'], expected)

    @utils.create_data_root({'var/log/nova/nova-compute.log':
                             EVENT_PCIDEVNOTFOUND_LOG})
    def test_run_nova_checks(self):
        expected = {'PciDeviceNotFoundById': {
                        '2022-09-17': {'0000:3b:0f.7': 1,
                                       '0000:3b:10.0': 1}}}
        with GlobalSearcher() as searcher:
            inst = agent.events.NovaComputeEventChecks(searcher)
            inst.run()
            actual = self.part_output_to_actual(inst.output)

        self.assertEqual(actual['agent-checks']['nova'], expected)

    def test_run_neutron_l3ha_checks(self):
        expected = {'keepalived': {
                     'transitions': {
                         '984c22fd-64b3-4fa1-8ddd-87090f401ce5': {
                             '2022-02-10': 1}}}}
        with GlobalSearcher() as searcher:
            inst = agent.events.NeutronL3HAEventChecks(searcher)
            inst.run()
            actual = self.part_output_to_actual(inst.output)

        self.assertEqual(actual['agent-checks']['neutron-l3ha'], expected)

    @mock.patch.object(agent.events, "VRRP_TRANSITION_WARN_THRESHOLD",
                       0)
    def test_run_neutron_l3ha_checks_w_issue(self):
        HotSOSConfig.use_all_logs = False
        expected = {'keepalived': {
                     'transitions': {
                         '984c22fd-64b3-4fa1-8ddd-87090f401ce5': {
                             '2022-02-10': 1}}}}
        with GlobalSearcher() as searcher:
            inst = agent.events.NeutronL3HAEventChecks(searcher)
            inst.run()
            actual = self.part_output_to_actual(inst.output)

        self.assertEqual(actual['agent-checks']['neutron-l3ha'], expected)
        issues = list(IssuesStore().load().values())[0]
        msg = ('1 router(s) have had more than 0 vrrp transitions (max=1) in '
               'the last 24 hours.')
        self.assertEqual([issue['message'] for issue in issues], [msg])

    @utils.create_data_root({'var/log/neutron/neutron-server.log':
                             NEUTRON_HTTP})
    def test_api_events(self):
        with GlobalSearcher() as searcher:
            inst = agent.events.APIEvents(searcher)
            inst.run()
            actual = self.part_output_to_actual(inst.output)

        expected = {'http-requests': {'neutron': {
                                        '2022-05-11': {'GET': 2,
                                                       'PUT': 3,
                                                       'POST': 4,
                                                       'DELETE': 5}}}}
        self.assertEqual(actual['api-info'], expected)

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('http-requests.yaml',
                                        'events/openstack'))
    @utils.create_data_root({'var/log/apache2/'
                             'nova-api-os-compute_access.log.2.gz':
                             '\n'.join(NOVA_REST_API[:2]),
                             'var/log/apache2/'
                             'nova-api-os-compute_access.log.1.gz':
                             '\n'.join(NOVA_REST_API[2:3]),
                             'var/log/apache2/nova-api-os-compute_access.log':
                             '\n'.join(NOVA_REST_API[3:])},
                            copy_from_original=['sos_commands/date/date'])
    def test_nova_http_requests(self):
        expected = {}
        with GlobalSearcher() as searcher:
            inst = agent.events.APIEvents(searcher)
            actual = self.part_output_to_actual(inst.output)
            expected = {'api-info': {
                            'http-requests': {
                                'nova': {
                                    '2024-12-27': {
                                        'GET': 4}
                                    }
                                }
                            }
                        }
            self.assertEqual(actual, expected)

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('nova-compute.yaml',
                                        'events/openstack'))
    @utils.create_data_root({'var/log/nova/nova-compute.log':
                             NOVA_LOCK_HELD},
                            copy_from_original=['sos_commands/date/date'])
    def test_nova_lock_held_times(self):
        expected = {}
        with GlobalSearcher() as searcher:
            inst = agent.events.NovaComputeEventChecks(searcher)
            actual = self.part_output_to_actual(inst.output)
            expected = {'agent-checks': {
                            'nova': {
                                'nova-compute': {
                                    'lock-held-times': {
                                        '2025-02-28': {'18': 2,
                                                       '19': 3}}}}}}
            self.assertDictEqual(actual, expected)

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('nova-compute.yaml',
                                        'events/openstack'))
    @utils.create_data_root({'var/log/nova/nova-compute.log':
                             NOVA_VM_BUILD_TIME},
                            copy_from_original=['sos_commands/date/date'])
    def test_nova_vm_builds(self):
        expected = {}
        with GlobalSearcher() as searcher:
            inst = agent.events.NovaComputeEventChecks(searcher)
            actual = self.part_output_to_actual(inst.output)
            expected = {'agent-checks': {
                            'nova': {
                                'nova-compute': {
                                    'vm-build-times-gt-60s': {
                                        '2025-02-06': {
                                            'top5': {'323': 1,
                                                     '210': 1,
                                                     '111': 1,
                                                     '78': 2,
                                                     '72': 1,
                                                     },
                                            'total': 6}}}}}}

            self.assertEqual(actual, expected)

    @utils.create_data_root({'var/log/neutron/neutron-server.log':
                             OVSDBAPP_LEADER_CHANGING})
    def test_server_ovsdbapp_events(self):
        with GlobalSearcher() as searcher:
            inst = agent.events.NeutronAgentEventChecks(searcher)
            inst.run()
            actual = self.part_output_to_actual(inst.output)

        expected = {'neutron-server': {
                    'ovsdbapp-nb-leader-reconnect': {
                        '2023-11-23': {'6641': 2}},
                    'ovsdbapp-sb-leader-reconnect': {
                        '2023-11-23': {'16642': 3}}}}
        self.assertEqual(actual['agent-checks'], expected)

    @utils.create_data_root({'var/log/neutron/neutron-server.log':
                             OVN_RESOURCE_VERSION_BUMP_EVENTS})
    def test_server_ovn_resource_version_bump_events(self):
        with GlobalSearcher() as searcher:
            inst = agent.events.NeutronAgentEventChecks(searcher)
            inst.run()
            actual = self.part_output_to_actual(inst.output)

        expected = {'neutron-server': {
                        'ovn-resource-revision-bump': {'2023-12-09': {
                            '4dedf9dd-ff5e-4b71-bebb-9d168b83c0b8': 2,
                            'd82ce545-ccdf-4784-9cc7-ba10f8051d1a': 2,
                            'ed43f1b0-c11c-46dc-9c1a-9654d450a010': 2}}}}
        self.assertEqual(actual['agent-checks'], expected)

    @utils.create_data_root({'var/log/neutron/neutron-server.log':
                             OVN_OVSDB_ABORTED_TRANSACTIONS})
    def test_server_ovsdb_aborted_transactions(self):
        with GlobalSearcher() as searcher:
            inst = agent.events.NeutronAgentEventChecks(searcher)
            inst.run()
            actual = self.part_output_to_actual(inst.output)

        expected = {'neutron-server': {
                        'ovsdb-transaction-aborted': {'2023-12-12': 5}}}
        self.assertEqual(actual['agent-checks'], expected)


class TestOpenstackAgentExceptions(TestOpenstackBase):
    """ Unit tests for OpenStack agent exception checks. """
    @utils.create_data_root({'var/log/nova/nova-compute.log': NC_LOGS},
                            copy_from_original=['sos_commands/systemd',
                                                'sos_commands/dpkg'])
    def test_agent_exception_checks_simple(self):
        expected = {'error': {
                        'nova': {
                            'nova-compute': {
                                'oslo_messaging.exceptions.MessagingTimeout': {
                                    '2022-02-09': 2}}}},
                    'warning': {
                        'nova': {
                            'nova-compute': {
                                'oslo_messaging.exceptions.MessagingTimeout': {
                                    '2022-02-04': 1,
                                    '2022-02-09': 1}}}}}
        inst = agent.exceptions.AgentExceptionChecks()
        files = {}
        logs = {}
        for loglevel, services in inst.agent_results.items():
            for service, results in services.items():
                files[service] = (
                              len(results.files_w_exceptions),
                              os.path.basename(results.files_w_exceptions[0]))
                logs[service] = results.exceptions_raised

            if loglevel == 'error':
                self.assertEqual(files, {'nova': (1, 'nova-compute.log')})
                expected_exceptions = {
                    'nova': ['oslo_messaging.exceptions.MessagingTimeout']}
                self.assertEqual(logs, expected_exceptions)
            else:
                self.assertEqual(files, {'nova': (1, 'nova-compute.log')})
                expected_exceptions = {
                    'nova': ['oslo_messaging.exceptions.MessagingTimeout']}
                self.assertEqual(logs, expected_exceptions)

        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual['agent-exceptions'], expected['error'])
        self.assertEqual(actual['agent-warnings'], expected['warning'])

    def test_agent_exception_checks(self):
        neutron_error_exceptions = {
            'neutron-openvswitch-agent': {
                'oslo_messaging.exceptions.MessagingTimeout': {
                    '2022-02-04': 75,
                    '2022-02-09': 3}},
            'neutron-dhcp-agent': {
                'oslo_messaging.exceptions.MessagingTimeout': {
                    '2022-02-04': 124,
                    '2022-02-09': 17}},
            'neutron-l3-agent': {
                'oslo_messaging.exceptions.MessagingTimeout': {
                    '2022-02-04': 73,
                    '2022-02-09': 3}},
            'neutron-metadata-agent': {
                'OSError': {'2022-02-09': 1},
                'oslo_messaging.exceptions.MessagingTimeout': {
                    '2022-02-04': 48,
                    '2022-02-09': 14}},
        }
        nova_error_exceptions = {
            'nova-compute': {
                'oslo_messaging.exceptions.MessagingTimeout': {
                    '2022-02-04': 64,
                    '2022-02-09': 2},
                'nova.exception.ResourceProviderRetrievalFailed': {
                    '2022-02-04': 6},
                'nova.exception.ResourceProviderAllocationRetrievalFailed': {
                    '2022-02-04': 2}},
            'nova-api-metadata': {
                'OSError': {'2022-02-09': 4},
                'oslo_messaging.exceptions.MessagingTimeout': {
                    '2022-02-04': 110,
                    '2022-02-09': 56}}
        }
        neutron_warn_exceptions = {
            'neutron-dhcp-agent': {
                'oslo_messaging.exceptions.MessagingTimeout': {
                    '2022-02-04': 2,
                    '2022-02-09': 1}},
            'neutron-l3-agent': {
                'oslo_messaging.exceptions.MessagingTimeout':
                    {'2022-02-04': 9,
                     '2022-02-09': 6}},
            'neutron-openvswitch-agent': {
                'oslo_messaging.exceptions.MessagingTimeout': {
                    '2022-02-04': 13,
                    '2022-02-09': 6}}
        }
        nova_warn_exceptions = {
            'nova-compute': {
                'oslo_messaging.exceptions.MessagingTimeout': {
                    '2022-02-04': 59,
                    '2022-02-09': 1}}
        }
        expected = {'error': {
                        'neutron': neutron_error_exceptions,
                        'nova': nova_error_exceptions},
                    'warning': {
                        'neutron': neutron_warn_exceptions,
                        'nova': nova_warn_exceptions},
                    }

        inst = agent.exceptions.AgentExceptionChecks()
        files = {}
        exceptions = {}
        for loglevel, services in inst.agent_results.items():
            for service, results in services.items():
                files[service] = (len(results.files_w_exceptions),
                                  os.path.basename(
                                                results.files_w_exceptions[0]))
                exceptions[service] = results.exceptions_raised

            if loglevel == 'error':
                self.assertEqual(files, {'neutron':
                                         (4, 'neutron-dhcp-agent.log.1'),
                                         'nova':
                                         (2, 'nova-api-metadata.log.1.gz')})
                expected_exceptions = {
                    'neutron': [
                        'oslo_messaging.exceptions.MessagingTimeout'],
                    'nova': [
                        ('nova.exception.ResourceProviderAllocation'
                         'RetrievalFailed'),
                        'OSrror',
                        'oslo_messaging.exceptions.MessagingTimeout',
                        'nova.exception.ResourceProviderRetrievalFailed']}
                self.assertEqual(sorted(exceptions),
                                 sorted(expected_exceptions))
            else:
                self.assertEqual(files, {'neutron':
                                         (3, 'neutron-dhcp-agent.log.1'),
                                         'nova':
                                         (1, 'nova-compute.log.1.gz')})
                expected_exceptions = {
                    'neutron': [
                        'oslo_messaging.exceptions.MessagingTimeout'],
                    'nova': [
                        'oslo_messaging.exceptions.MessagingTimeout']}
                self.assertEqual(exceptions, expected_exceptions)

        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual['agent-exceptions'], expected['error'])
        self.assertEqual(actual['agent-warnings'], expected['warning'])
