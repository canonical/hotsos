from charmhelpers.core import hookenv
import charms.reactive as reactive


class MySQLRouterRequires(reactive.RelationBase):
    scope = reactive.scopes.GLOBAL

    # These remote data fields will be automatically mapped to accessors
    # with a basic documentation string provided.
    auto_accessors = [
        'db_host', 'ssl_ca', 'ssl_cert', 'ssl_key', 'wait_timeout']

    @reactive.hook('{requires:mysql-router}-relation-joined')
    def joined(self):
        self.set_state('{relation_name}.connected')
        self.set_or_clear_available()

    def set_or_clear_available(self):
        if self.db_router_data_complete():
            self.set_state('{relation_name}.available')
        else:
            self.remove_state('{relation_name}.available')
        if self.proxy_db_data_complete():
            self.set_state('{relation_name}.available.proxy')
        else:
            self.remove_state('{relation_name}.available.proxy')
        if self.ssl_data_complete():
            self.set_state('{relation_name}.available.ssl')
        else:
            self.remove_state('{relation_name}.available.ssl')

    @reactive.hook('{requires:mysql-router}-relation-changed')
    def changed(self):
        self.joined()

    @reactive.hook('{requires:mysql-router}-relation-{broken,departed}')
    def departed(self):
        # Clear state
        self.remove_state('{relation_name}.connected')
        self.remove_state('{relation_name}.available')
        self.remove_state('{relation_name}.proxy.available')
        self.remove_state('{relation_name}.available.ssl')
        # Check if this is the last unit
        for conversation in self.conversations():
            for rel_id in conversation.relation_ids:
                if len(hookenv.related_units(rel_id)) > 0:
                    # This is not the last unit so reevaluate state
                    self.joined()
                    self.changed()

    def configure_db_router(self, username, hostname, prefix):
        """
        Called by charm layer that uses this interface to configure a database.
        """

        relation_info = {
            prefix + '_username': username,
            prefix + '_hostname': hostname,
            'private-address': hostname,
        }
        self.set_prefix(prefix)
        self.set_remote(**relation_info)
        self.set_local(**relation_info)

    def configure_proxy_db(self, database, username, hostname, prefix):
        """
        Called by charm layer that uses this interface to configure a database.
        """

        relation_info = {
            prefix + '_database': database,
            prefix + '_username': username,
            prefix + '_hostname': hostname,
        }
        self.set_prefix(prefix)
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

    def database(self, prefix):
        """
        Return a configured database name.
        """
        return self.get_local(prefix + '_database')

    def username(self, prefix):
        """
        Return a configured username.
        """
        return self.get_local(prefix + '_username')

    def hostname(self, prefix):
        """
        Return a configured hostname.
        """
        return self.get_local(prefix + '_hostname')

    def password(self, prefix):
        """
        Return a database password.
        """
        return self.get_remote(prefix + '_password')

    def allowed_units(self, prefix):
        """
        Return a database's allowed_units.
        """
        return self.get_remote(prefix + '_allowed_units')

    def db_router_data_complete(self):
        """
        Check if required db router data is complete.
        """
        data = {
            'db_host': self.db_host(),
        }
        if self.get_prefixes():
            suffixes = ['_password']
            for prefix in self.get_prefixes():
                for suffix in suffixes:
                    key = prefix + suffix
                    data[key] = self.get_remote(key)
            if all(data.values()):
                return True
        return False

    def proxy_db_data_complete(self):
        """
        Check if required proxy databases data is complete.
        """
        data = {
            'db_host': self.db_host(),
        }
        # The mysql-router prefix + proxied db prefixes
        if self.get_prefixes() and len(self.get_prefixes()) > 1:
            suffixes = ['_password', '_allowed_units']
            for prefix in self.get_prefixes():
                for suffix in suffixes:
                    key = prefix + suffix
                    data[key] = self.get_remote(key)
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
