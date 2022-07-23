from hotsos.core.plugintools import summary_entry_offset as idx
from hotsos.core.plugins.juju import JujuChecksBase


class JujuSummary(JujuChecksBase):

    @idx(0)
    def __summary_services(self):
        if self.systemd.services:
            return {'systemd': self.systemd.service_info,
                    'ps': self.systemd.process_info}

    @idx(1)
    def __summary_version(self):
        if self.machine:
            return self.machine.version
        else:
            return "unknown"

    @idx(2)
    def __summary_machine(self):
        if self.machine:
            return self.machine.id
        else:
            return "unknown"

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

    @idx(5)
    def __summary_charm_repo_info(self):
        if self.units:
            out = {}
            for u in self.units:
                if u.repo_info:
                    out[u.name] = u.repo_info.get('commit')

            if out:
                return out
