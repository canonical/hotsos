import abc


class IssueTypeBase(object):
    ISSUE_TYPE = 'issue'

    def __init__(self, msg):
        self.msg = msg

    @property
    def name(self):
        return self.__class__.__name__


class BugTypeBase(abc.ABC, IssueTypeBase):
    ISSUE_TYPE = 'bug'

    def __init__(self, id, msg):
        self.id = id
        self.msg = msg

    @abc.abstractproperty
    def base_url(self):
        pass

    @abc.abstractproperty
    def url(self):
        pass


class HotSOSScenariosWarning(IssueTypeBase):
    pass


class SystemWarning(IssueTypeBase):
    pass


class KernelError(IssueTypeBase):
    pass


class KernelWarning(IssueTypeBase):
    pass


class MemoryWarning(IssueTypeBase):
    pass


class CephWarning(IssueTypeBase):
    pass


class CephHealthWarning(IssueTypeBase):
    pass


class CephCrushWarning(IssueTypeBase):
    pass


class CephCrushError(IssueTypeBase):
    pass


class CephOSDError(IssueTypeBase):
    pass


class CephOSDWarning(IssueTypeBase):
    pass


class CephMonWarning(IssueTypeBase):
    pass


class CephMapsWarning(IssueTypeBase):
    pass


class CephMgrError(IssueTypeBase):
    pass


class CephRGWWarning(IssueTypeBase):
    pass


class CephDaemonWarning(IssueTypeBase):
    pass


class CephDaemonVersionsError(IssueTypeBase):
    pass


class JujuWarning(IssueTypeBase):
    pass


class BcacheWarning(IssueTypeBase):
    pass


class NeutronL3HAWarning(IssueTypeBase):
    pass


class NetworkWarning(IssueTypeBase):
    pass


class RabbitMQWarning(IssueTypeBase):
    pass


class OpenstackWarning(IssueTypeBase):
    pass


class OVNError(IssueTypeBase):
    pass


class OVNWarning(IssueTypeBase):
    pass


class OpenvSwitchWarning(IssueTypeBase):
    pass


class SOSReportWarning(IssueTypeBase):
    pass


class SysCtlWarning(IssueTypeBase):
    pass


class OpenstackError(IssueTypeBase):
    pass


class KubernetesWarning(IssueTypeBase):
    pass


class PacemakerWarning(IssueTypeBase):
    pass


class MySQLWarning(IssueTypeBase):
    pass


class LXDWarning(IssueTypeBase):
    pass


class LaunchpadBug(BugTypeBase):

    @property
    def base_url(self):
        return 'https://bugs.launchpad.net/bugs/'

    @property
    def url(self):
        return "{}{}".format(self.base_url, self.id)


class Bugzilla(BugTypeBase):

    @property
    def base_url(self):
        return 'https://bugzilla.redhat.com/show_bug.cgi?id='

    @property
    def url(self):
        return "{}{}".format(self.base_url, self.id)


class StoryBoardBug(BugTypeBase):

    @property
    def base_url(self):
        return 'https://storyboard.openstack.org/#!/story/'

    @property
    def url(self):
        return "{}{}".format(self.base_url, self.id)


class CephTrackerBug(BugTypeBase):

    @property
    def base_url(self):
        return 'https://tracker.ceph.com/issues/'

    @property
    def url(self):
        return "{}{}".format(self.base_url, self.id)
