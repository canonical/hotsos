#!/usr/bin/python3
import html
import json
import yaml

from core.issues.utils import MASTER_YAML_ISSUES_FOUND_KEY
from core.issues.bugs import MASTER_YAML_KNOWN_BUGS_KEY
from core.log import log
from core import (
    constants,
    plugintools,
)

FILTER_SCHEMA = [MASTER_YAML_ISSUES_FOUND_KEY, MASTER_YAML_KNOWN_BUGS_KEY]


def _get_short_format(master_yaml):
    filtered = {}
    for plugin in master_yaml:
        for key in FILTER_SCHEMA:
            if key in master_yaml[plugin]:
                if key not in filtered:
                    filtered[key] = {}

                items = master_yaml[plugin][key]
                filtered[key][plugin] = items

    return filtered


def _get_very_short_format(master_yaml):
    filtered = {}
    for plugin in master_yaml:
        for key in FILTER_SCHEMA:
            if key in master_yaml[plugin]:
                if key not in filtered:
                    filtered[key] = {}

                items = master_yaml[plugin][key]
                if type(items) == dict:
                    filtered[key][plugin] = {key: len(val)
                                             for key, val in items.items()}
                else:
                    # support old format summaries
                    if key == MASTER_YAML_ISSUES_FOUND_KEY:
                        aggr_info = {}
                    else:
                        aggr_info = []

                    for item in items:
                        if key == MASTER_YAML_ISSUES_FOUND_KEY:
                            item_key = item['type']
                            if item_key not in aggr_info:
                                aggr_info[item_key] = 1
                            else:
                                aggr_info[item_key] += 1

                        else:
                            item_key = item['id']
                            aggr_info.append(item_key)

                    filtered[key][plugin] = aggr_info

    return filtered


def minimise_master_output(mode):
    """ Converts the master output to include issues and bugs. """

    log.debug("Minimising output (mode=%s).", mode)
    with open(constants.MASTER_YAML_OUT) as fd:
        master_yaml = yaml.safe_load(fd)

    if mode == 'short':
        filtered = _get_short_format(master_yaml)
    elif mode == 'very-short':
        filtered = _get_very_short_format(master_yaml)
    else:
        log.debug("Unknown minimalmode '%s'", mode)
        return

    with open(constants.MASTER_YAML_OUT, 'w') as fd:
        if filtered:
            fd.write(plugintools.dump(filtered, stdout=False))
            fd.write("\n")
        else:
            fd.write("")


def convert_output_to_json():
    """ Convert the default yaml output to json. """
    with open(constants.MASTER_YAML_OUT, encoding='utf-8') as fd:
        master_yaml = yaml.safe_load(fd)
        with open(constants.MASTER_YAML_OUT, 'w', encoding='utf-8') as fd:
            fd.write(json.dumps(master_yaml, indent=2, sort_keys=True))


def encode_output_to_html():
    with open(constants.MASTER_YAML_OUT, encoding='utf-8') as fd:
        master_yaml = fd.read()
        with open(constants.MASTER_YAML_OUT, 'w', encoding='utf-8') as fd:
            fd.write(html.escape(master_yaml))


if __name__ == "__main__":
    if constants.MINIMAL_MODE:
        minimise_master_output(constants.MINIMAL_MODE)

    if constants.OUTPUT_FORMAT == 'json':
        log.debug('Converting master yaml file to %s', constants.OUTPUT_FORMAT)
        convert_output_to_json()

    if constants.OUTPUT_ENCODING == 'html':
        log.debug('Encoding output file to %s', constants.OUTPUT_ENCODING)
        encode_output_to_html()
