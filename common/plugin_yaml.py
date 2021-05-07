#!/usr/bin/python3
import os
import yaml

from common.constants import (
    PART_NAME,
    PLUGIN_TMP_DIR,
    PLUGIN_NAME,
)


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

    parts_index = os.path.join(PLUGIN_TMP_DIR, "index.yaml")
    part_path = os.path.join(PLUGIN_TMP_DIR,
                             "{}.{}.part.yaml".format(PLUGIN_NAME, PART_NAME))

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
    parts_index = os.path.join(PLUGIN_TMP_DIR, "index.yaml")
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

    plugin_master = {PLUGIN_NAME: parts}
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
