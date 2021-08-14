import os

from common import constants
from common.searchtools import (
    FileSearcher,
    SearchDef,
)
from common.plugins.openstack import (
    OpenstackChecksBase,
    OpenstackConfig,
)

from plugins.system.pyparts.general import SystemGeneral
from plugins.kernel.pyparts.info import KernelGeneralChecks

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
        vcpu_info = {}
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

            vcpu_info["used"] = total_vcpus
            sysinfo = SystemGeneral()
            sysinfo.get_system_info()

            if sysinfo.output:
                total_cores = sysinfo.output["num-cpus"]
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

                k = KernelGeneralChecks()
                k.get_cpu_info()
                if k.output:
                    smt = k.output.get("cpu", {}).get("smt")
                    # repeat this here so that available cores value has
                    # context
                    if smt is not None:
                        vcpu_info["smt"] = smt

                factor = float(total_vcpus) / available_cores
                vcpu_info["overcommit-factor"] = round(factor, 2)

            self._output["vcpu-info"] = vcpu_info

    @property
    def output(self):
        if self._output:
            return {"vm-info": self._output}

    def __call__(self):
        self._get_vm_info()
        self._get_vcpu_info()
