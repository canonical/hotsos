# Copyright 2020 Canonical Ltd
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

from .lib import base_requires

from charms.reactive import (
    when,
)


class CephClientRequires(base_requires.CephRequires):

    @when('endpoint.{endpoint_name}.joined')
    def joined(self):
        super().joined()

    @when('endpoint.{endpoint_name}.changed')
    def changed(self):
        super().changed()

    @when('endpoint.{endpoint_name}.departed')
    def departed(self):
        super().changed()

    @when('endpoint.{endpoint_name}.broken')
    def broken(self):
        super().broken()

    def initial_ceph_response(self):
        data = {
            'key': self.key,
            'auth': self.auth,
            'mon_hosts': self.mon_hosts()
        }
        return data
