from hotsos.core.plugins.storage import StorageBase


class SmartctlChecks(StorageBase):
    """Base class for smartctl storage checks."""
    @classmethod
    def is_runnable(cls):
        # Implement logic to determine if smartctl checks should run.
        # For now, always returns True.
        return True
