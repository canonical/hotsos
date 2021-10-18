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


def save_part(data, priority=0):
    """
    Save part output yaml in temporary location. These are collected and
    aggregrated at the end of the plugin run.
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
        if priority in index:
            index[priority].append(part_path)
        else:
            index[priority] = [part_path]

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
    for priority in sorted(index):
        for part in index[priority]:
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


class PluginPartBase(ApplicationBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._output = {}

    @property
    def plugin_runnable(self):
        """
        Must be implemented by all plugins to define at runtime whether they
        should run.
        """
        raise NotImplementedError

    @property
    def output(self):
        if self._output:
            return self._output

    def __call__(self):
        """ This must be implemented.

        The plugin runner will call this method by default unless specific
        methods are defined in the plugin definition (yaml).
        """
        raise NotImplementedError


class PluginRunner(object):

    def __call__(self):
        """
        Fetch definition for current plugin and execute each of its parts. See
        definitions file at defs/plugins.yaml for information on supported
        format.
        """
        path = os.path.join(constants.PLUGIN_YAML_DEFS, "plugins.yaml")
        with open(path) as fd:
            yaml_defs = yaml.safe_load(fd.read())

        if not yaml_defs:
            return

        failed_parts = []
        plugins = yaml_defs.get("plugins", {})
        plugin = plugins.get(constants.PLUGIN_NAME, {})
        parts = plugin.get("parts", {})
        if not parts:
            log.debug("plugin %s has no parts to run", constants.PLUGIN_NAME)

        # The following are executed as part of each plugin run (but not last).
        ALWAYS_RUN = {'default_bug_checker':
                      {'core.checks': 'BugChecksBase'}}
        for part, parts in ALWAYS_RUN.items():
            for obj, cls in parts.items():
                # update current env to reflect actual part being run
                os.environ['PART_NAME'] = part
                part_obj = getattr(importlib.import_module(obj), cls)
                try:
                    part_obj()()
                except Exception as exc:
                    failed_parts.append(part)
                    log.debug("part '%s' raised exception: %s", part, exc)
                    if constants.DEBUG_MODE:
                        raise

                # NOTE: we don't currently expect these parts to produce any
                # output.

        for part, obj_names in plugin.get("parts", {}).items():
            # update current env to reflect actual part being run
            os.environ['PART_NAME'] = part
            mod_string = ('plugins.{}.pyparts.{}'.
                          format(constants.PLUGIN_NAME, part))
            # load part
            mod = importlib.import_module(mod_string)
            # every part should have a yaml priority defined
            if hasattr(mod, "YAML_PRIORITY"):
                yaml_priority = getattr(mod, "YAML_PRIORITY")
            else:
                yaml_priority = 0

            part_out = {}
            for entry in obj_names or []:
                part_obj = getattr(mod, entry)()
                # Only run plugin if it delares itself runnable.
                if not part_obj.plugin_runnable:
                    log.debug("plugin=%s, part=%s not runnable - skipping",
                              constants.PLUGIN_NAME, part)
                    continue

                log.debug("running plugin=%s, part=%s",
                          constants.PLUGIN_NAME, part)
                try:
                    part_obj()
                    # NOTE: since all parts are expected to be implementations
                    # of PluginPartBase we expect them to always define an
                    # output property.
                    output = part_obj.output
                except Exception as exc:
                    failed_parts.append(part)
                    log.debug("part '%s' raised exception: %s", part, exc)
                    output = None
                    if constants.DEBUG_MODE:
                        raise

                if output:
                    meld_part_output(output, part_out)

            save_part(part_out, priority=yaml_priority)

        if failed_parts:
            save_part({'failed-parts': failed_parts}, priority=0)

        # The following are executed at the end of each plugin run (i.e. after
        # all other parts have run).
        FINAL_RUN = {'core.plugins.utils.known_bugs_and_issues':
                     'KnownBugsAndIssuesCollector'}
        for obj, cls in FINAL_RUN.items():
            getattr(importlib.import_module(obj), cls)()()
