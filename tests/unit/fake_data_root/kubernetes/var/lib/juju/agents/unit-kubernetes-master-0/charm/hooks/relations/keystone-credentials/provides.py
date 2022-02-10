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


class KeystoneProvides(RelationBase):
    scope = scopes.GLOBAL

    @hook('{provides:keystone-credentials}-relation-joined')
    def joined(self):
        self.set_flag('{relation_name}.connected')

    @hook('{provides:keystone-credentials}-relation-{broken,departed}')
    def departed(self):
        self.clear_flag('{relation_name}.connected')

    def expose_credentials(self, credentials):
        """Expose Keystone credentials to related units.

        :param credentials: The Keystone credentials to be exposed.
        :type credentials: dict
        """
        self.set_remote(**credentials)
