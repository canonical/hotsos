class HotSOSConfigMeta(type):
    DEFAULTS = {'MAX_PARALLEL_TASKS': 8,
                'MAX_LOGROTATE_DEPTH': 7,
                'USE_ALL_LOGS': False,
                'MACHINE_READABLE': False}

    def __getattr__(cls, key):
        if key not in cls.CONFIG:
            if key in cls.DEFAULTS:
                return cls.DEFAULTS[key]

            return None

        return cls.CONFIG.get(key)


class HotSOSConfig(object, metaclass=HotSOSConfigMeta):
    CONFIG = {}

    @classmethod
    def reset(cls):
        cls.CONFIG = {}

    @classmethod
    def set(cls, key, val):
        cls.CONFIG[key] = val


def setup_config(**kwargs):
    for k, v in kwargs.items():
        HotSOSConfig.set(k, v)
