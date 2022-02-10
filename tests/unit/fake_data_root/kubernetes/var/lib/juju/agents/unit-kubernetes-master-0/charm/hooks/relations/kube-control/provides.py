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
    set_flag,
    data_changed
)

from charmhelpers.core import (
    hookenv,
    unitdata
)


DB = unitdata.kv()


class KubeControlProvider(Endpoint):
    """
    Implements the kubernetes-master side of the kube-control interface.
    """
    def manage_flags(self):
        toggle_flag(self.expand_name('{endpoint_name}.connected'),
                    self.is_joined)
        toggle_flag(self.expand_name('{endpoint_name}.gpu.available'),
                    self.is_joined and self._get_gpu())
        requests_data_id = self.expand_name('{endpoint_name}.requests')
        requests = self.auth_user()
        if data_changed(requests_data_id, requests):
            set_flag(self.expand_name('{endpoint_name}.requests.changed'))

    def set_dns(self, port, domain, sdn_ip, enable_kube_dns):
        """
        Send DNS info to the remote units.

        We'll need the port, domain, and sdn_ip of the dns service. If
        sdn_ip is not required in your deployment, the units private-ip
        is available implicitly.
        """
        for relation in self.relations:
            relation.to_publish_raw.update({
                'port': port,
                'domain': domain,
                'sdn-ip': sdn_ip,
                'enable-kube-dns': enable_kube_dns,
            })

    def auth_user(self):
        """
        Return the kubelet_user value on the wire from the requestors.
        """
        requests = []

        for unit in self.all_joined_units:
            requests.append(
                (unit.unit_name,
                 {'user': unit.received_raw.get('kubelet_user'),
                  'group': unit.received_raw.get('auth_group')})
            )

        requests.sort()
        return requests

    def sign_auth_request(self, scope, user, kubelet_token, proxy_token,
                          client_token):
        """
        Send authorization tokens to the requesting unit.
        """
        cred = {
            'scope': scope,
            'kubelet_token': kubelet_token,
            'proxy_token': proxy_token,
            'client_token': client_token
        }

        if not DB.get('creds'):
            DB.set('creds', {})

        all_creds = DB.get('creds')
        all_creds[user] = cred
        DB.set('creds', all_creds)

        for relation in self.relations:
            relation.to_publish.update({
                'creds': all_creds
            })

    def clear_creds(self):
        """
        Clear creds from the relation. This is used by non-leader units to stop
        advertising creds so that the leader can assume full control of them.
        """
        DB.unset('creds')
        for relation in self.relations:
            relation.to_publish_raw['creds'] = ''

    def _get_gpu(self):
        """
        Return True if any remote worker is gpu-enabled.
        """
        for unit in self.all_joined_units:
            if unit.received_raw.get('gpu') == 'True':
                hookenv.log('Unit {} has gpu enabled'.format(unit))
                return True

        return False

    def set_cluster_tag(self, cluster_tag):
        """
        Send the cluster tag to the remote units.
        """
        for relation in self.relations:
            relation.to_publish_raw.update({
                'cluster-tag': cluster_tag
            })

    def set_registry_location(self, registry_location):
        """
        Send the registry location to the remote units.
        """
        for relation in self.relations:
            relation.to_publish_raw.update({
                'registry-location': registry_location
            })

    def set_cohort_keys(self, cohort_keys):
        """
        Send the cohort snapshot keys.
        """
        for relation in self.relations:
            relation.to_publish['cohort-keys'] = cohort_keys

    def set_default_cni(self, default_cni):
        """
        Send the default CNI. The default_cni value should be a string
        containing the name of a related CNI application to use as the
        default CNI. For example: "flannel" or "calico". If no default has
        been chosen then "" can be sent instead.
        """
        for relation in self.relations:
            relation.to_publish['default-cni'] = default_cni

    def set_api_endpoints(self, endpoints):
        """
        Send the list of API endpoint URLs to which workers should connect.
        """
        endpoints = sorted(endpoints)
        for relation in self.relations:
            relation.to_publish['api-endpoints'] = endpoints
