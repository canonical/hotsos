class IssueTypeBase(object):
    def __init__(self, msg):
        self.name = self.__class__.__name__
        self.msg = msg


class MemoryWarning(IssueTypeBase):
    pass


class CephCrushWarning(IssueTypeBase):
    pass


class JujuWarning(IssueTypeBase):
    pass


class BcacheWarning(IssueTypeBase):
    pass


class NeutronL3HAWarning(IssueTypeBase):
    pass


class NetworkWarning(IssueTypeBase):
    pass
