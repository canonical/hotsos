#!/usr/bin/python3

# Copyright (C) 2011, 2012, 2014 Canonical
# All Rights Reserved
# Author: Liam Young, Jacek Nykis

from collections import defaultdict
from datetime import datetime, timedelta
from fnmatch import fnmatchcase
from itertools import chain
import argparse
import os
import sys


lsb_dict = {}
with open("/etc/lsb-release") as f:
    lsb = [s.split("=") for s in f.readlines()]
    lsb_dict = dict([(k, v.strip()) for k, v in lsb])


def gen_data_lines(filename):
    with open(filename, "rt") as fin:
        for line in fin:
            if not line.startswith("#"):
                yield line


def gen_stats(data_lines):
    for line in data_lines:
        try:
            vhost, queue, _, _, m_all, _ = line.split(None, 5)
        except ValueError:
            print("ERROR: problem parsing the stats file")
            sys.exit(2)
        assert m_all.isdigit(), ("Message count is not a number: {0!r}"
                                 .format(m_all))
        yield vhost, queue, int(m_all)


def collate_stats(stats, limits, exclude, busiest_queues):
    # Create a dict with stats collated according to the definitions in the
    # limits file. If none of the definitions in the limits file is matched,
    # store the stat without collating.
    collated = defaultdict(lambda: 0)
    for vhost, queue, m_all in stats:
        skip = False

        for e_vhost, e_queue in exclude:
            if fnmatchcase(vhost, e_vhost) and fnmatchcase(queue, e_queue):
                skip = True
                break

        if skip:
            continue

        for l_vhost, l_queue, _, _ in limits:
            if fnmatchcase(vhost, l_vhost) and fnmatchcase(queue, l_queue):
                collated[l_vhost, l_queue] += m_all
                # Save vhost and queue names when using wildcards as arguments.
                if busiest_queues > 0:
                    collated[vhost, queue] += m_all
                break
        else:
            collated[vhost, queue] += m_all
    return collated


def check_stats(stats_collated, limits):
    # Create a limits lookup dict with keys of the form (vhost, queue).
    limits_lookup = dict(
        ((l_vhost, l_queue), (int(t_warning), int(t_critical)))
        for l_vhost, l_queue, t_warning, t_critical in limits)
    if not (stats_collated):
        yield 'No Queues Found', 'No Vhosts Found', None, "UNKNOWN"
    # Go through the stats and compare again limits, if any.
    for l_vhost, l_queue in sorted(stats_collated):
        m_all = stats_collated[l_vhost, l_queue]
        try:
            t_warning, t_critical = limits_lookup[l_vhost, l_queue]
        except KeyError:
            yield l_queue, l_vhost, m_all, "UNKNOWN"
        else:
            if m_all >= t_critical:
                yield l_queue, l_vhost, m_all, "CRIT"
            elif m_all >= t_warning:
                yield l_queue, l_vhost, m_all, "WARN"


def check_stats_file_freshness(stats_file, oldest_timestamp):
    """Check if a rabbitmq stats file is fresh

    Fresh here is defined as modified within the last 2* cron job intervals

    :param stats_file: file name to check
    :param oldest_timestamp: oldest timestamp the file can be last modified
    :return: tuple (status, message)
    """
    file_mtime = datetime.fromtimestamp(os.path.getmtime(stats_file))
    if file_mtime < oldest_timestamp:
        return (
            "CRIT",
            "Rabbit stats file not updated since {}".format(
                file_mtime
            ),
        )
    return ("OK", "")


def top_n_queues(stats, busiest_queues):
    if busiest_queues <= 0:
        return []
    tqueues = [" - Top Queues"]
    sorted_messages_stats = sorted(stats.items(),
                                   key=lambda y: y[1],
                                   reverse=True)
    for stat in sorted_messages_stats[:busiest_queues]:
        tqueues.append("{0}:{1} -> {2}".format(stat[0][0],  # vhost
                                               stat[0][1],  # queue
                                               stat[1]))    # messages
    return tqueues


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='RabbitMQ queue size nagios check.')
    parser.add_argument(
        '-c',
        nargs=4,
        action='append',
        required=True,
        metavar=('vhost', 'queue', 'warn', 'crit'),
        help='Vhost and queue to check. Can be used multiple times'
    )
    parser.add_argument(
        '-e',
        nargs=2,
        action='append',
        required=False,
        default=[],
        metavar=('vhost', 'queue'),
        help=(
            'Vhost and queue to exclude from checks. Can be used multiple '
            'times'
        )
    )
    parser.add_argument(
        '-m',
        nargs='?',
        action='store',
        required=False,
        default=0,
        type=int,
        help=(
            'Maximum age (in seconds) the stats files can be before a crit is '
            'raised'
        )
    )
    parser.add_argument(
        '-d',
        type=int,
        required=False,
        default=0,
        metavar=('n'),
        help='Display the n busiest queues'
    )
    parser.add_argument(
        'stats_file',
        nargs='*',
        type=str,
        help='file containing queue stats')
    args = parser.parse_args()

    # Start generating stats from all files given on the command line.
    stats = gen_stats(
        chain.from_iterable(
            gen_data_lines(filename) for filename in args.stats_file))
    # Collate stats according to limit definitions and check.
    stats_collated = collate_stats(stats, args.c, args.e, args.d)
    stats_checked = check_stats(stats_collated, args.c)
    criticals, warnings = [], []
    for queue, vhost, message_no, status in stats_checked:
        if status == "CRIT":
            criticals.append(
                "%s in %s has %s messages" % (queue, vhost, message_no))
        elif status == "WARN":
            warnings.append(
                "%s in %s has %s messages" % (queue, vhost, message_no))

    if args.m:
        oldest = datetime.now() - timedelta(seconds=args.m)
        freshness_results = [check_stats_file_freshness(f, oldest)
                             for f in args.stats_file]
        criticals.extend(
            msg for status, msg in freshness_results if status == "CRIT"
        )

    tqueues = top_n_queues(stats_collated, args.d)

    if len(criticals) > 0:
        print("CRITICAL: {0} {1}".format(", ".join(criticals),
                                         " | ".join(tqueues)))
        sys.exit(2)
        # XXX: No warnings if there are criticals?
    elif len(warnings) > 0:
        print("WARNING: {0} {1}".format(", ".join(warnings),
                                        " | ".join(tqueues)))
        sys.exit(1)
    else:
        print("OK")
        sys.exit(0)
