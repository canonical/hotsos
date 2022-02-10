#!/usr/bin/python3
"""
Checks for RabbitMQ cluster partitions.

Copyright (C) 2017 Canonical
All Rights Reserved
Author: James Hebden

This Nagios check will use the HTTP management API
to fetch cluster status, and check it for problems
such as partitions and offline nodes.
"""

from optparse import OptionParser
import json
import requests
import socket
import sys

if __name__ == '__main__':

    hostname = socket.gethostname()

    parser = OptionParser()
    parser.add_option("--host", dest="host",
                      help="RabbitMQ host to connect to [default=%default]",
                      metavar="HOST", default="localhost")
    parser.add_option("--port", dest="port", type="int",
                      help="port RabbitMQ is running on [default=%default]",
                      metavar="PORT", default=5672)
    parser.add_option("-v", "--verbose", default=False, action="store_true",
                      help="verbose run")
    parser.add_option("-u", "--user", dest="user", default="guest",
                      help="RabbitMQ user [default=%default]",
                      metavar="USER")
    parser.add_option("-p", "--password", dest="password", default="guest",
                      help="RabbitMQ password [default=%default]",
                      metavar="PASSWORD")
    parser.add_option("-t", "--tls", dest="tls", default=False,
                      help="Use TLS to talk to RabbitMQ? [default=%default]",
                      metavar="TLS")
    parser.add_option("-H", "--hostname",
                      dest="hostname",
                      default=hostname,
                      help="""Override hostname used when querying
                      cluster status [default=%default]""")
    parser.add_option("-R", "--rabbitname",
                      dest="rabbitname",
                      default="rabbit",
                      help="""Override rabbit user ID used when querying
                      cluster status [default=%default]""")
    (options, args) = parser.parse_args()

    if options.verbose:
        print("Checking host: %s@%s:%d") % (
            options.user,
            options.host,
            options.port
        )

    if (options.tls):
        proto = 'https'
    else:
        proto = 'http'

    query = '{0}://{1}:{2}@{3}:{4}/api/nodes/{5}@{6}'.format(
        proto,
        options.user,
        options.password,
        options.host,
        options.port,
        options.rabbitname,
        options.hostname,
    )

    try:
        partition_data = requests.get(query).text

    except requests.ConnectionError as error:
        print(
            "ERROR: could not connect to cluster: {0}".format(
                error
            )
        )
        sys.exit(3)

    if options.verbose:
        print(partition_data)

    try:
        partitions = len(json.loads(partition_data)['partitions'])
        cluster = len(json.loads(partition_data)['cluster_links'])

    except json.decoder.JSONDecodeError:
        print(
            "UNKNOWN: Could not parse cluster status data returned by RabbitMQ"
        )
        sys.exit(3)

    if(partitions > 0 or cluster < 0):
        print(
            "CRITICAL: %d partitions detected, %d nodes online."
        ) % (partitions, cluster)
        sys.exit(2)
    else:
        print("OK: No partitions detected")
        sys.exit(0)
