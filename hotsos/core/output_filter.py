#!/usr/bin/python3
import html
import json

from hotsos.core import plugintools
from hotsos.core.issues import IssuesManager
from hotsos.core.log import log

FILTER_SCHEMA = [IssuesManager.SUMMARY_OUT_ISSUES_ROOT,
                 IssuesManager.SUMMARY_OUT_BUGS_ROOT]


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
                    if key == IssuesManager.SUMMARY_OUT_ISSUES_ROOT:
                        aggr_info = {}
                    else:
                        aggr_info = []

                    for item in items:
                        if key == IssuesManager.SUMMARY_OUT_ISSUES_ROOT:
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


def minimise_master_output(summary_yaml, mode):
    """ Converts the master output to include issues and bugs. """

    log.debug("Minimising output (mode=%s).", mode)
    if not summary_yaml:
        return summary_yaml

    filtered = {}
    if mode == 'short':
        filtered = _get_short_format(summary_yaml)
    elif mode == 'very-short':
        filtered = _get_very_short_format(summary_yaml)
    else:
        log.debug("Unknown minimalmode '%s'", mode)
        return summary_yaml

    return filtered


def apply_output_formatting(summary_yaml, format, html_escape=False,
                            minimal_mode=None):
    filtered = summary_yaml

    if minimal_mode:
        filtered = minimise_master_output(filtered, minimal_mode)

    if format == 'json':
        log.debug('Converting master yaml file to %s', format)
        filtered = json.dumps(filtered, indent=2, sort_keys=True)
    else:
        filtered = plugintools.dump(filtered)

    if html_escape:
        log.debug('Encoding output file to html')
        filtered = html.escape(filtered)

    return filtered
