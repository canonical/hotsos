# Copyright 2019-2021 Canonical Ltd
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

import configparser
import json
import os
import subprocess
import tenacity

import charms_openstack.charm
import charms_openstack.adapters

import charms.reactive as reactive

import charmhelpers.core as ch_core
import charmhelpers.contrib.network.ip as ch_net_ip

import charmhelpers.contrib.database.mysql as mysql

import charmhelpers.contrib.openstack.templating as os_templating


# Flag Strings
MYSQL_ROUTER_BOOTSTRAPPED = "charm.mysqlrouter.bootstrapped"
MYSQL_ROUTER_BOOTSTRAP_ATTEMPTED = "charm.mysqlrouter.bootstrap-attempted"
MYSQL_ROUTER_STARTED = "charm.mysqlrouter.started"
DB_ROUTER_AVAILABLE = "db-router.available"
DB_ROUTER_PROXY_AVAILABLE = "db-router.available.proxy"


@charms_openstack.adapters.config_property
def db_router_address(cls):
    return ch_net_ip.get_relation_ip("db-router")


@charms_openstack.adapters.config_property
def shared_db_address(cls):
    # This is is a subordinate relation, we want mysql communication
    # to run over localhost
    # Alternatively: ch_net_ip.get_relation_ip("shared-db")
    return "127.0.0.1"


class MySQLRouterCharm(charms_openstack.charm.OpenStackCharm):
    """Charm class for the MySQLRouter charm."""
    name = ch_core.hookenv.service_name()
    packages = ["mysql-router"]
    release = "stein"
    release_pkg = "mysql-router"
    required_relations = ["db-router", "shared-db"]
    source_config_key = "source"
    mysql_connect_timeout = 30

    systemd_file = os.path.join(
        "/etc/systemd/system",
        "{}.service".format(name))

    services = [name]
    restart_map = {
        "/var/lib/mysql/{}/mysqlrouter.conf".format(name): services
    }
    # TODO Pick group owner
    group = "mysql"

    # For internal use with mysql.get_db_data
    _unprefixed = "MRUP"

    # mysql.MySQLdb._exceptions.OperationalError error 2013
    # LP Bug #1915842
    _waiting_for_initial_communication_packet_error = 2013

    @property
    def mysqlrouter_pid_file(self):
        """Determine the path for the mysqlrouter PID file.

        :param self: Self
        :type self: MySQLRouterCharm instance
        :returns: Path to the PID file in /run
        :rtype: str
        """
        return "/run/mysql/mysqlrouter-{}.pid".format(self.name)

    @property
    def mysqlrouter_bin(self):
        """Determine the path to the mysqlrouter binary.

        :param self: Self
        :type self: MySQLRouterCharm instance
        :returns: Path to the binary
        :rtype: str
        """
        return "/usr/bin/mysqlrouter"

    @property
    def db_router_endpoint(self):
        """Get the MySQL Router (db-router) interface.

        :param self: Self
        :type self: MySQLRouterCharm instance
        :returns: db-router interface
        :rtype: MySQLRouterRequires object
        """
        return reactive.relations.endpoint_from_flag("db-router.available")

    @property
    def db_prefix(self):
        """Determine the prefix to use on the db-router relation.

        :param self: Self
        :type self: MySQLRouterCharm instance
        :returns: Prefix
        :rtype: str
        """
        return "mysqlrouter"

    @property
    def db_router_user(self):
        """Determine the username to access the MySQL InnoDB Cluster.

        :param self: Self
        :type self: MySQLRouterCharm instance
        :returns: Username
        :rtype: str
        """
        return "{}user".format(self.db_prefix)

    @property
    def db_router_password(self):
        """Determine the password for the MySQL InnoDB Cluster.

        Using the MySQL Router Endpoint determine the password to access the
        MySQL InnoDB Cluster.

        :param self: Self
        :type self: MySQLRouterCharm instance
        :returns: Password
        :rtype: str
        """
        return json.loads(
            self.db_router_endpoint.password(prefix=self.db_prefix))

    @property
    def db_router_address(self):
        """Determine this unit's DB-Router address.

        Using the class method determine this unit's address for the DB-Router
        relation.

        :param self: Self
        :type self: MySQLRouterCharm instance
        :returns: Address
        :rtype: str
        """
        return self.options.db_router_address

    @property
    def cluster_address(self):
        """Determine MySQL InnoDB Cluster's address.

        Using the MySQL Router Endpoint determine the MySQL InnoDB Cluster's
        address.

        :param self: Self
        :type self: MySQLRouterCharm instance
        :returns: Address
        :rtype: str
        """
        return json.loads(self.db_router_endpoint.db_host())

    @property
    def shared_db_address(self):
        """Determine this unit's Shared-DB address.

        Using the class method determine this unit's address for the Shared-DB
        relation.

        :param self: Self
        :type self: MySQLRouterCharm instance
        :returns: Address
        :rtype: str
        """
        return self.options.shared_db_address

    @property
    def mysqlrouter_port(self):
        return self.options.base_port

    @property
    def mysqlrouter_working_dir(self):
        """Determine the path to the mysqlrouter working directory.

        :param self: Self
        :type self: MySQLRouterCharm instance
        :returns: Path to the directory
        :rtype: str
        """
        return "{}/{}".format(self.mysqlrouter_home_dir, self.name)

    @property
    def mysqlrouter_home_dir(self):
        """Determine the path to the mysqlrouter working directory.

        :param self: Self
        :type self: MySQLRouterCharm instance
        :returns: Path to the directory
        :rtype: str
        """
        return "/var/lib/mysql"

    @property
    def mysqlrouter_conf(self):
        """Determine the path to the mysqlrouter.conf file.

        :returns: Path to the mysqlrouter.conf file
        :rtype: str
        """
        return "{}/mysqlrouter.conf".format(self.mysqlrouter_working_dir)

    @property
    def mysqlrouter_user(self):
        return "mysql"

    @property
    def mysqlrouter_group(self):
        return "mysql"

    @property
    def ssl_ca(self):
        """Return the SSL Certificate Authority

        :param self: Self
        :type self: MySQLInnoDBClusterCharm instance
        :returns: Cluster username
        :rtype: str
        :rtype: Union[str, None]
        """
        if self.db_router_endpoint:
            if self.db_router_endpoint.ssl_ca():
                return json.loads(self.db_router_endpoint.ssl_ca())

    @property
    def restart_functions(self):
        return {self.name: self.custom_restart_function}

    def install(self):
        """Custom install function.

        :param self: Self
        :type self: MySQLRouterCharm instance
        :side effect: Executes other functions
        :returns: This function is called for its side effect
        :rtype: None
        """
        # TODO: charms.openstack should probably do this
        # Need to configure source first
        self.configure_source()
        super().install()

        # Neither MySQL Router nor MySQL common packaging creates a user, group
        # or home dir. As we want it to run as a system user in a predictable
        # location create all of these.
        # Create the group
        if not ch_core.host.group_exists(self.mysqlrouter_group):
            ch_core.host.add_group(
                self.mysqlrouter_group, system_group=True)
        # Create the user
        if not ch_core.host.user_exists(self.mysqlrouter_user):
            ch_core.host.adduser(
                self.mysqlrouter_user, shell="/usr/sbin/nologin",
                system_user=True, primary_group=self.mysqlrouter_group,
                home_dir=self.mysqlrouter_home_dir)
        # Create the directory
        if not os.path.exists(self.mysqlrouter_home_dir):
            ch_core.host.mkdir(
                self.mysqlrouter_home_dir,
                owner=self.mysqlrouter_user,
                group=self.mysqlrouter_group,
                perms=0o755)

        # Systemd File
        ch_core.templating.render(
            source="mysqlrouter.service",
            template_loader=os_templating.get_loader(
                'templates/', self.release),
            target=self.systemd_file,
            context=self.adapters_instance,
            group=self.group,
            perms=0o755,
        )
        cmd = ["systemctl", "enable", self.name]
        subprocess.check_output(cmd, stderr=subprocess.STDOUT)

    def get_db_helper(self):
        """Get an instance of the MySQLDB8Helper class.

        :param self: Self
        :type self: MySQLRouterCharm instance
        :returns: Instance of MySQLDB8Helper class
        :rtype: MySQLDB8Helper instance
        """
        db_helper = mysql.MySQL8Helper(
            rpasswdf_template="/var/lib/charm/{}/mysql.passwd"
                              .format(ch_core.hookenv.service_name()),
            upasswdf_template="/var/lib/charm/{}/mysql-{{}}.passwd"
                              .format(ch_core.hookenv.service_name()),
            user=self.db_router_user,
            password=self.db_router_password,
            host=self.cluster_address)
        return db_helper

    def states_to_check(self, required_relations=None):
        """Custom states to check function.

        Construct a custom set of connected and available states for each
        of the relations passed, along with error messages and new status
        conditions.

        :param self: Self
        :type self: MySQLRouterCharm instance
        :param required_relations: List of relations which overrides
                                   self.relations
        :type required_relations: list of strings
        :returns: {relation: [(state, err_status, err_msg), (...),]}
        :rtype: dict
        """
        states_to_check = super().states_to_check(required_relations)
        states_to_check["charm"] = [
            (MYSQL_ROUTER_BOOTSTRAPPED,
             "waiting",
             "MySQL Router not yet bootstrapped"),
            (MYSQL_ROUTER_STARTED,
             "waiting",
             "MySQL Router not yet started"),
            (DB_ROUTER_PROXY_AVAILABLE,
             "waiting",
             "Waiting for proxied DB creation from cluster")]

        return states_to_check

    def check_mysql_connection(self, reraise_on=None):
        """Check if an instance of MySQL is accessible.

        Attempt a connection to the given instance of mysql to determine if it
        is running and accessible.

        :param reraise_on: List of integer error codes to reraise exceptions.
                           For use with tenacity retries on specific
                           exceptions.
        :type reraise_on: List[int]
        :side effect: Uses get_db_helper to execute a connection to the DB.
        :returns: True if connection succeeds or False if not
        :rtype: boolean
        """
        m_helper = self.get_db_helper()
        try:
            m_helper.connect(self.db_router_user,
                             self.db_router_password,
                             self.shared_db_address,
                             port=self.mysqlrouter_port,
                             connect_timeout=self.mysql_connect_timeout)
            return True
        except mysql.MySQLdb._exceptions.OperationalError as e:
            ch_core.hookenv.log("Could not connect to db", "DEBUG")
            if not reraise_on:
                return False
            else:
                if e.args[0] in reraise_on:
                    raise e

    def custom_assess_status_check(self):
        """Custom assess status check.

        Custom assess status check that validates connectivity to this unit's
        MySQL instance.

        Returns tuple of (sate, message), if there is a problem to report to
        status output, or (None, None) if all is well.

        :param self: Self
        :type self: MySQLRouterCharm instance
        :returns: Either (state, message) or (None, None)
        :rtype: Union[tuple(str, str), tuple(None, None)]
        """
        # Start with default checks
        for f in [self.check_if_paused,
                  self.check_interfaces,
                  self.check_mandatory_config]:
            state, message = f()
            if state is not None:
                ch_core.hookenv.status_set(state, message)
                return state, message

        # We should not get here until there is a connection to the
        # cluster (db-router available)
        if not self.check_mysql_connection():
            return "blocked", "Failed to connect to MySQL"

        return None, None

    def bootstrap_mysqlrouter(self):
        """Bootstrap MySQL Router.

        Execute the mysqlrouter bootstrap command. MySQL Router bootstraps into
        a working directory information it gathers from the MySQL InnoDB
        Cluster about the cluster's schema. Configuration and working files
        live in self.mysqlrouter_bin.

        :param self: Self
        :type self: MySQLRouterCharm instance
        :side effect: Executes the mysqlrouter bootstrap command
        :returns: This function is called for its side effect
        :rtype: None
        """

        if reactive.flags.is_flag_set(MYSQL_ROUTER_BOOTSTRAPPED):
            ch_core.hookenv.log(
                "Bootstrap mysqlrouter is being called after we set the "
                "bootstrapped flag: {}. This may require manual intervention,"
                "bailing for now."
                .format(MYSQL_ROUTER_BOOTSTRAPPED),
                "WARNING")
            return

        cmd = [self.mysqlrouter_bin,
               "--user", self.mysqlrouter_user,
               "--name", self.name,
               "--bootstrap",
               "{}:{}@{}".format(self.db_router_user,
                                 self.db_router_password,
                                 self.cluster_address),
               "--directory", self.mysqlrouter_working_dir,
               "--conf-use-sockets",
               "--conf-bind-address", self.shared_db_address,
               "--report-host", self.db_router_address,
               "--conf-base-port", str(self.mysqlrouter_port)]
        # Avoid multiple routers trying to bind to the same api port
        # Bug #1911907
        if ch_core.host.cmp_pkgrevno('mysql-router', '8.0.22') >= 0:
            cmd.append("--disable-rest")

        # If we have attempted to bootstrap before but unsuccessfully,
        # use the force option to avoid LP Bug#1919560
        if reactive.flags.is_flag_set(MYSQL_ROUTER_BOOTSTRAP_ATTEMPTED):
            cmd.append("--force")

        # Set and attempt the bootstrap
        reactive.flags.set_flag(MYSQL_ROUTER_BOOTSTRAP_ATTEMPTED)
        try:
            output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
            ch_core.hookenv.log(output, "DEBUG")
        except subprocess.CalledProcessError as e:
            ch_core.hookenv.log(
                "Failed to bootstrap mysqlrouter: {}"
                .format(e.output.decode("UTF-8")), "ERROR")
            return
        # Clear the attempted flag as we were successful
        reactive.flags.clear_flag(MYSQL_ROUTER_BOOTSTRAP_ATTEMPTED)
        # Set that we have been bootstrapped
        reactive.flags.set_flag(MYSQL_ROUTER_BOOTSTRAPPED)

    def start_mysqlrouter(self):
        """Start MySQL Router.

        Start up the mysqlrouter daemon via the start script.

        :param self: Self
        :type self: MySQLRouterCharm instance
        :side effect: Executes the mysqlrouter start script
        :returns: This function is called for its side effect
        :rtype: None
        """
        ch_core.host.service_start(self.name)
        reactive.flags.set_flag(MYSQL_ROUTER_STARTED)

    def stop_mysqlrouter(self):
        """Stop MySQL Router.

        Stop the mysqlrouter daemon via the stop script.

        :param self: Self
        :type self: MySQLRouterCharm instance
        :side effect: Executes the mysqlrouter stop script
        :returns: This function is called for its side effect
        :rtype: None
        """
        ch_core.host.service_stop(self.name)

    def restart_mysqlrouter(self):
        """Restart MySQL Router.

        Restart the mysqlrouter daemon by calling self.stop_mysqlrouter and
        self.start_mysqlrouter.

        :param self: Self
        :type self: MySQLRouterCharm instance
        :side effect: Executes other functions
        :returns: This function is called for its side effect
        :rtype: None
        """
        ch_core.host.service_restart(self.name)

    def proxy_db_and_user_requests(
            self, receiving_interface, sending_interface):
        """Proxy database and user requests to the MySQL InnoDB Cluster.

        Take requests from the shared-db relation and proxy them to the
        db-router relation using their respective endpoints.

        :param self: Self
        :type self: MySQLRouterCharm instance
        :param receiving_interface: Shared-DB interface
        :type receiving_interface: MySQLSharedProvides object
        :param sending_interface: DB-Router interface
        :type sending_interface: MySQLRouterRequires object
        :side effect: Executes sending interface's set function
        :returns: This function is called for its side effect
        :rtype: None
        """
        # We can use receiving_interface.all_joined_units.received
        # as this is a subordiante and there is only one unit related.
        db_data = mysql.get_db_data(
            dict(receiving_interface.all_joined_units.received),
            unprefixed=self._unprefixed)

        for prefix in db_data:
            sending_interface.configure_proxy_db(
                db_data[prefix].get("database"),
                db_data[prefix].get("username"),
                db_data[prefix].get("hostname"),
                prefix=prefix)

    def proxy_db_and_user_responses(
            self, receiving_interface, sending_interface):
        """Proxy database and user responses to clients.

        Take responses from the db-router relation and proxy them to the
        shared-db relation using their respective endpoints.

        :param self: Self
        :type self: MySQLRouterCharm instance
        :param receiving_interface: DB-Router interface
        :type receiving_interface: MySQLRouterRequires object
        :param sending_interface: Shared-DB interface
        :type sending_interface: MySQLSharedProvides object
        :side effect: Executes sending interface's set function
        :returns: This function is called for its side effect
        :rtype: None
        """
        try:
            # This is a subordinate relationship there is only ever one
            unit = sending_interface.all_joined_units[0]
        except IndexError:
            # NOTE(lourot): this happens when the unit is departing, see
            # lp:1881596. Let's just silently give up:
            return

        for prefix in receiving_interface.get_prefixes():

            if prefix in self.db_prefix:
                # Do not send the mysqlrouter credentials to the client
                continue

            if not receiving_interface.password(prefix=prefix):
                ch_core.hookenv.log(
                    "Skipping proxy_db_and_user_responses as we have no "
                    "relation data on a departing db-router relation. ",
                    "WARNING")
                return

            _password = json.loads(
                receiving_interface.password(prefix=prefix))

            # Wait timeout is an optional setting
            _wait_timeout = receiving_interface.wait_timeout()
            if _wait_timeout:
                _wait_timeout = json.loads(_wait_timeout)
            # SSL CA is an optional setting
            _ssl_ca = receiving_interface.ssl_ca()
            if _ssl_ca:
                _ssl_ca = json.loads(_ssl_ca)
            else:
                # Reset ssl_ca in case we previously had it set
                ch_core.hookenv.log("Proactively resetting ssl_ca", "DEBUG")
                sending_interface.relations[
                    unit.relation.relation_id].to_publish_raw["ssl_ca"] = None

            if ch_core.hookenv.local_unit() in (json.loads(
                    receiving_interface.allowed_units(prefix=prefix))):
                _allowed_hosts = unit.unit_name
            else:
                _allowed_hosts = None
            if prefix in self._unprefixed:
                prefix = None

            sending_interface.set_db_connection_info(
                unit.relation.relation_id,
                self.shared_db_address,
                _password,
                allowed_units=_allowed_hosts,
                prefix=prefix,
                wait_timeout=_wait_timeout,
                db_port=self.mysqlrouter_port,
                ssl_ca=_ssl_ca)

    def update_config_parameters(self, parameters):
        """Update configuration parameters using ConfigParser.

        Update this instances mysqlrouter.conf with a dictionary set of
        configuration parameters and values of the form:

        parameters = {
            "HEADING": {
                "param": "value"
            }
        }

        :param parameters: Dictionary of parameters
        :type parameters: dict
        :side effect: Writes the mysqlrouter.conf file
        :returns: This function is called for its side effect
        :rtype: None
        """
        config = configparser.ConfigParser()
        config.read(self.mysqlrouter_conf)
        for heading in parameters.keys():
            for param in parameters[heading].keys():
                # BUG LP#1927981 - heading may not exist during a charm upgrade
                # Handle missing heading via direct assignment in except.
                try:
                    config[heading][param] = parameters[heading][param]
                except KeyError:
                    config[heading] = {param: parameters[heading][param]}
        ch_core.hookenv.log("Writing {}".format(
            self.mysqlrouter_conf))
        with open(self.mysqlrouter_conf, 'w') as configfile:
            config.write(configfile)

    def config_changed(self):
        """Config changed.

        Custom config changed as we are not using templates we need to update
        config via ConfigParser. We only update after the mysql-router service
        has bootstrapped.

        :side effect: Calls update_config_parameter and restarts mysql-router
                      if the config file has changed.
        :returns: This function is called for its side effect
        :rtype: None
        """
        if not os.path.exists(self.mysqlrouter_conf):
            ch_core.hookenv.log(
                "mysqlrouter.conf does not yet exist. "
                "Skipping config changed.", "DEBUG")
            return

        _parameters = {
            "metadata_cache:jujuCluster": {
                "ttl": str(self.options.ttl),
                "auth_cache_ttl": str(self.options.auth_cache_ttl),
                "auth_cache_refresh_interval":
                    str(self.options.auth_cache_refresh_interval),
            },
            "DEFAULT": {
                "pid_file": self.mysqlrouter_pid_file,
                "max_connections": str(self.options.max_connections),
            }
        }

        if self.ssl_ca:
            ch_core.hookenv.log("TLS mode PASSTHROUGH", "DEBUG")
            _parameters["DEFAULT"]["client_ssl_mode"] = "PASSTHROUGH"
        else:
            ch_core.hookenv.log("TLS mode PREFERRED", "DEBUG")
            _parameters["DEFAULT"]["client_ssl_mode"] = "PREFERRED"

        with ch_core.host.restart_on_change(
                self.restart_map, restart_functions=self.restart_functions):
            ch_core.hookenv.log("Updating configuration parameters", "DEBUG")
            self.update_config_parameters(_parameters)

    @tenacity.retry(wait=tenacity.wait_fixed(10),
                    retry=tenacity.retry_if_exception_type(
                        mysql.MySQLdb._exceptions.OperationalError),
                    reraise=True,
                    stop=tenacity.stop_after_attempt(5))
    def custom_restart_function(self, service_name):
        """Tenacity retry custom restart function for restart_on_change

        Custom restart function for use in restart_on_change contexts. Tenacity
        retry enabled based on verification of connectivity.

        :side effect: Calls service_stop and service_start on the mysql-router
                      service(s).
        :returns: This function is called for its side effect
        :rtype: None
        """
        ch_core.hookenv.log(
            "Custom restart of {}".format(service_name), "DEBUG")
        self.service_stop(service_name)
        self.service_start(service_name)
        # Only raise an exception if it matches
        # mysql.MySQLdb._exceptions.OperationalError error 2013
        # LP Bug #1915842
        self.check_mysql_connection(
            reraise_on=[self._waiting_for_initial_communication_packet_error])
