import os

from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers import SYSCtlConfHelper
from hotsos.core.plugins.system import SystemChecks
from hotsos.core.plugintools import summary_entry


class SYSCtlChecks(SystemChecks):
    """ System sysctl checker.

    Checks system sysctl state.
    """
    summary_part_index = 1

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cached_fs_sysctl = None

    @staticmethod
    def _get_values_prioritised(config, key_priorities, conffile):
        """
        Run through all key/value pairs from this config set and only keep ones
        that have not yet been supersceded by another file.

        @param config: dict if key/value pairs
        @param key_priorities: dict if found keys and the highest priority
                               attributed to them.
        @param conffile: the name of the conf file these settings are from.
                         None implies infinite priority i.e. /etc/sysctl.conf
        """
        kv_conf = {}
        for key, value in config.items():
            if conffile and key in key_priorities:
                if key_priorities[key] >= conffile:
                    continue

            key_priorities[key] = conffile
            kv_conf[key] = (value, conffile)

        return kv_conf

    def _get_charm_sysctl_d(self):
        """ Collect all key/value pairs defined under /etc/sysctl.d that were
        written by a charm.
        """
        config = {'set': {},
                  'unset': {}}

        path = os.path.join(HotSOSConfig.data_root, 'etc/sysctl.d')
        if not os.path.isdir(path):
            return config

        conffiles = ['50-ceph-osd-charm.conf',
                     '50-nova-compute.conf',
                     '50-openvswitch.conf',
                     '50-swift-storage-charm.conf',
                     '50-quantum-gateway.conf']
        key_priorities = {}
        for conffile in sorted(conffiles):
            sysctl = SYSCtlConfHelper(os.path.join(path, conffile))
            _set = self._get_values_prioritised(sysctl.setters,
                                                key_priorities,
                                                conffile)
            config['set'].update(_set)
            _unset = self._get_values_prioritised(sysctl.unsetters,
                                                  key_priorities,
                                                  conffile)
            config['unset'].update(_unset)

        return config

    def _get_sysctl_conf(self):
        config = {'set': {},
                  'unset': {}}
        path = os.path.join(HotSOSConfig.data_root, 'etc/sysctl.conf')
        if not os.path.exists(path):
            return config

        sysctl = SYSCtlConfHelper(path)
        config['set'] = self._get_values_prioritised(sysctl.setters, {}, None)
        config['unset'] = self._get_values_prioritised(sysctl.unsetters, {},
                                                       None)
        return config

    def _get_sysctl_d(self):
        """ Collect all key/value pairs defined under /etc/sysctl.d and keep
        the highest priority value for any given key.

        man sysctld specifies that the following locations are searched for
        config so we will include these:

            * /etc/sysctl.d
            * /usr/lib/sysctl.d
            * /run/sysctl.d
        """
        key_priorities = {}
        config = {'set': {},
                  'unset': {}}
        for location in ['etc', 'usr/lib', 'run']:
            path = os.path.join(HotSOSConfig.data_root, location, 'sysctl.d')
            if not os.path.isdir(path):
                continue

            for conffile in os.listdir(path):
                # Only files ending in .conf are recognised by sysctl so don't
                # count content of other files as expected.
                if not conffile.endswith('.conf'):
                    continue

                sysctl = SYSCtlConfHelper(os.path.join(path, conffile))
                _set = self._get_values_prioritised(sysctl.setters,
                                                    key_priorities,
                                                    conffile)
                config['set'].update(_set)
                _unset = self._get_values_prioritised(sysctl.unsetters,
                                                      key_priorities,
                                                      conffile)
                config['unset'].update(_unset)

        return config

    def _get_fs_sysctl(self):
        if self._cached_fs_sysctl:
            return self._cached_fs_sysctl

        sysctl = self._get_sysctl_d()
        # /etc/sysctl.conf overrides all
        _sysctl = self._get_sysctl_conf()
        sysctl['set'].update(_sysctl['set'])
        sysctl['unset'].update(_sysctl['unset'])
        self._cached_fs_sysctl = sysctl
        return self._cached_fs_sysctl

    @summary_entry('sysctl-mismatch', 10)
    def summary_sysctl_mismatch(self):
        """ Compare the values for any key set under sysctl.d and report
        an issue if any mismatches detected.
        """
        sysctl = self._get_fs_sysctl()
        mismatch = {}
        for key, config in sysctl['set'].items():
            # some keys will not be readable e.g. when inside an unprivileged
            # container so we just ignore them.
            value = config[0]
            if key in sysctl['unset']:
                s_priority = config[1]
                u_priority = sysctl['unset'][key][1]
                # None priority implies infinite or /etc/sysctl.conf
                if (s_priority is None or u_priority is None or
                        u_priority > s_priority):
                    continue

            if value != self.sysctl_all.get(key, value):
                mismatch[key] = {"actual": self.sysctl_all[key],
                                 "expected": value}

        return mismatch or None

    @summary_entry('juju-charm-sysctl-mismatch', 11)
    def summary_juju_charm_sysctl_mismatch(self):
        """ Compare the values for any key set under sysctl.d and report
        an issue if any mismatches detected.
        """
        sysctl = self._get_fs_sysctl()
        mismatch = {}
        sysctl = self._get_charm_sysctl_d()
        for key, config in sysctl['set'].items():
            value = config[0]
            if value != self.sysctl_all.get(key):
                mismatch[key] = {"conf": config[1],
                                 "actual": self.sysctl_all.get(key),
                                 "expected": value}

        return mismatch or None
