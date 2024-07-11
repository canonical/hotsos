class ScenarioException(Exception):
    """ Generic exception used with Scenarios. """


class UnsupportedFormatError(Exception):
    """Raised when a value is not in the expected format."""


class InvalidFileFormatError(Exception):
    """Raised when a file's format is not in the expected format."""


class MismatchError(Exception):
    """Generic mismatch exception type."""


class NameAlreadyRegisteredError(Exception):
    """Raised when a given name is already registered in an entity."""


class InvalidPathError(Exception):
    """Raised when a path is invalid."""


class NameNotSetError(Exception):
    """Raised when the name for an entity is absent."""


class AlreadyLoadedError(Exception):
    """Raised when an entity is expected to be loaded only once, but the load
    operation is called again."""


class NotEnoughParametersError(Exception):
    """Raised when an operation did not get enough parameters to operate."""


class MissingRequiredParameterError(Exception):
    """Raised when an operation did not get a parameter required
     for the operation."""


class UnexpectedParameterError(Exception):
    """Raised when an operation did get an unexpected parameter."""


class NoCallbacksRegisteredError(Exception):
    """Raised when a callback-based entity does not have a callback
    registered."""


class NotYetInitializedError(Exception):
    """Raised when an entity is not initialized where it already must be."""


class PreconditionError(Exception):
    """Raised when an operation's precondition is not met."""


class ExpectationNotMetError(Exception):
    """Raised when an operation's expectation is not met."""
