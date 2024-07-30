import os
import re
from functools import cached_property
from dataclasses import dataclass

from hotsos.core.config import HotSOSConfig
from hotsos.core.factory import FactoryBase
from hotsos.core.host_helpers import CLIHelper
from hotsos.core.plugins.openstack.openstack import (
    OpenstackConfig,
    OSTServiceBase,
)

# See https://github.com/openstack/neutron-lib/blob/master/neutron_lib/constants.py#L346  # noqa, pylint: disable=C0301
IP_HEADER_BYTES = 20
GRE_HEADER_BYTES = 22
VXLAN_HEADER_BYTES = 30


class NeutronBase(OSTServiceBase):
    """ Base class for Neutron checks. """
    def __init__(self, *args, **kwargs):
        super().__init__('neutron', *args, **kwargs)
        self.neutron_ovs_config = self.project.config['openvswitch-agent']

    @cached_property
    def bind_interfaces(self):
        """
        Fetch interfaces used by Openstack Neutron. Returned dict is keyed by
        config key used to identify interface.
        """
        local_ip = self.neutron_ovs_config.get('local_ip')

        interfaces = {}
        if not any([local_ip]):
            return interfaces

        if local_ip:
            port = self.nethelp.get_interface_with_addr(local_ip)
            # NOTE: local_ip can be an address or fqdn, we currently only
            # support searching by address.
            if port:
                interfaces.update({'local_ip': port})

        return interfaces


class ServiceChecks():
    """ Neutron service specific checks.  """
    @cached_property
    def ovs_cleanup_run_manually(self):
        """ Allow one run on node boot/reboot but not after. """
        run_manually = False
        start_count = 0
        cli = CLIHelper()
        cexpr = re.compile(r"Started OpenStack Neutron OVS cleanup.")
        for line in cli.journalctl(unit="neutron-ovs-cleanup"):
            if re.compile("-- Reboot --").match(line):
                # reset after reboot
                run_manually = False
                start_count = 0
            elif cexpr.search(line):
                if start_count:
                    run_manually = True

                start_count += 1

        return run_manually


@dataclass
class NeutronRouter:
    """ Representation of a Neutron router. """

    uuid: str
    ha_state: str
    vr_id: str = None


class NeutronHAInfo():
    """ Representation of Neutron HA state. """
    def __init__(self):
        self.vr_id = None

    @cached_property
    def state_path(self):
        ha_confs = 'var/lib/neutron/ha_confs'
        return os.path.join(HotSOSConfig.data_root, ha_confs)

    @cached_property
    def ha_routers(self):
        if not os.path.exists(self.state_path):
            return []

        _routers = []
        for entry in os.listdir(self.state_path):
            entry = os.path.join(self.state_path, entry)
            if not os.path.isdir(entry):
                # if its not a directory then it is probably not a live router
                # so we ignore it.
                continue

            state_path = os.path.join(entry, 'state')
            if not os.path.exists(state_path):
                continue

            with open(state_path, encoding='utf-8') as fd:
                uuid = os.path.basename(entry)
                state = fd.read().strip()
                router = NeutronRouter(uuid, state)

            keepalived_conf_path = os.path.join(entry, 'keepalived.conf')
            if os.path.isfile(keepalived_conf_path):
                with open(keepalived_conf_path, encoding='utf-8') as fd:
                    for line in fd:
                        expr = r'.+ virtual_router_id (\d+)'
                        ret = re.compile(expr).search(line)
                        if ret:
                            router.vr_id = ret.group(1)

            _routers.append(router)

        return _routers

    def find_router_with_vr_id(self, vr_id):
        for r in self.ha_routers:
            if r.vr_id == vr_id:
                return r

        return None


class Config(FactoryBase):
    """ Neutron config. """
    def __getattr__(self, path):
        path = os.path.join(HotSOSConfig.data_root, 'etc/neutron', path)
        return OpenstackConfig(path)
