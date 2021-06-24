#!/usr/bin/python3
from openstack_common import OpenstackChecksBase

YAML_PRIORITY = 1


class OpenstackInstanceChecks(OpenstackChecksBase):

    def get_vm_info(self):
        instances = self.running_instances
        if instances:
            self._output["instances"] = instances

    def __call__(self):
        self.get_vm_info()
