# Copyright 2014 Canonical Limited.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import re

from subprocess import check_output, CalledProcessError

from charmhelpers.core.hookenv import (
    log,
    ERROR,
)

CRUSH_BUCKET = """root {name} {{
    id {id}    # do not change unnecessarily
    # weight 0.000
    alg straw2
    hash 0  # rjenkins1
}}

rule {name} {{
    ruleset 0
    type replicated
    min_size 1
    max_size 10
    step take {name}
    step chooseleaf firstn 0 type host
    step emit
}}"""

# This regular expression looks for a string like:
# root NAME {
# id NUMBER
# so that we can extract NAME and ID from the crushmap
CRUSHMAP_BUCKETS_RE = re.compile(r"root\s+(.+)\s+\{\s*id\s+(-?\d+)")

# This regular expression looks for ID strings in the crushmap like:
# id NUMBER
# so that we can extract the IDs from a crushmap
CRUSHMAP_ID_RE = re.compile(r"id\s+(-?\d+)")


class Crushmap(object):
    """An object oriented approach to Ceph crushmap management."""

    def __init__(self):
        self._crushmap = self.load_crushmap()
        roots = re.findall(CRUSHMAP_BUCKETS_RE, self._crushmap)
        buckets = []
        ids = list(map(
            lambda x: int(x),
            re.findall(CRUSHMAP_ID_RE, self._crushmap)))
        ids = sorted(ids)
        if roots != []:
            for root in roots:
                buckets.append(CRUSHBucket(root[0], root[1], True))

        self._buckets = buckets
        if ids != []:
            self._ids = ids
        else:
            self._ids = [0]

    def load_crushmap(self):
        try:
            crush = str(check_output(['ceph', 'osd', 'getcrushmap'])
                        .decode('UTF-8'))
            return str(check_output(['crushtool', '-d', '-'],
                                    stdin=crush.stdout)
                       .decode('UTF-8'))
        except CalledProcessError as e:
            log("Error occurred while loading and decompiling CRUSH map:"
                "{}".format(e), ERROR)
            raise

    def ensure_bucket_is_present(self, bucket_name):
        if bucket_name not in [bucket.name for bucket in self.buckets()]:
            self.add_bucket(bucket_name)
            self.save()

    def buckets(self):
        """Return a list of buckets that are in the Crushmap."""
        return self._buckets

    def add_bucket(self, bucket_name):
        """Add a named bucket to Ceph"""
        new_id = min(self._ids) - 1
        self._ids.append(new_id)
        self._buckets.append(CRUSHBucket(bucket_name, new_id))

    def save(self):
        """Persist Crushmap to Ceph"""
        try:
            crushmap = self.build_crushmap()
            compiled = str(check_output(['crushtool', '-c', '/dev/stdin', '-o',
                                         '/dev/stdout'], stdin=crushmap)
                           .decode('UTF-8'))
            ceph_output = str(check_output(['ceph', 'osd', 'setcrushmap', '-i',
                                            '/dev/stdin'], stdin=compiled)
                              .decode('UTF-8'))
            return ceph_output
        except CalledProcessError as e:
            log("save error: {}".format(e))
            raise

    def build_crushmap(self):
        """Modifies the current CRUSH map to include the new buckets"""
        tmp_crushmap = self._crushmap
        for bucket in self._buckets:
            if not bucket.default:
                tmp_crushmap = "{}\n\n{}".format(
                    tmp_crushmap,
                    Crushmap.bucket_string(bucket.name, bucket.id))

        return tmp_crushmap

    @staticmethod
    def bucket_string(name, id):
        return CRUSH_BUCKET.format(name=name, id=id)


class CRUSHBucket(object):
    """CRUSH bucket description object."""

    def __init__(self, name, id, default=False):
        self.name = name
        self.id = int(id)
        self.default = default

    def __repr__(self):
        return "Bucket {{Name: {name}, ID: {id}}}".format(
            name=self.name, id=self.id)

    def __eq__(self, other):
        """Override the default Equals behavior"""
        if isinstance(other, self.__class__):
            return self.__dict__ == other.__dict__
        return NotImplemented

    def __ne__(self, other):
        """Define a non-equality test"""
        if isinstance(other, self.__class__):
            return not self.__eq__(other)
        return NotImplemented
