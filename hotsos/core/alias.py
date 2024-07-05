"""Aliasing utilities."""

from hotsos.core.log import log


class AliasAlreadyInUseError(Exception):
    """Raised when an alias is already in use."""

    def __init__(self, name):
        self.message = f"Alias '{name}` already in use!"

    def __str__(self):
        return self.message


class AliasForbiddenError(Exception):
    """Raised when an alias is forbidden to use."""

    def __init__(self, name):
        self.message = f"Alias '{name}` is forbidden!"

    def __str__(self):
        return self.message


class AliasRegistry:
    """
    A class that provides a registry for aliasing Python things.
    """

    # A class-level dictionary to store registered aliases.
    registry = {}

    @staticmethod
    def register(name, decoratee):
        """
        Register a function, method, or property under an alias.

        This method handles different types of Python objects and creates
        appropriate wrappers or registrations based on the object type.

        Args:
            name (str): The alias under which to register the decoratee.
            decoratee (callable or property): The Python object to be
            registered.

        Raises:
            AliasAlreadyInUseError: If the alias name is already registered.
            AliasForbiddenError: If the alias name starts with "hotsos."
        """
        isprop = isinstance(decoratee, property)
        target = decoratee.fget if isprop else decoratee

        if name.startswith("hotsos."):
            raise AliasForbiddenError(name)

        if name in AliasRegistry.registry:
            log.debug("alias registration failed -- already in use(`%s`)",
                      name)
            raise AliasAlreadyInUseError(name)

        import_path = f"{target.__module__}.{target.__qualname__}"
        log.debug("registering alias `%s` --> {%s}", name, import_path)
        # Register full import path.
        AliasRegistry.registry[name] = import_path

    @staticmethod
    def resolve(the_alias, default=None):
        """
        Retrieve a registered alias.

        Args:
            the_alias (str): The alias to retrieve.

        Returns:
            callable: The function or wrapper associated with the alias.

        Raises:
            NoSuchAliasError: No such alias in the registry.
        """

        if the_alias not in AliasRegistry.registry:
            log.debug(
                "alias `%s` not found in the registry, "
                "returning the default value",
                the_alias,
            )
            return default

        value = AliasRegistry.registry[the_alias]
        log.debug("alias %s resolved to %s", the_alias, value)
        return value


def alias(argument):
    """Create an alias for a property, function or a thing."""

    def real_decorator(func):
        """We're not wrapping the func as we don't want
        to do anything at runtime. We just want to alias
        `func` to some user-defined name and call it on-demand."""
        AliasRegistry.register(argument, func)
        return func

    return real_decorator
