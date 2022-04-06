class HotSOSConfigMeta(type):

    def __getattr__(cls, key):
        val = cls.CONFIG.get(key)
        return val


class HotSOSConfig(object, metaclass=HotSOSConfigMeta):
    CONFIG = {'MAX_PARALLEL_TASKS': 8,
              'MAX_LOGROTATE_DEPTH': 7,
              'USE_ALL_LOGS': False,
              'MACHINE_READABLE': False,
              }

    @classmethod
    def set(cls, key, val):
        cls.CONFIG[key] = val


def setup_config(**kwargs):
    for k, v in kwargs.items():
        HotSOSConfig.set(k, v)
