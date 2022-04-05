import abc


class BugTypeBase(abc.ABC):
    def __init__(self, id, msg):
        self.name = self.__class__.__name__
        self.id = id
        self.msg = msg

    @abc.abstractproperty
    def base_url(self):
        pass

    @abc.abstractproperty
    def url(self):
        pass


class LaunchpadBug(BugTypeBase):

    @property
    def base_url(self):
        return 'https://bugs.launchpad.net/bugs/'

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
