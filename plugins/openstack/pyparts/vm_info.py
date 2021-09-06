import os

from core import constants
from core.searchtools import (
    FileSearcher,
    SearchDef,
)
from core.plugins.openstack import (
    OpenstackChecksBase,
    OpenstackConfig,
)

from core.plugins.system import SystemBase
from core.plugins.kernel import CPU

YAML_PRIORITY = 3


class OpenstackInstanceChecks(OpenstackChecksBase):

    def __init__(self):
        super().__init__()
        self._nova_config = OpenstackConfig(os.path.join(constants.DATA_ROOT,
                                                         "etc/nova/nova.conf"))

    def _get_vm_info(self):
        instances = self.instances
        if instances:
            self._output["running"] = [i.uuid for i in instances]

    def _get_vcpu_info(self):
        vcpu_info = {}
        guests = []
        s = FileSearcher()
        instances = self.instances
        if instances:
            for i in instances:
                guests.append(i.name)
                path = os.path.join(constants.DATA_ROOT, 'etc/libvirt/qemu',
                                    "{}.xml".format(i.name))
                s.add_search_term(SearchDef(".+vcpus>([0-9]+)<.+",
                                            tag=i.name), path)

            total_vcpus = 0
            results = s.search()
            for guest in guests:
                for r in results.find_by_tag(guest):
                    vcpus = r.get(1)
                    total_vcpus += int(vcpus)

            vcpu_info["used"] = total_vcpus
            sysinfo = SystemBase()
            if sysinfo.num_cpus is not None:
                total_cores = sysinfo.num_cpus
                vcpu_info["system-cores"] = total_cores

                pinset = self._nova_config.get("vcpu_pin_set",
                                               expand_ranges=True) or []
                pinset += self._nova_config.get("cpu_dedicated_set",
                                                expand_ranges=True) or []
                pinset += self._nova_config.get("cpu_shared_set",
                                                expand_ranges=True) or []
                if pinset:
                    # if pinning is used, reduce total num of cores available
                    # to those included in nova cpu sets.
                    available_cores = len(set(pinset))
                else:
                    available_cores = total_cores

                vcpu_info["available-cores"] = available_cores

                cpu = CPU()
                # put this here so that available cores value has
                # context
                if cpu.smt is not None:
                    vcpu_info["smt"] = cpu.smt

                factor = float(total_vcpus) / available_cores
                vcpu_info["overcommit-factor"] = round(factor, 2)

            self._output["vcpu-info"] = vcpu_info

    @property
    def output(self):
        if self._output:
            return {"vm-info": self._output}

    def __call__(self):
        # Only run if we think Openstack is installed.
        if not self.openstack_installed:
            return

        self._get_vm_info()
        self._get_vcpu_info()
