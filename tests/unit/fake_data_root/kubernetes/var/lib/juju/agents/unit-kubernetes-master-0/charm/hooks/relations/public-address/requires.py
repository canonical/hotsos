import json

from charms.reactive import toggle_flag, Endpoint


class PublicAddressRequires(Endpoint):
    def manage_flags(self):
        toggle_flag(self.expand_name('{endpoint_name}.available'),
                    len(self.get_addresses_ports()) > 0)

    def set_backend_port(self, port):
        """
        Set the port that the backend service is listening on.

        Defaults to 6443 if not set.
        """
        for rel in self.relations:
            rel.to_publish_raw['port'] = str(port)

    def get_addresses_ports(self):
        '''Returns a list of available HTTP providers and their associated
        public addresses and ports.

        The return value is a list of dicts of the following form::
            [
                {
                    'public-address': address_for_frontend,
                    'port': port_for_frontend,
                },
                # ...
            ]
        '''
        hosts = set()
        for relation in self.relations:
            for unit in relation.joined_units:
                data = unit.received_raw
                hosts.add((data['public-address'], data['port']))
                if 'extended_data' in data:
                    for ed in json.loads(data['extended_data']):
                        hosts.add((ed['public-address'], ed['port']))

        return [{'public-address': pa, 'port': p}
                for pa, p in sorted(host for host in hosts
                                    if None not in host)]
