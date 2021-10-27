from core.host_helpers import NetworkPort
from core.plugins.openvswitch import OpenvSwitchChecksBase

YAML_PRIORITY = 0


class OpenvSwitchServiceChecks(OpenvSwitchChecksBase):

    def get_running_services_info(self):
        """Get string info for running daemons."""
        if self.svc_check.services:
            self._output['services'] = self.svc_check.service_info_str

    def __call__(self):
        self.get_running_services_info()


class OpenvSwitchPackageChecks(OpenvSwitchChecksBase):

    def __call__(self):
        self._output['dpkg'] = self.apt_check.all_formatted


class OpenvSwitchConfigChecks(OpenvSwitchChecksBase):

    @property
    def output(self):
        if self._output:
            return {'config': self._output}

    def __call__(self):
        if self.offload_enabled:
            self._output['offload'] = 'enabled'


class OpenvSwitchBridgeChecks(OpenvSwitchChecksBase):

    @property
    def output(self):
        if self._output:
            return {'bridges': self._output}

    def __call__(self):
        bridges = {}
        for bridge in self.bridges:
            # filter patch/phy ports since they are not generally interesting
            ports = []
            for port in bridge.ports:
                if type(port) != NetworkPort:
                    name = port
                else:
                    name = port.name

                if (name.startswith('patch-') or name.startswith('phy-') or
                        name.startswith('int-')):
                    continue

                if type(port) != NetworkPort:
                    # ovs port so will be just a name
                    ports.append(port)
                    continue

                ports.append(port.to_dict())

            # exlude br-int port since it will have too many
            if bridge.name == 'br-int' and ports:
                ports = ["({} ports)".format(len(ports))]

            bridges[bridge.name] = ports

        if bridges:
            self._output = bridges
