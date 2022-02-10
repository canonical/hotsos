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

import relations.hacluster.interface_hacluster.common as common
from charms.reactive import hook
from charms.reactive import RelationBase
from charms.reactive import scopes
from charms.reactive.helpers import data_changed as rh_data_changed
from charmhelpers.core import hookenv


class HAClusterRequires(RelationBase, common.ResourceManagement):
    # The hacluster charm is a subordinate charm and really only works
    # for a single service to the HA Cluster relation, therefore set the
    # expected scope to be GLOBAL.
    scope = scopes.GLOBAL

    @hook('{requires:hacluster}-relation-joined')
    def joined(self):
        self.set_state('{relation_name}.connected')

    @hook('{requires:hacluster}-relation-changed')
    def changed(self):
        if self.is_clustered():
            self.set_state('{relation_name}.available')
        else:
            self.remove_state('{relation_name}.available')

    @hook('{requires:hacluster}-relation-{broken,departed}')
    def departed(self):
        self.remove_state('{relation_name}.available')
        self.remove_state('{relation_name}.connected')

    def data_changed(self, data_id, data, hash_type='md5'):
        return rh_data_changed(data_id, data, hash_type)

    def get_remote_all(self, key, default=None):
        """Return a list of all values presented by remote units for key"""
        values = []
        for conversation in self.conversations():
            for relation_id in conversation.relation_ids:
                for unit in hookenv.related_units(relation_id):
                    value = hookenv.relation_get(key,
                                                 unit,
                                                 relation_id) or default
                    if value:
                        values.append(value)
        return list(set(values))
