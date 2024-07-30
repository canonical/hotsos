# pylint: disable=too-few-public-methods

import abc


class IssueTypeBase():
    """ Base class for all implementations for issue type. """
    ISSUE_TYPE = 'issue'

    def __init__(self, msg):
        self.msg = msg

    @property
    def name(self):
        return self.__class__.__name__


class BugTypeBase(abc.ABC, IssueTypeBase):
    """ Base class for issues related to bugs. """
    ISSUE_TYPE = 'bug'

    def __init__(self, bug_id, msg):
        super().__init__(msg)
        self.id = bug_id

    @property
    @abc.abstractmethod
    def base_url(self):
        pass

    @property
    @abc.abstractmethod
    def url(self):
        pass


class CVETypeBase(BugTypeBase):
    """ Base class for issues related to CVE bugs. """
    ISSUE_TYPE = 'cve'


class HotSOSScenariosWarning(IssueTypeBase):
    """ Issue raised when one or more scenario failed to run.  """


class SystemWarning(IssueTypeBase):
    """ Issue for system level warnings. """


class KernelError(IssueTypeBase):
    """ Issue for kernel level errors. """


class KernelWarning(IssueTypeBase):
    """ Issue for kernel level warnings. """


class MemoryWarning(IssueTypeBase):
    """ Issue for memory warnings. """


class CephWarning(IssueTypeBase):
    """ Issue for ceph warnings. """


class CephHealthWarning(IssueTypeBase):
    """ Issue for Ceph cluster health warnings. """


class CephCrushWarning(IssueTypeBase):
    """ Issue for Ceph cluster CRUSH warnings. """


class CephCrushError(IssueTypeBase):
    """ Issue for Ceph cluster CRUSH errors. """


class CephOSDError(IssueTypeBase):
    """ Issue for Ceph osd errors. """


class CephOSDWarning(IssueTypeBase):
    """ Issue for Ceph osd warnings. """


class CephMonWarning(IssueTypeBase):
    """ Issue for Ceph mon warnings. """


class CephMapsWarning(IssueTypeBase):
    """ Issue for Ceph maps warnings. """


class CephMgrError(IssueTypeBase):
    """ Issue for Ceph mgr errors. """


class CephRGWWarning(IssueTypeBase):
    """ Issue for Ceph RGW warnings. """


class CephDaemonWarning(IssueTypeBase):
    """ Issue for Ceph daemon warnings. """


class CephDaemonVersionsError(IssueTypeBase):
    """ Issue for Ceph daemon versions error. """


class JujuWarning(IssueTypeBase):
    """ Issue for Juju warnings. """


class BcacheWarning(IssueTypeBase):
    """ Issue for Bcache warnings. """


class NeutronL3HAWarning(IssueTypeBase):
    """ Issue for Neutron L3HA warnings. """


class NetworkWarning(IssueTypeBase):
    """ Issue for network warnings. """


class NFSNameResolutionError(IssueTypeBase):
    """ Issue for NFS name resolution. """


class RabbitMQWarning(IssueTypeBase):
    """ Issue for RabbitMQ warnings. """


class OpenstackWarning(IssueTypeBase):
    """ Issue for Openstack warnings. """


class OVNError(IssueTypeBase):
    """ Issue for OpenvSwitch OVN errors. """


class OVNWarning(IssueTypeBase):
    """ Issue for OpenvSwitch OVN warnings. """


class OpenvSwitchWarning(IssueTypeBase):
    """ Issue for OpenvSwitch OVN errors. """


class SOSReportWarning(IssueTypeBase):
    """ Issue for SOSReport warnings. """


class SysCtlWarning(IssueTypeBase):
    """ Issue for SYSCtl warnings. """


class OpenstackError(IssueTypeBase):
    """ Issue for Openstack errors. """


class KubernetesWarning(IssueTypeBase):
    """ Issue for Kubernetes warnings. """


class PacemakerWarning(IssueTypeBase):
    """ Issue for Pacemaker warnings. """


class MySQLWarning(IssueTypeBase):
    """ Issue for MYSQL warnings. """


class LXDWarning(IssueTypeBase):
    """ Issue for LXD warnings. """


class MAASWarning(IssueTypeBase):
    """ Issue for MAAS warnings. """


class VaultWarning(IssueTypeBase):
    """ Issue for Vault warnings. """


class SSSDWarning(IssueTypeBase):
    """ Issue for SSSD warnings. """


class UbuntuCVE(CVETypeBase):
    """ Ubuntu CVE bug type """
    @property
    def base_url(self):
        return 'https://ubuntu.com/security/'

    @property
    def url(self):
        return f"{self.base_url}{self.id}"


class MitreCVE(CVETypeBase):
    """ Mitre CVE bug type """
    @property
    def base_url(self):
        return 'https://www.cve.org/CVERecord?id='

    @property
    def url(self):
        return f"{self.base_url}{self.id}"


class LaunchpadBug(BugTypeBase):
    """ Launchpad bug type """
    @property
    def base_url(self):
        return 'https://bugs.launchpad.net/bugs/'

    @property
    def url(self):
        return f"{self.base_url}{self.id}"


class Bugzilla(BugTypeBase):
    """ Bugzilla bug type """
    @property
    def base_url(self):
        return 'https://bugzilla.redhat.com/show_bug.cgi?id='

    @property
    def url(self):
        return f"{self.base_url}{self.id}"


class StoryBoardBug(BugTypeBase):
    """ Storyboard bug type """
    @property
    def base_url(self):
        return 'https://storyboard.openstack.org/#!/story/'

    @property
    def url(self):
        return f"{self.base_url}{self.id}"


class CephTrackerBug(BugTypeBase):
    """ Ceph tracker bug type """
    @property
    def base_url(self):
        return 'https://tracker.ceph.com/issues/'

    @property
    def url(self):
        return f"{self.base_url}{self.id}"
