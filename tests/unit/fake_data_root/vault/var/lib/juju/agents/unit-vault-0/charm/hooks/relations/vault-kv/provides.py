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

from charms.reactive import is_flag_set, toggle_flag, clear_flag
from charms.reactive import Endpoint
from charmhelpers import core as ch_core


class VaultKVProvides(Endpoint):
    def manage_flags(self):
        any_fields_changed = False
        for field in ('access_address',
                      'secret_backend',
                      'hostname',
                      'isolated'):
            flag = self.expand_name('endpoint.{endpoint_name}.'
                                    'changed.{}').format(field)
            any_fields_changed = any_fields_changed or is_flag_set(flag)
            clear_flag(flag)
        toggle_flag(self.expand_name('{endpoint_name}.connected'),
                    self.is_joined)
        toggle_flag(self.expand_name('endpoint.{endpoint_name}.new-request'),
                    any_fields_changed)

    def publish_url(self, vault_url, remote_binding=None):
        """ Publish URL for Vault to all Relations

        :param vault_url: api url used by remote client to speak to vault.
        :param remote_binding: Deprecated
        """
        if remote_binding:
            ch_core.hookenv.log(
                "Use of remote_binding in publish_url is deprecated. "
                "See LP Bug #1895185", "WARNING")
        for relation in self.relations:
            relation.to_publish['vault_url'] = vault_url

    def publish_ca(self, vault_ca):
        """ Publish SSL CA for Vault to all Relations """
        for relation in self.relations:
            relation.to_publish['vault_ca'] = vault_ca

    def get_remote_unit_name(self, unit):
        """Get the remote units name.

        :param unit: Unit to get name for.
        :type name: Unit
        :returns: Unit name
        :rtype: str
        """
        return unit.received.get('unit_name') or unit.unit_name

    def set_role_id(self, unit, role_id, token):
        """ Set the AppRole ID and token for out-of-band Secret ID retrieval
        for a specific remote unit """
        # for cmr we will need to the other end to provide their unit name
        # expicitly.
        unit_name = self.get_remote_unit_name(unit)
        unit.relation.to_publish['{}_role_id'.format(unit_name)] = role_id
        unit.relation.to_publish['{}_token'.format(unit_name)] = token

    def requests(self):
        """ Retrieve full set of setup requests from all remote units """
        requests = []
        for relation in self.relations:
            for unit in relation.units:
                access_address = unit.received['access_address']
                ingress_address = unit.received['ingress-address']
                secret_backend = unit.received['secret_backend']
                hostname = unit.received['hostname']
                isolated = unit.received['isolated']
                unit_name = self.get_remote_unit_name(unit)
                if not (secret_backend and access_address and
                        hostname and isolated is not None):
                    continue
                requests.append({
                    'unit': unit,
                    'unit_name': unit_name,
                    'access_address': access_address,
                    'ingress_address': ingress_address,
                    'secret_backend': secret_backend,
                    'hostname': hostname,
                    'isolated': isolated,
                })
        return requests
