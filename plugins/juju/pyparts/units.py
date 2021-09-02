from core.plugins.juju import JujuChecksBase

YAML_PRIORITY = 2


class JujuUnitChecks(JujuChecksBase):

    def get_nonlocal_unit_info(self):
        """ These are units that may be running on the local host i.e.
        their associated jujud process is visible but inside containers.
        """
        unit_nonlocal = []
        app_nonlocal = {}
        units_nonlocal_dedup = set()
        local_units = [u.name for u in self.units]
        for unit in self.ps_units:
            if unit.name in local_units:
                continue

            unit_nonlocal.append(unit)

        if unit_nonlocal:
            return list(sorted([u.name for u in unit_nonlocal]))

    def __call__(self):
        unit_info = {}
        if self.units:
            unit_info["local"] = sorted([u.name for u in self.units])

        non_local = self.get_nonlocal_unit_info()
        if non_local:
            unit_info['lxd'] = non_local

        if unit_info:
            self._output.update({"units": unit_info})
