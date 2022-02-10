# Copyright 2017 Canonical Ltd
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json

import charms.reactive as reactive

from charmhelpers.core.hookenv import (
    application_name,
    local_unit,
    log,
)
from charmhelpers.contrib.network.ip import format_ipv6_addr

from charmhelpers.contrib.storage.linux.ceph import (
    CephBrokerRq,
    is_request_complete,
    is_request_sent,
)


class CephRequires(reactive.Endpoint):

    def joined(self):
        reactive.set_flag(self.expand_name('{endpoint_name}.connected'))

    @property
    def key(self):
        return self._key()

    def _key(self):
        return self.all_joined_units.received.get('key')

    @property
    def auth(self):
        return self._auth()

    def _auth(self):
        return self.all_joined_units.received.get('auth')

    @property
    def relation_name(self):
        return self.expand_name('{endpoint_name}')

    def initial_ceph_response(self):
        raise NotImplementedError

    def changed(self):
        data = self.initial_ceph_response()
        if all(data.values()):
            reactive.set_flag(self.expand_name('{endpoint_name}.available'))

        rq = self.get_current_request()
        if rq:
            log("changed broker_req: {}".format(rq.ops))

            if rq and is_request_complete(rq, relation=self.relation_name):
                log("Setting ceph-client.pools.available")
                reactive.set_flag(
                    self.expand_name('{endpoint_name}.pools.available'))
            else:
                log("incomplete request. broker_req not found")

    def broken(self):
        reactive.clear_flag(
            self.expand_name('{endpoint_name}.available'))
        reactive.clear_flag(
            self.expand_name('{endpoint_name}.connected'))
        reactive.clear_flag(
            self.expand_name('{endpoint_name}.pools.available'))

    def create_replicated_pool(self, name, replicas=3, weight=None,
                               pg_num=None, group=None, namespace=None,
                               app_name=None, **kwargs):
        """
        Request pool setup

        :param name: Name of pool to create
        :type name: str
        :param replicas: Number of replicas for supporting pools
        :type replicas: int
        :param weight: The percentage of data the pool makes up
        :type weight: Optional[float]
        :param pg_num: If not provided, this value will be calculated by the
                       broker based on how many OSDs are in the cluster at the
                       time of creation. Note that, if provided, this value
                       will be capped at the current available maximum.
        :type pg_num: Optional[int]
        :param group: Group to add pool to.
        :type group: Optional[str]
        :param namespace: A group can optionally have a namespace defined that
                          will be used to further restrict pool access.
        :type namespace: Optional[str]
        :param app_name: (Optional) Tag pool with application name.  Note that
                         there is certain protocols emerging upstream with
                         regard to meaningful application names to use.
                         Examples are ``rbd`` and ``rgw``.
        :type app_name: Optional[str]
        :param kwargs: Additional keyword arguments subject to validation.
                       Refer to CephBrokerRq.add_op_create_replicated_pool
                       method for documentation.
        :type kwargs: Dict[str,any]
        """
        rq = self.get_current_request() or CephBrokerRq()
        kwargs.update({
            'name': name,
            'replica_count': replicas,
            'pg_num': pg_num,
            'weight': weight,
            'group': group,
            'namespace': namespace,
            'app_name': app_name,
        })
        rq.add_op_create_replicated_pool(**kwargs)
        self.send_request_if_needed(rq)
        reactive.clear_flag(
            self.expand_name('{endpoint_name}.pools.available'))

    def create_pool(self, name, replicas=3, weight=None, pg_num=None,
                    group=None, namespace=None):
        """
        Request pool setup -- deprecated. Please use create_replicated_pool
        or create_erasure_pool(which doesn't exist yet)

        @param name: Name of pool to create
        @param replicas: Number of replicas for supporting pools
        @param weight: The percentage of data the pool makes up
        @param pg_num: If not provided, this value will be calculated by the
                       broker based on how many OSDs are in the cluster at the
                       time of creation. Note that, if provided, this value
                       will be capped at the current available maximum.
        @param group: Group to add pool to.
        @param namespace: A group can optionally have a namespace defined that
                          will be used to further restrict pool access.
        """
        self.create_replicated_pool(name, replicas, weight, pg_num, group,
                                    namespace)

    def create_erasure_pool(self, name, erasure_profile=None,
                            weight=None, group=None, app_name=None,
                            max_bytes=None, max_objects=None,
                            allow_ec_overwrites=False,
                            **kwargs):
        """
        Request erasure coded pool setup

        :param name: Name of pool to create
        :type name: str
        :param erasure_profile: Name of erasure profile for pool
        :type erasure_profile: str
        :param weight: The percentage of data the pool makes up
        :type weight: Optional[float]
        :param group: Group to add pool to.
        :type group: Optional[str]
        :param app_name: Name of application using pool
        :type app_name: Optional[str]
        :param max_bytes: Maximum bytes of quota to apply
        :type max_bytes: Optional[int]
        :param max_objects: Maximum object quota to apply
        :type max_objects: Optional[int]
        :param allow_ec_overwrites: Allow EC pools to be overwritten
        :type allow_ec_overwrites: bool
        :param kwargs: Additional keyword arguments subject to validation.
                       Refer to CephBrokerRq.add_op_create_replicated_pool
                       method for documentation.
        :type kwargs: Dict[str,any]
        """
        rq = self.get_current_request() or CephBrokerRq()
        kwargs.update({
            'name': name,
            'erasure_profile': erasure_profile,
            'weight': weight,
            'group': group,
            'app_name': app_name,
            'max_bytes': max_bytes,
            'max_objects': max_objects,
            'allow_ec_overwrites': allow_ec_overwrites,
        })
        rq.add_op_create_erasure_pool(**kwargs)
        self.send_request_if_needed(rq)
        reactive.clear_flag(
            self.expand_name('{endpoint_name}.pools.available'))

    def create_erasure_profile(self, name,
                               erasure_type='jerasure',
                               erasure_technique=None,
                               k=None, m=None,
                               failure_domain=None,
                               lrc_locality=None,
                               shec_durability_estimator=None,
                               clay_helper_chunks=None,
                               device_class=None,
                               clay_scalar_mds=None,
                               lrc_crush_locality=None):
        """
        Create erasure coding profile

        @param name: Name of erasure coding profile
        @param erasure_type: Erasure coding plugin to use
        @param erasure_technique: Erasure coding technique to use
        @param k: Number of data chunks
        @param m: Number of coding chunks
        @param failure_domain: Failure domain to use for PG placement
        @param lrc_locality:
            Group the coding and data chunks into sets
            of size locality (lrc plugin)
        @param shec_durability_estimator:
            The number of parity chuncks each of which includes
            a data chunk in its calculation range (shec plugin)
        @param clay_helper_chunks:
            The number of helper chunks to use for recovery operations
            (clay plugin)
        @param device_class:
            Device class to use for profile (ssd, hdd, nvme)
        @param clay_scalar_mds:
            Plugin to use for CLAY layered construction
            (jerasure|isa|shec)
        @param lrc_crush_locality:
            Type of crush bucket in which set of chunks
            defined by lrc_locality will be stored.
        """
        rq = self.get_current_request() or CephBrokerRq()
        rq.add_op_create_erasure_profile(
            name=name,
            erasure_type=erasure_type,
            erasure_technique=erasure_technique,
            k=k, m=m,
            failure_domain=failure_domain,
            lrc_locality=lrc_locality,
            shec_durability_estimator=shec_durability_estimator,
            clay_helper_chunks=clay_helper_chunks,
            device_class=device_class,
            clay_scalar_mds=clay_scalar_mds,
            lrc_crush_locality=lrc_crush_locality
        )
        self.send_request_if_needed(rq)
        reactive.clear_flag(
            self.expand_name('{endpoint_name}.pools.available'))

    def request_access_to_group(self, name, namespace=None, permission=None,
                                key_name=None,
                                object_prefix_permissions=None):
        """
        Adds the requested permissions to service's Ceph key

        Adds the requested permissions to the current service's Ceph key,
        allowing the key to access only the specified pools or
        object prefixes. object_prefix_permissions should be a dictionary
        keyed on the permission with the corresponding value being a list
        of prefixes to apply that permission to.
            {
                'rwx': ['prefix1', 'prefix2'],
                'class-read': ['prefix3']}
        @param name: Target group name for permissions request.
        @param namespace: namespace to further restrict pool access.
        @param permission: Permission to be requested against pool
        @param key_name: userid to grant permission to
        @param object_prefix_permissions: Add object_prefix permissions.
        """
        current_request = self.get_current_request() or CephBrokerRq()
        current_request.add_op_request_access_to_group(
            name,
            namespace=namespace,
            permission=permission,
            key_name=key_name,
            object_prefix_permissions=object_prefix_permissions)
        self.send_request_if_needed(current_request)

    def send_request_if_needed(self, request):
        """Send broker request if an equivalent request has not been sent

        @param request: A CephBrokerRq object
        """
        if is_request_sent(request, relation=self.relation_name):
            log('Request already sent but not complete, '
                'not sending new request')
        else:
            for relation in self.relations:
                relation.to_publish['broker_req'] = json.loads(
                    request.request)
                relation.to_publish_raw[
                    'application-name'] = application_name()
                relation.to_publish_raw['unit-name'] = local_unit()

    def get_current_request(self):
        broker_reqs = []
        for relation in self.relations:
            broker_req = relation.to_publish.get('broker_req', {})
            if broker_req:
                rq = CephBrokerRq()
                rq.set_ops(broker_req['ops'])
                broker_reqs.append(rq)
        # Check that if there are multiple requests then they are the same.
        assert all(x == broker_reqs[0] for x in broker_reqs)
        if broker_reqs:
            return broker_reqs[0]

    def get_remote_all(self, key, default=None):
        """Return a list of all values presented by remote units for key"""
        values = []
        for relation in self.relations:
            for unit in relation.units:
                value = unit.received.get(key, default)
                if value:
                    values.append(value)
        return list(set(values))

    def mon_hosts(self):
        """List of all monitor host public addresses"""
        hosts = []
        addrs = self.get_remote_all('ceph-public-address')
        for ceph_addrs in addrs:
            # NOTE(jamespage): This looks odd but deals with
            #                  use with ceph-proxy which
            #                  presents all monitors in
            #                  a single space delimited field.
            for addr in ceph_addrs.split(' '):
                hosts.append(format_ipv6_addr(addr) or addr)
        hosts.sort()
        return hosts
