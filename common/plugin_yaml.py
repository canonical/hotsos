#!/usr/bin/python3
import os
import yaml

from common import (
    constants
)


class HOTSOSDumper(yaml.Dumper):
    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)

    def represent_dict_preserve_order(self, data):
        return self.represent_dict(data.items())


def get_master_plugin_yaml(plugin):
    return yaml.safe_load(open(constants.MASTER_YAML_OUT)).get(plugin, {})


def master_has_plugin(name):
    """Returns True if the master yaml has a top-level entry (dict key)
    with the given plugin name.
    """
    path = os.environ.get('MASTER_YAML_OUT')
    if not os.path.exists(path):
        raise Exception("Master yaml path not found '{}'".format(path))

    master_yaml = yaml.safe_load(open(path))
    return name in master_yaml


def dump(data, indent=0):
    if not master_has_plugin(constants.PLUGIN_NAME):
        data = {constants.PLUGIN_NAME: data}
    else:
        indent = 2

    indented = []
    HOTSOSDumper.add_representer(
        dict,
        HOTSOSDumper.represent_dict_preserve_order)
    out = yaml.dump(data, Dumper=HOTSOSDumper,
                    default_flow_style=False).rstrip("\n")
    for line in out.split("\n"):
        indented.append("{}{}".format(" " * indent, line))

    print('\n'.join(indented))
