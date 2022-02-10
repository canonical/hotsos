#!/usr/bin/python
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from charms.reactive import Endpoint, toggle_flag


class KubeDNSRequireer(Endpoint):
    def manage_flags(self):
        '''Set flags according to whether we have DNS provider details.'''
        toggle_flag(self.expand_name('{endpoint_name}.available'),
                    self.has_info())

    def details(self):
        '''Return the DNS provider details.'''
        return {
            'domain': self._get_value('domain'),
            'sdn-ip': self._get_value('sdn-ip'),
            'port': self._get_value('port'),
        }

    def has_info(self):
        ''' Determine if we have all needed info'''
        return all(self.details().values())

    def _get_value(self, key):
        return self.all_joined_units.received_raw.get(key)
