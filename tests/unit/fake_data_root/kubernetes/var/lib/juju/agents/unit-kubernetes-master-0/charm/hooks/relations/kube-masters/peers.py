#!/usr/local/sbin/charm-env python3
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

from charms.reactive import (
    Endpoint,
    toggle_flag,
)

from charmhelpers.core.hookenv import log


class KubeMastersPeer(Endpoint):
    """
    Implements peering for kubernetes-master units.
    """
    def manage_flags(self):
        """
        Set states corresponding to the data we have.
        """
        toggle_flag(
            self.expand_name('{endpoint_name}.connected'),
            self.is_joined)
        toggle_flag(
            self.expand_name('{endpoint_name}.cohorts.ready'),
            self.is_joined and self._peers_have_cohorts())

    def _peers_have_cohorts(self):
        """
        Return True if all peers have cohort keys.
        """
        for unit in self.all_joined_units:
            if not unit.received.get('cohort-keys'):
                log('Unit {} does not yet have cohort-keys'.format(unit))
                return False

        log('All units have cohort-keys')
        return True

    def set_cohort_keys(self, cohort_keys):
        """
        Send the cohort snapshot keys.
        """
        for relation in self.relations:
            relation.to_publish['cohort-keys'] = cohort_keys
