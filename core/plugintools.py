import os
import importlib
import yaml

from core import constants
from core.log import log


class HOTSOSDumper(yaml.Dumper):
    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)

    def represent_dict_preserve_order(self, data):
        return self.represent_dict(data.items())


def save_part(data, offset):
    """
    Save part output yaml in temporary location. These are collected and
    aggregated at the end of the plugin run.
    """
    HOTSOSDumper.add_representer(
        dict,
        HOTSOSDumper.represent_dict_preserve_order)
    out = yaml.dump(data, Dumper=HOTSOSDumper,
                    default_flow_style=False).rstrip("\n")

    parts_index = os.path.join(constants.PLUGIN_TMP_DIR, "index.yaml")
    part_path = os.path.join(constants.PLUGIN_TMP_DIR,
                             "{}.{}.part.yaml".format(constants.PLUGIN_NAME,
                                                      constants.PART_NAME))

    # don't clobber
    if os.path.exists(part_path):
        newpath = part_path
        i = 0
        while os.path.exists(newpath):
            i += 1
            newpath = "{}.{}".format(part_path, i)

        part_path = newpath

    with open(part_path, 'w') as fd:
        fd.write(out)

    index = get_parts_index()
    with open(parts_index, 'w') as fd:
        if offset in index:
            index[offset].append(part_path)
        else:
            index[offset] = [part_path]

        fd.write(yaml.dump(index))


def get_parts_index():
    parts_index = os.path.join(constants.PLUGIN_TMP_DIR, "index.yaml")
    index = {}
    if os.path.exists(parts_index):
        with open(parts_index) as fd:
            index = yaml.safe_load(fd.read()) or {}

    return index


def meld_part_output(data, existing):
    """
    Don't allow root level keys to be clobbered, instead just
    update them. This assumes that part subkeys will be unique.
    """
    remove_keys = []
    for key in data:
        if key in existing:
            if type(existing[key]) == dict:
                existing[key].update(data[key])
                remove_keys.append(key)

    if remove_keys:
        for key in remove_keys:
            del data[key]

    existing.update(data)


def collect_all_parts(index):
    parts = {}
    for offset in sorted(index):
        for part in index[offset]:
            with open(part) as fd:
                part_yaml = yaml.safe_load(fd)

                # Don't allow root level keys to be clobbered, instead just
                # update them. This assumes that part subkeys will be unique.
                meld_part_output(part_yaml, parts)

    return parts


def dump_all_parts():
    index = get_parts_index()
    if not index:
        return

    parts = collect_all_parts(index)
    if not parts:
        return

    plugin_master = {constants.PLUGIN_NAME: parts}
    HOTSOSDumper.add_representer(
        dict,
        HOTSOSDumper.represent_dict_preserve_order)
    out = yaml.dump(plugin_master, Dumper=HOTSOSDumper,
                    default_flow_style=False).rstrip("\n")
    print(out)


def dump(data, stdout=True):
    HOTSOSDumper.add_representer(
        dict,
        HOTSOSDumper.represent_dict_preserve_order)
    out = yaml.dump(data, Dumper=HOTSOSDumper,
                    default_flow_style=False).rstrip("\n")
    if stdout:
        print(out)
    else:
        return out


class ApplicationBase(object):

    @property
    def bind_interfaces(self):
        """Implement this method to return a dict of network interfaces used
        by this application.
        """
        raise NotImplementedError


def summary_entry_offset(offset):
    def _inner(f):
        def _inner2(*args, **kwargs):
            out = f(*args, **kwargs)
            if out is not None:
                return {'data': out, 'offset': offset}

        return _inner2
    return _inner


class SummaryEntry(object):

    def __init__(self, data, offset):
        self.data = data
        self.offset = offset

    @staticmethod
    def is_raw_entry(entry):
        if type(entry) != dict:
            return False

        if set(entry.keys()).symmetric_difference(['data', 'offset']):
            return False

        return True


class PluginPartBase(ApplicationBase):
    # max per part before overlap
    PLUGIN_PART_OFFSET_MAX = 500

    def __init__(self, *args, **kwargs):
        plugin_tmp = constants.PLUGIN_TMP_DIR
        if not plugin_tmp or not os.path.isdir(plugin_tmp):
            raise Exception("plugin PLUGIN_TMP_DIR not initialised - exiting")

        super().__init__(*args, **kwargs)

    @property
    def plugin_runnable(self):
        """
        Must be implemented by all plugins to define at runtime whether they
        should run.
        """
        raise NotImplementedError

    @property
    def summary_subkey(self):
        """
        This can be optionally implemented in order to have all output of the
        current part placed under the keyname provided by this property i.e.
        <plugin_name>: <subkey>: ...
        """
        return None

    @property
    def summary(self):
        """
        This can be optionally implemented as a way of pushing all results into
        the summary root for the current plugin part.

        The alternative is to implement methods called __summary_<key> such
        that the returned value is placed under <key>.
        """
        return None

    @property
    def output(self):
        _output = {}
        if self.summary:
            for key, data in self.summary.items():
                _output[key] = SummaryEntry(data, 0)

        for m in dir(self.__class__):
            cls = self.__class__.__name__
            if m.startswith('_{}__summary_'.format(cls)):
                key = m.partition('_{}__summary_'.format(cls))[2]
                key = key.replace('_', '-')
                out = getattr(self, m)()
                if not out:
                    continue

                if SummaryEntry.is_raw_entry(out):
                    out = SummaryEntry(out['data'], out['offset'])
                else:
                    # put at the end
                    out = SummaryEntry(out, self.PLUGIN_PART_OFFSET_MAX - 1)

                _output[key] = out

        return _output

    @property
    def raw_output(self):
        out = self.output
        if out:
            return {key: entry.data for key, entry in out.items()}

    def __call__(self):
        pass


class PluginRunner(object):

    def run_parts(self, parts, debug_mode=False):
        failed_parts = []
        # The following are executed as part of each plugin run (but not last).
        ALWAYS_RUN = {'auto_bug_check':
                      {'core.ycheck.bugs': 'YBugChecker'},
                      'auto_scenario_check':
                      {'core.ycheck.scenarios': 'YScenarioChecker'}}
        for name, always_parts in ALWAYS_RUN.items():
            for obj, cls in always_parts.items():
                # update current env to reflect actual part being run
                os.environ['PART_NAME'] = name
                part_obj = getattr(importlib.import_module(obj), cls)
                try:
                    part_obj()()
                except Exception as exc:
                    failed_parts.append(name)
                    log.exception("part '%s' raised exception: %s", name, exc)
                    if debug_mode:
                        raise

                # NOTE: we don't expect these parts to produce any output
                # for the summary so we wont check for it (the only raise
                # issues and bugs which are handled independently).

        for name, part_info in parts.items():
            # update current env to reflect actual part being run
            os.environ['PART_NAME'] = name
            for cls in part_info['objects']:
                inst = cls()
                # Only run plugin if it delares itself runnable.
                if not inst.plugin_runnable:
                    log.debug("%s.%s.%s not runnable - skipping",
                              constants.PLUGIN_NAME, name, cls.__name__)
                    continue

                log.debug("running %s.%s.%s",
                          constants.PLUGIN_NAME, name, cls.__name__)
                try:
                    inst()
                    # NOTE: since all parts are expected to be implementations
                    # of PluginPartBase we expect them to always define an
                    # output property.
                    output = inst.output
                    subkey = inst.summary_subkey
                except Exception as exc:
                    failed_parts.append(name)
                    log.exception("part '%s' raised exception: %s", name, exc)
                    output = None
                    if debug_mode:
                        raise

                if output:
                    for key, entry in output.items():
                        out = {key: entry.data}
                        if subkey:
                            out = {subkey: out}

                        part_max = PluginPartBase.PLUGIN_PART_OFFSET_MAX
                        part_offset = part_info['part_yaml_offset']
                        offset = ((part_offset * part_max) + entry.offset)
                        save_part(out, offset=offset)

        if failed_parts:
            # always put these at the top
            save_part({'failed-parts': failed_parts}, offset=0)

        # The following are executed at the end of each plugin run (i.e. after
        # all other parts have run).
        FINAL_RUN = {'core.plugins.utils.known_bugs_and_issues':
                     'KnownBugsAndIssuesCollector'}
        for obj, cls in FINAL_RUN.items():
            getattr(importlib.import_module(obj), cls)()()
