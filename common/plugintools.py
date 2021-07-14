import os
import importlib
import yaml

from common import constants


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


def collect_all_parts(index):
    parts = {}
    for priority in sorted(index):
        for part in index[priority]:
            with open(part) as fd:
                part_yaml = yaml.safe_load(fd)
                parts.update(part_yaml)

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


class PluginPartBase(object):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._output = {}

    @property
    def output(self):
        if self._output:
            return self._output


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

        plugins = yaml_defs.get("plugins", {})
        plugin = plugins.get(constants.PLUGIN_NAME, {})
        parts = plugin.get("parts", {})
        for part in parts:
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
            for entry in parts[part] or []:
                if type(parts[part]) == list:
                    obj = getattr(mod, entry)
                    inst = obj()
                    inst()
                else:
                    cls_name = entry
                    cls = getattr(mod, cls_name)
                    inst = cls()

                    methods = parts[part][cls_name].get("methods", [])
                    # Only call __class__ of methods are NOT explicitly
                    # defined.
                    if not methods:
                        if hasattr(inst, "__call__"):
                            inst()
                        else:
                            raise Exception("expected to find a __call__ "
                                            "method in class {} but did not "
                                            "find one".format(cls_name))
                    else:
                        for method_name in methods:
                            method = getattr(inst, method_name)
                            method()

                if hasattr(inst, "output"):
                    out = inst.output
                    if out:
                        part_out.update(out)

            save_part(part_out, priority=yaml_priority)

        # Always execute this as last part
        mod_string = "common.plugins.utils.known_bugs_and_issues"
        mod = importlib.import_module(mod_string)
        mod.KnownBugsAndIssuesCollector()()
