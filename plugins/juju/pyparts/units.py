import os

from common.plugins.juju import (
    JUJU_LOG_PATH,
    JujuChecksBase,
)

YAML_PRIORITY = 2


class JujuUnitChecks(JujuChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.units = {}

    def get_nonlocal_unit_info(self):
        unit_nonlocal = set()
        app_nonlocal = {}
        units_nonlocal_dedup = set()
        for unit in self.ps_units:
            if unit in self.units.get("local", []):
                continue

            unit_nonlocal.add(unit)
            # i.e. it is running but there is no log file in /var/log/juju
            # so it is likely running in a container
            app = self._get_app_from_unit_name(unit)
            if app:
                version = self._get_unit_version(unit)
                if version is not None:
                    if app in app_nonlocal:
                        if version > app_nonlocal[app]:
                            app_nonlocal[app] = version
                    else:
                        app_nonlocal[app] = version

        # dedup unit_nonlocal
        for unit in unit_nonlocal:
            app = self._get_app_from_unit_name(unit)
            version = app_nonlocal[app]
            if version == self._get_unit_version(unit):
                units_nonlocal_dedup.add(unit)

        if units_nonlocal_dedup:
            self.units["lxd"] = \
                list(sorted(units_nonlocal_dedup))

    def get_local_unit_info_legacy(self):
        units_local = set()
        combined_units = self.ps_units.union(self.log_units)
        for unit in combined_units:
            if unit in self.log_units:
                units_local.add(unit)

        if units_local:
            self.units["local"] = list(sorted(units_local))

    def get_local_unit_info(self):
        self.units["local"] = self.machine.deployed_units

    def __call__(self):
        if not os.path.exists(JUJU_LOG_PATH):
            return

        if self.machine.version < "2.9":
            self.get_local_unit_info_legacy()
        else:
            self.get_local_unit_info()

        self.get_nonlocal_unit_info()
        if self.units:
            self._output.update({"units": self.units})
