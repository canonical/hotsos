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

from charms.reactive import RelationBase
from charms.reactive import hook
from charms.reactive import scopes


class EtcdProvider(RelationBase):
    scope = scopes.GLOBAL

    @hook('{provides:etcd}-relation-{joined,changed}')
    def joined_or_changed(self):
        ''' Set the connected state from the provides side of the relation. '''
        self.set_state('{relation_name}.connected')

    @hook('{provides:etcd}-relation-{broken,departed}')
    def broken_or_departed(self):
        '''Remove connected state from the provides side of the relation. '''
        conv = self.conversation()
        if len(conv.units) == 1:
            conv.remove_state('{relation_name}.connected')

    def set_client_credentials(self, key, cert, ca):
        ''' Set the client credentials on the global conversation for this
        relation. '''
        self.set_remote('client_key', key)
        self.set_remote('client_ca', ca)
        self.set_remote('client_cert', cert)

    def set_connection_string(self, connection_string, version=''):
        ''' Set the connection string on the global conversation for this
        relation. '''
        # Note: Version added as a late-dependency for 2 => 3 migration
        # If no version is specified, consumers should presume etcd 2.x
        self.set_remote('connection_string', connection_string)
        self.set_remote('version', version)
