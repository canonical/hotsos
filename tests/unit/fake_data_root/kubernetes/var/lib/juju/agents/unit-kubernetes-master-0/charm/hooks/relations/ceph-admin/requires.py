from charms.reactive import Endpoint
from charms.reactive import toggle_flag


class CephClient(Endpoint):
    def manage_flags(self):
        toggle_flag(self.expand_name('{endpoint_name}.available'),
                    all([self.key(),
                         self.fsid(),
                         self.auth(),
                         self.mon_hosts()]))

    def key(self):
        return self.all_joined_units.received_raw['key']

    def fsid(self):
        return self.all_joined_units.received_raw['fsid']

    def auth(self):
        return self.all_joined_units.received_raw['auth']

    def mon_hosts(self):
        return self.all_joined_units.received_raw['mon_hosts']
