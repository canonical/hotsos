from hotsos.core.host_helpers.cli.commands import kubectl
from hotsos.core.issues import IssuesManager, OpenstackWarning
from hotsos.core.plugins.openstack.common import (
    OpenstackBase,
    OpenStackChecks,
)
from hotsos.core.plugins.openstack.sunbeam import SunbeamInfo
from hotsos.core.plugins.sosreport import SOSReportBase
from hotsos.core.plugintools import (
    summary_entry,
    get_min_available_entry_index,
)


class SunbeamStatus(OpenstackBase, OpenStackChecks):
    """ Get information from Sunbeam to display. """
    summary_part_index = 15

    @staticmethod
    @summary_entry('sunbeam', get_min_available_entry_index() + 10)
    def summary_sunbeam():
        """Return Sunbeam pod and statefulset info."""
        sunbeam = SunbeamInfo()
        if sunbeam.pods:
            return {'pods': sunbeam.pods,
                    'statefulsets': sunbeam.statefulsets}

        if (sunbeam.is_controller and not
                SOSReportBase().data_root_is_sosreport):
            IssuesManager().add(OpenstackWarning(
                "this host is a sunbeam controller but no kubernetes data "
                "was found - kubectl may have failed (does "
                f"{kubectl.DEFAULT_CFG_PATH} exist? - if not you can try "
                "setting the KUBECONFIG env var to a valid path)"))

        return None
