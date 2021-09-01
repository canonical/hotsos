import os


class constants_properties(type):
    """
    Required to allow constants class to be used as if each attribute is a
    @classmethod + @property.
    """

    @property
    def DATA_ROOT(cls):
        return cls._DATA_ROOT()

    @property
    def MASTER_YAML_OUT(cls):
        return cls._MASTER_YAML_OUT()

    @property
    def PLUGIN_TMP_DIR(cls):
        return cls._PLUGIN_TMP_DIR()

    @property
    def PLUGIN_NAME(cls):
        return cls._PLUGIN_NAME()

    @property
    def PART_NAME(cls):
        return cls._PART_NAME()

    @property
    def PLUGIN_YAML_DEFS(cls):
        return cls._PLUGIN_YAML_DEFS()

    @property
    def USE_ALL_LOGS(cls):
        return cls._USE_ALL_LOGS()

    @property
    def MAX_PARALLEL_TASKS(cls):
        return cls._MAX_PARALLEL_TASKS()

    @property
    def MAX_LOGROTATE_DEPTH(cls):
        return cls._MAX_LOGROTATE_DEPTH()


class constants(object, metaclass=constants_properties):
    """
    We use a class for constant globals to ensure they are loaded dyanmically
    which is necessry to ensure any runtime changes take effect.
    """

    @classmethod
    def bool_str(cls, val):
        if val.lower() == "true":
            return True
        elif val.lower() == "false":
            return False

        return val

    @classmethod
    def _DATA_ROOT(cls):
        return os.environ.get('DATA_ROOT', '/')

    @classmethod
    def _MASTER_YAML_OUT(cls):
        return os.environ.get('MASTER_YAML_OUT')

    @classmethod
    def _PLUGIN_TMP_DIR(cls):
        return os.environ.get('PLUGIN_TMP_DIR')

    @classmethod
    def _PLUGIN_NAME(cls):
        return os.environ.get('PLUGIN_NAME')

    @classmethod
    def _PART_NAME(cls):
        return os.environ.get('PART_NAME')

    @classmethod
    def _PLUGIN_YAML_DEFS(cls):
        return os.environ.get('PLUGIN_YAML_DEFS')

    @classmethod
    def _USE_ALL_LOGS(cls):
        if cls.bool_str(os.environ.get('USE_ALL_LOGS', 'False')):
            return True
        else:
            return False

    @classmethod
    def _MAX_PARALLEL_TASKS(cls):
        return int(os.environ.get('MAX_PARALLEL_TASKS', 8))

    @classmethod
    def _MAX_LOGROTATE_DEPTH(cls):
        return int(os.environ.get('MAX_LOGROTATE_DEPTH', 7))
