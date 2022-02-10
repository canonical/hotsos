# Copyright 2019 Canonical Ltd
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

from charms import reactive
import charmhelpers.contrib.network.ip as ch_net_ip


class MySQLSharedProvides(reactive.Endpoint):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ingress_address = ch_net_ip.get_relation_ip(self.endpoint_name)

    def relation_ids(self):
        return [x.relation_id for x in self.relations]

    def set_ingress_address(self):
        for relation in self.relations:
            relation.to_publish_raw["ingress-address"] = self.ingress_address
            relation.to_publish_raw["private-address"] = self.ingress_address

    def available(self):
        for unit in self.all_joined_units:
            if unit.received['username']:
                return True
            for key in unit.received.keys():
                if "_username" in key:
                    return True
        return False

    @reactive.when('endpoint.{endpoint_name}.joined')
    def joined(self):
        reactive.clear_flag(self.expand_name('{endpoint_name}.available'))
        reactive.set_flag(self.expand_name('{endpoint_name}.connected'))
        self.set_ingress_address()

    @reactive.when('endpoint.{endpoint_name}.changed')
    def changed(self):
        flags = (
            self.expand_name(
                'endpoint.{endpoint_name}.changed.database'),
            self.expand_name(
                'endpoint.{endpoint_name}.changed.username'),
            self.expand_name(
                'endpoint.{endpoint_name}.changed.hostname'),
        )
        if reactive.all_flags_set(*flags):
            for flag in flags:
                reactive.clear_flag(flag)

        if self.available():
            reactive.set_flag(self.expand_name('{endpoint_name}.available'))
        else:
            reactive.clear_flag(self.expand_name('{endpoint_name}.available'))

    def remove(self):
        flags = (
            self.expand_name('{endpoint_name}.connected'),
            self.expand_name('{endpoint_name}.available'),
        )
        for flag in flags:
            reactive.clear_flag(flag)

    @reactive.when('endpoint.{endpoint_name}.broken')
    def broken(self):
        self.remove()

    @reactive.when('endpoint.{endpoint_name}.departed')
    def departed(self):
        self.remove()

    def set_db_connection_info(
            self, relation_id, db_host, password,
            allowed_units=None, prefix=None, wait_timeout=None, db_port=3306,
            ssl_ca=None):
        # Implementations of shared-db pre-date the json encoded era of
        # interface layers. In order not to have to update dozens of charms,
        # publish in raw data

        # No prefix for db_host and wait_timeout
        self.relations[relation_id].to_publish_raw["db_host"] = db_host
        self.relations[relation_id].to_publish_raw["db_port"] = db_port
        if wait_timeout:
            self.relations[relation_id].to_publish_raw["wait_timeout"] = (
                wait_timeout)
        if ssl_ca:
            self.relations[relation_id].to_publish_raw["ssl_ca"] = ssl_ca
        if not prefix:
            self.relations[relation_id].to_publish_raw["password"] = password
            self.relations[relation_id].to_publish_raw[
                "allowed_units"] = allowed_units
        else:
            self.relations[relation_id].to_publish_raw[
                "{}_password".format(prefix)] = password
            self.relations[relation_id].to_publish_raw[
                "{}_allowed_units".format(prefix)] = allowed_units
