class IssueTypeBase(object):
    def __init__(self, msg):
        self.name = self.__class__.__name__
        self.msg = msg


class MemoryWarning(IssueTypeBase):
    pass
