from charmhelpers.core import hookenv
from charms.reactive import RelationBase
from charms.reactive import hook
from charms.reactive import scopes


class MySQLSharedRequires(RelationBase):
    scope = scopes.GLOBAL

    # These remote data fields will be automatically mapped to accessors
    # with a basic documentation string provided.
    auto_accessors = ['access-network', 'db_host', 'db_port',
                      'ssl_ca', 'ssl_cert', 'ssl_key',
                      'cluster-series-upgrading', 'wait_timeout']

    @hook('{requires:mysql-shared}-relation-joined')
    def joined(self):
        self.set_state('{relation_name}.connected')

    @hook('{requires:mysql-shared}-relation-changed')
    def changed(self):
        if self.cluster_series_upgrading() == 'True':
            self.remove_state('{relation_name}.available')
            self.remove_state('{relation_name}.available.access_network')
            self.remove_state('{relation_name}.available.ssl')
        else:
            if self.base_data_complete() and self.unit_allowed_all_dbs():
                self.set_state('{relation_name}.available')
            if self.access_network_data_complete():
                self.set_state('{relation_name}.available.access_network')
            if self.ssl_data_complete():
                self.set_state('{relation_name}.available.ssl')

    @hook('{requires:mysql-shared}-relation-{broken,departed}')
    def departed(self):
        # Clear state
        self.remove_state('{relation_name}.connected')
        self.remove_state('{relation_name}.available')
        self.remove_state('{relation_name}.available.access_network')
        self.remove_state('{relation_name}.available.ssl')
        # Check if this is the last unit
        for conversation in self.conversations():
            for rel_id in conversation.relation_ids:
                if len(hookenv.related_units(rel_id)) > 0:
                    # This is not the last unit so reevaluate state
                    self.joined()
                    self.changed()

    def configure(self, database, username, hostname=None, prefix=None):
        """
        Called by charm layer that uses this interface to configure a database.
        """
        if not hostname:
            conversation = self.conversation()
            try:
                hostname = hookenv.network_get_primary_address(
                    conversation.relation_name
                )
            except NotImplementedError:
                hostname = hookenv.unit_private_ip()

        if prefix:
            relation_info = {
                prefix + '_database': database,
                prefix + '_username': username,
                prefix + '_hostname': hostname,
            }
            self.set_prefix(prefix)
        else:
            relation_info = {
                'database': database,
                'username': username,
                'hostname': hostname,
            }
        self.set_remote(**relation_info)
        self.set_local(**relation_info)

    def set_prefix(self, prefix):
        """
        Store all of the database prefixes in a list.
        """
        prefixes = self.get_local('prefixes')
        if prefixes:
            if prefix not in prefixes:
                self.set_local('prefixes', prefixes + [prefix])
        else:
            self.set_local('prefixes', [prefix])

    def get_prefixes(self):
        """
        Return the list of saved prefixes.
        """
        return self.get_local('prefixes')

    def database(self, prefix=None):
        """
        Return a configured database name.
        """
        if prefix:
            return self.get_local(prefix + '_database')
        return self.get_local('database')

    def username(self, prefix=None):
        """
        Return a configured username.
        """
        if prefix:
            return self.get_local(prefix + '_username')
        return self.get_local('username')

    def hostname(self, prefix=None):
        """
        Return a configured hostname.
        """
        if prefix:
            return self.get_local(prefix + '_hostname')
        return self.get_local('hostname')

    def password(self, prefix=None):
        """
        Return a database password.
        """
        if prefix:
            return self.get_remote(prefix + '_password')
        return self.get_remote('password')

    def allowed_units(self, prefix=None):
        """
        Return a database's allowed_units.
        """
        if prefix:
            return self.get_remote(prefix + '_allowed_units')
        return self.get_remote('allowed_units')

    def base_data_complete(self):
        """
        Check if required base data is complete.
        """
        data = {
            'db_host': self.db_host(),
        }
        if self.get_prefixes():
            suffixes = ['_password', '_allowed_units']
            for prefix in self.get_prefixes():
                for suffix in suffixes:
                    key = prefix + suffix
                    data[key] = self.get_remote(key)
        else:
            data['password'] = self.get_remote('password')
            data['allowed_units'] = self.get_remote('allowed_units')
        if all(data.values()):
            return True
        return False

    def unit_allowed_db(self, prefix=None):
        """"
        Check unit can access requested database.

        :param prefix: Prefix used to distinguish multiple db requests.
        :type prefix: str
        :returns: Whether db acl has been setup.
        :rtype: bool
        """
        allowed = False
        allowed_units = self.allowed_units(prefix=prefix) or ''
        hookenv.log("Checking {} is in {}".format(
            hookenv.local_unit(),
            allowed_units.split()))
        if allowed_units and hookenv.local_unit() in allowed_units.split():
            allowed = True
        hookenv.log("Unit allowed: {}".format(allowed))
        return allowed

    def unit_allowed_all_dbs(self):
        """"
        Check unit can access all requested databases.

        :returns: Whether db acl has been setup for all dbs.
        :rtype: bool
        """
        if self.get_prefixes():
            _allowed = [self.unit_allowed_db(prefix=p)
                        for p in self.get_prefixes()]
        else:
            _allowed = [self.unit_allowed_db()]
        hookenv.log("Allowed: {}".format(_allowed))
        if all(_allowed):
            hookenv.log("Returning unit_allowed_all_dbs True")
            return True
        hookenv.log("Returning unit_allowed_all_dbs False")
        return False

    def access_network_data_complete(self):
        """
        Check if optional access network data provided by mysql is complete.
        """
        data = {
            'access-network': self.access_network(),
        }
        if all(data.values()):
            return True
        return False

    def ssl_data_complete(self):
        """
        Check if optional ssl data provided by mysql is complete.
        """
        data = {
            'ssl_ca': self.ssl_ca(),
        }
        if all(data.values()):
            return True
        return False
