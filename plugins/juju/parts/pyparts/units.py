#!/usr/bin/python3
import os

from juju_common import (
    JUJU_LOG_PATH,
    JujuChecksBase,
)

YAML_PRIORITY = 2


class JujuUnitChecks(JujuChecksBase):

    def get_unit_info(self):
        unit_info = {"units": {}}
        unit_nonlocal = set()
        app_nonlocal = {}
        app_local = set()
        units_local = set()
        units_local_not_running = set()
        units_local_not_running_filtered = set()
        units_nonlocal_dedup = set()

        if not os.path.exists(JUJU_LOG_PATH):
            return

        ps_units = self._get_ps_units()
        log_units = self._get_log_units()
        combined_units = ps_units.union(log_units)

        for unit in combined_units:
            if unit in log_units:
                if unit in ps_units:
                    app_local.add(unit.partition('-')[2])
                    units_local.add(unit)
                else:
                    units_local_not_running.add(unit)
            else:
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

                unit_nonlocal.add(unit)

        # remove units from units_local_not_running that are just old versions
        # the one currently running
        for unit in units_local_not_running:
            app = self._get_app_from_unit_name(unit)
            if not app or app not in app_local:
                units_local_not_running_filtered.add(unit)

        # dedup unit_nonlocal
        for unit in unit_nonlocal:
            app = self._get_app_from_unit_name(unit)
            version = app_nonlocal[app]
            if version == self._get_unit_version(unit):
                units_nonlocal_dedup.add(unit)

        if units_local:
            unit_info["units"]["local"] = list(sorted(units_local))

        if units_local_not_running_filtered:
            unit_info["units"]["stopped"] = \
                list(sorted(units_local_not_running_filtered))

        if units_nonlocal_dedup:
            unit_info["units"]["lxd"] = \
                list(sorted(units_nonlocal_dedup))

        if unit_info["units"]:
            self._output.update(unit_info)

    def __call__(self):
        self.get_unit_info()
