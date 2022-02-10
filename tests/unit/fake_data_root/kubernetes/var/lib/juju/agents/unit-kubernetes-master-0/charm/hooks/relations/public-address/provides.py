import json

from charms.reactive import toggle_flag
from charms.reactive import Endpoint


class PublicAdddressProvides(Endpoint):

    def manage_flags(self):
        toggle_flag(self.expand_name('{endpoint_name}.available'),
                    self.is_joined)

    def set_address_port(self, address, port, relation=None):
        if relation is None:
            # no relation specified, so send the same data to everyone
            relations = self.relations
        else:
            # specific relation given, so only send the data to that one
            relations = [relation]
        if type(address) is list:
            # build 2 lists to zip together that are the same length
            length = len(address)
            p = [port] * length
            combined = zip(address, p)
            clients = [{'public-address': a, 'port': p}
                       for a, p in combined]
            # for backwards compatibility, we just send a single entry
            # and have an array of dictionaries in a field of that
            # entry for the other entries.
            first = clients.pop(0)
            first['extended_data'] = json.dumps(clients)
            for relation in relations:
                relation.to_publish_raw.update(first)
        else:
            for relation in relations:
                relation.to_publish_raw.update({'public-address': address,
                                                'port': port})

    @property
    def requests(self):
        return [Request(rel) for rel in self.relations]


class Request:
    def __init__(self, rel):
        self.rel = rel

    @property
    def application_name(self):
        return self.rel.application_name

    @property
    def members(self):
        return [(u.received_raw.get('ingress-address',
                                    u.received_raw['private-address']),
                 u.received_raw.get('port', '6443'))
                for u in self.rel.joined_units]

    def set_address_port(self, address, port):
        self.rel.endpoint.set_address_port(address, port, self.rel)
