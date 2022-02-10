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


class KubeControlRequirer(Endpoint):
    """
    Implements the kubernetes-worker side of the kube-control interface.
    """
    def manage_flags(self):
        """
        Set states corresponding to the data we have.
        """
        toggle_flag(
            self.expand_name('{endpoint_name}.connected'),
            self.is_joined)
        toggle_flag(
            self.expand_name('{endpoint_name}.dns.available'),
            self.is_joined and self.dns_ready())
        toggle_flag(
            self.expand_name('{endpoint_name}.auth.available'),
            self.is_joined and self._has_auth_credentials())
        toggle_flag(
            self.expand_name('{endpoint_name}.cluster_tag.available'),
            self.is_joined and self.get_cluster_tag())
        toggle_flag(
            self.expand_name('{endpoint_name}.registry_location.available'),
            self.is_joined and self.get_registry_location())
        toggle_flag(
            self.expand_name('{endpoint_name}.cohort_keys.available'),
            self.is_joined and self.cohort_keys)
        toggle_flag(
            self.expand_name('{endpoint_name}.default_cni.available'),
            self.is_joined and self.get_default_cni() is not None)
        toggle_flag(
            self.expand_name('{endpoint_name}.api_endpoints.available'),
            self.is_joined and self.get_api_endpoints())

    def get_auth_credentials(self, user):
        """
        Return the authentication credentials.
        """
        rx = {}
        for unit in self.all_joined_units:
            rx.update(unit.received.get('creds', {}))
        if not rx:
            return None

        if user in rx:
            return {
                'user': user,
                'kubelet_token': rx[user]['kubelet_token'],
                'proxy_token': rx[user]['proxy_token'],
                'client_token': rx[user]['client_token']
            }
        else:
            return None

    def get_dns(self):
        """
        Return DNS info provided by the master.
        """
        rx = self.all_joined_units.received_raw

        return {
            'port': rx.get('port'),
            'domain': rx.get('domain'),
            'sdn-ip': rx.get('sdn-ip'),
            'enable-kube-dns': rx.get('enable-kube-dns'),
        }

    def dns_ready(self):
        """
        Return True if we have all DNS info from the master.
        """
        keys = ['port', 'domain', 'sdn-ip', 'enable-kube-dns']
        dns_info = self.get_dns()
        return (set(dns_info.keys()) == set(keys) and
                dns_info['enable-kube-dns'] is not None)

    def set_auth_request(self, kubelet, group='system:nodes'):
        """
        Tell the master that we are requesting auth, and to use this
        hostname for the kubelet system account.

        Param groups - Determines the level of eleveted privleges of the
        requested user. Can be overridden to request sudo level access on the
        cluster via changing to system:masters.
        """
        for relation in self.relations:
            relation.to_publish_raw.update({
                'kubelet_user': kubelet,
                'auth_group': group
            })

    def set_gpu(self, enabled=True):
        """
        Tell the master that we're gpu-enabled (or not).
        """
        log('Setting gpu={} on kube-control relation'.format(enabled))
        for relation in self.relations:
            relation.to_publish_raw.update({
                'gpu': enabled
            })

    def _has_auth_credentials(self):
        """
        Predicate method to signal we have authentication credentials.
        """
        if self.all_joined_units.received_raw.get('creds'):
            return True

    def get_cluster_tag(self):
        """
        Tag for identifying resources that are part of the cluster.
        """
        return self.all_joined_units.received_raw.get('cluster-tag')

    def get_registry_location(self):
        """
        URL for container image registry.
        """
        return self.all_joined_units.received_raw.get('registry-location')

    @property
    def cohort_keys(self):
        """
        The cohort snapshot keys sent by the masters.
        """
        return self.all_joined_units.received['cohort-keys']

    def get_default_cni(self):
        """
        Default CNI network to use.
        """
        return self.all_joined_units.received['default-cni']

    def get_api_endpoints(self):
        """
        Returns a list of API endpoint URLs.
        """
        endpoints = set()
        for unit in self.all_joined_units:
            endpoints.update(unit.received['api-endpoints'] or [])
        return sorted(endpoints)
