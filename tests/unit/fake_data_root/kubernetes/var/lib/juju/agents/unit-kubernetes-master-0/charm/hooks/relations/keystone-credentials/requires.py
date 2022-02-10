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

from charmhelpers.core import hookenv
from charms.reactive import RelationBase
from charms.reactive import hook
from charms.reactive import scopes


class KeystoneRequires(RelationBase):
    scope = scopes.GLOBAL

    # These remote data fields will be automatically mapped to accessors
    # with a basic documentation string provided.

    auto_accessors = ['private-address', 'credentials_host',
                      'credentials_protocol', 'credentials_port',
                      'credentials_project', 'credentials_username',
                      'credentials_password', 'credentials_project_id',
                      'credentials_project_domain_id',
                      'credentials_user_domain_id',
                      'credentials_project_domain_name',
                      'credentials_user_domain_name',
                      'api_version', 'auth_host', 'auth_protocol', 'auth_port',
                      'region', 'ca_cert', 'https_keystone']

    @hook('{requires:keystone-credentials}-relation-joined')
    def joined(self):
        self.set_state('{relation_name}.connected')
        self.update_state()

    def update_state(self):
        """Update the states of the relations based on the data that the
        relation has.

        If the :meth:`base_data_complete` is False then all of the states
        are removed.  Otherwise, the individual states are set according to
        their own data methods.
        """
        base_complete = self.base_data_complete()
        states = {
            '{relation_name}.available': True,
            '{relation_name}.available.ssl': self.ssl_data_complete(),
            '{relation_name}.available.auth': self.auth_data_complete()
        }
        for k, v in states.items():
            if base_complete and v:
                self.set_state(k)
            else:
                self.remove_state(k)

    @hook('{requires:keystone-credentials}-relation-changed')
    def changed(self):
        self.update_state()
        self.set_state('{relation_name}.available.updated')
        hookenv.atexit(self._clear_updated)

    @hook('{requires:keystone-credentials}-relation-{broken,departed}')
    def departed(self):
        self.update_state()

    def base_data_complete(self):
        data = {
            'private-address': self.private_address(),
            'credentials_host': self.credentials_host(),
            'credentials_protocol': self.credentials_protocol(),
            'credentials_port': self.credentials_port(),
            'api_version': self.api_version(),
            'auth_host': self.auth_host(),
            'auth_protocol': self.auth_protocol(),
            'auth_port': self.auth_port(),
        }
        if all(data.values()):
            return True
        return False

    def auth_data_complete(self):
        data = {
            'credentials_project': self.credentials_project(),
            'credentials_username': self.credentials_username(),
            'credentials_password': self.credentials_password(),
            'credentials_project_id': self.credentials_project_id(),
        }
        if all(data.values()):
            return True
        return False

    def ssl_data_complete(self):
        data = {
            'https_keystone': self.https_keystone(),
            'ca_cert': self.ca_cert(),
        }
        for value in data.values():
            if not value or value == '__null__':
                return False
        return True

    def request_credentials(self, username, project=None, region=None,
                            requested_roles=None, requested_grants=None,
                            domain=None):
        """
        Request credentials from Keystone

        :side effect: set requested paramaters on the identity-credentials
                      relation

        Required parameter
        :param username: Username to be created.

        Optional parametrs
        :param project: Project (tenant) name to be created. Defaults to
                        services project.
        :param requested_roles: Comma delimited list of roles to be created
        :param requested_grants: Comma delimited list of roles to be granted.
                                 Defaults to Admin role.
        :param domain: Keystone v3 domain the user will be created in. Defaults
                       to the Default domain.
        """
        relation_info = {
            'username': username,
            'project': project,
            'requested_roles': requested_roles,
            'requested_grants': requested_grants,
            'domain': domain,
        }

        self.set_local(**relation_info)
        self.set_remote(**relation_info)

    def _clear_updated(self):
        self.remove_state('{relation_name}.available.updated')
