#!/usr/bin/python3
import os

from common import (
    plugin_yaml,
)
from juju_common import (
    JUJU_LOG_PATH,
    JujuChecksBase,
)

JUJU_UNIT_INFO = {"units": {}}


class JujuUnitChecks(JujuChecksBase):

    def get_unit_info(self):
        unit_nonlocal = set()
        app_nonlocal = {}
        app_local = set()
        units_local = set()
        units_local_not_running = set()
        units_local_not_running_filtered = set()
        units_nonlocal_dedup = set()

        if not os.path.exists(JUJU_LOG_PATH):
            return

        ps_units = self.get_ps_units()
        log_units = self.get_log_units()
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
                app = self.get_app_from_unit_name(unit)
                if app:
                    version = self.get_unit_version(unit)
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
            app = self.get_app_from_unit_name(unit)
            if not app or app not in app_local:
                units_local_not_running_filtered.add(unit)

        # dedup unit_nonlocal
        for unit in unit_nonlocal:
            app = self.get_app_from_unit_name(unit)
            version = app_nonlocal[app]
            if version == self.get_unit_version(unit):
                units_nonlocal_dedup.add(unit)

        if units_local:
            JUJU_UNIT_INFO["units"]["local"] = list(sorted(units_local))

        if units_local_not_running_filtered:
            JUJU_UNIT_INFO["units"]["stopped"] = \
                list(sorted(units_local_not_running_filtered))

        if units_nonlocal_dedup:
            JUJU_UNIT_INFO["units"]["lxd"] = \
                list(sorted(units_nonlocal_dedup))

    def __call__(self):
        self.get_unit_info()


def get_unit_checks():
    return JujuUnitChecks()


if __name__ == "__main__":
    get_unit_checks()()
    if JUJU_UNIT_INFO["units"]:
        plugin_yaml.save_part(JUJU_UNIT_INFO, priority=2)
