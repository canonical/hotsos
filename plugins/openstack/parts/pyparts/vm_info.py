import os

from common import constants
from common.searchtools import (
    FileSearcher,
    SearchDef,
)

from openstack_common import (
    OpenstackChecksBase,
    OpenstackConfig,
)

from plugins.system.parts.pyparts.system import SystemChecks

YAML_PRIORITY = 3


class OpenstackInstanceChecks(OpenstackChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._nova_config = OpenstackConfig(os.path.join(constants.DATA_ROOT,
                                                         "etc/nova/nova.conf"))

    def _get_vm_info(self):
        instances = self.running_instances
        if instances:
            self._output["running"] = [i['uuid'] for i in instances]

    def _get_vcpu_info(self):
        guests = []
        s = FileSearcher()
        instances = self.running_instances
        if instances:
            for i in instances:
                name = i["name"]
                guests.append(name)
                path = os.path.join(constants.DATA_ROOT, 'etc/libvirt/qemu',
                                    "{}.xml".format(name))
                s.add_search_term(SearchDef(".+vcpus>([0-9]+)<.+",
                                            tag=name), path)

            total_vcpus = 0
            results = s.search()
            for guest in guests:
                for r in results.find_by_tag(guest):
                    vcpus = r.get(1)
                    total_vcpus += int(vcpus)

            self._output["vcpu-info"] = {"used": total_vcpus}
            sysinfo = SystemChecks()
            sysinfo.get_system_info()

            total_cpus = sysinfo.output["num-cpus"]
            self._output["vcpu-info"]["system-cpus"] = total_cpus

            pinset = self._nova_config.get("vcpu_pin_set",
                                           expand_ranges=True) or []
            pinset += self._nova_config.get("cpu_dedicated_set",
                                            expand_ranges=True) or []
            pinset += self._nova_config.get("cpu_shared_set",
                                            expand_ranges=True) or []
            if pinset:
                # if pinning is used, reduce total num of cpus available to
                # those included in nova cpu sets.
                available_cpus = len(set(pinset))
            else:
                available_cpus = total_cpus

            self._output["vcpu-info"]["available-pcpus"] = available_cpus

            factor = float(total_vcpus) / available_cpus
            self._output["vcpu-info"]["overcommit-factor"] = round(factor, 2)

    @property
    def output(self):
        if self._output:
            return {"vm-info": self._output}

    def __call__(self):
        self._get_vm_info()
        self._get_vcpu_info()
