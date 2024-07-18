import abc


# pylint: disable-next= too-few-public-methods
class FactoryBase(abc.ABC):
    """
    Provide a common way to implement factory objects.

    The basic idea is that implementations of this class are instantiated and
    then content is generated using attrs as input. This provides a way e.g. to
    defer operations on a set of data that need only be retrieved once.
    """

    @abc.abstractmethod
    def __getattr__(self, name):
        """
        All factory implementations must implement this method to
        allow them to dynamically generate objects from arbitrary input
        provided by calling as an attribute on this object.
        """
