from hotsos.core.plugins.openstack.common import (
    OpenstackBase,
    OpenStackChecks,
)
from hotsos.core.plugins.openstack.sunbeam import SunbeamInfo
from hotsos.core.plugintools import (
    summary_entry,
    get_min_available_entry_index,
)


class SunbeamStatus(OpenstackBase, OpenStackChecks):
    """ Get information from Sunbeam to display. """
    summary_part_index = 14

    @staticmethod
    @summary_entry('sunbeam', get_min_available_entry_index() + 10)
    def summary_sunbeam():
        sunbeam = SunbeamInfo()
        if sunbeam.pods:
            return {'pods': sunbeam.pods,
                    'statefulsets': sunbeam.statefulsets}

        return None
