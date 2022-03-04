from core.plugintools import summary_entry_offset as idx
from core.plugins.juju import JujuServiceChecksBase

YAML_OFFSET = 0


class JujuSummary(JujuServiceChecksBase):

    @idx(0)
    def __summary_services(self):
        if self.services:
            return {'systemd': self.service_info,
                    'ps': self.process_info}

    @idx(1)
    def __summary_version(self):
        if self.machine:
            return self.machine.version

    @idx(2)
    def __summary_machine(self):
        if self.machine:
            return self.machine.id

    @idx(3)
    def __summary_charms(self):
        if self.charms:
            charms = ["{}-{}".format(c.name, c.version) for c in self.charms]
            return sorted(charms)

    @idx(4)
    def __summary_units(self):
        unit_info = {}
        if self.units:
            unit_info["local"] = sorted([u.name for u in self.units])

        if self.nonlocal_units:
            unit_info['lxd'] = sorted([u.name for u in self.nonlocal_units])

        if unit_info:
            return unit_info
