#!/usr/bin/python3
import os
import yaml

from common.constants import (
    PART_NAME,
    MASTER_YAML_OUT,
    PLUGIN_TMP_DIR,
    PLUGIN_NAME,
)


class HOTSOSDumper(yaml.Dumper):
    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)

    def represent_dict_preserve_order(self, data):
        return self.represent_dict(data.items())


def get_master_plugin_yaml(plugin):
    return yaml.safe_load(open(MASTER_YAML_OUT)).get(plugin, {})


def master_has_plugin(name):
    """Returns True if the master yaml has a top-level entry (dict key)
    with the given plugin name.
    """
    if not os.path.exists(MASTER_YAML_OUT):
        raise Exception("Master yaml path not found '{}'".
                        format(MASTER_YAML_OUT))

    master_yaml = yaml.safe_load(open(MASTER_YAML_OUT))
    return name in master_yaml


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

    parts_index = os.path.join(PLUGIN_TMP_DIR, "index.yaml")
    part_path = os.path.join(PLUGIN_TMP_DIR,
                             "{}.{}.part.yaml".format(PLUGIN_NAME, PART_NAME))
    with open(part_path, 'w') as fd:
        fd.write(out)

    index = {}
    if os.path.exists(parts_index):
        with open(parts_index) as fd:
            index = yaml.safe_load(fd.read()) or {}

    with open(parts_index, 'w') as fd:
        if priority in index:
            index[priority].append(part_path)
        else:
            index[priority] = [part_path]

        fd.write(yaml.dump(index))


def dump_all_parts():
    plugin_master = {PLUGIN_NAME: {}}
    parts_index = os.path.join(PLUGIN_TMP_DIR, "index.yaml")
    index = {}
    if os.path.exists(parts_index):
        with open(parts_index) as fd:
            index = yaml.safe_load(fd.read()) or {}

    if not index:
        return

    for priority in sorted(index):
        for part in index[priority]:
            with open(part) as fd:
                part_yaml = yaml.safe_load(fd)
                plugin_master[PLUGIN_NAME].update(part_yaml)

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
