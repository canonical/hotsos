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


class KubeDNSProvider(Endpoint):
    def manage_flags(self):
        toggle_flag(self.expand_name('{endpoint_name}.connected'),
                    self.is_joined)

    def set_dns_info(self, *, domain, sdn_ip, port):
        '''Set the domain, sdn_ip, and port of the DNS provider.'''
        for relation in self.relations:
            relation.to_publish_raw.update({
                'domain': domain,
                'sdn-ip': sdn_ip,
                'port': port,
            })
