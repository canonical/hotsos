#!/usr/bin/python3
from common import plugin_yaml
from openstack_common import OpenstackChecksBase

VM_INFO = {}


class OpenstackInstanceChecks(OpenstackChecksBase):

    def get_vm_info(self):
        instances = self.running_instances
        if instances:
            VM_INFO["instances"] = instances

    def __call__(self):
        self.get_vm_info()


def get_vm_checks():
    return OpenstackInstanceChecks()


if __name__ == "__main__":
    get_vm_checks()()
    if VM_INFO:
        plugin_yaml.save_part(VM_INFO, priority=1)
