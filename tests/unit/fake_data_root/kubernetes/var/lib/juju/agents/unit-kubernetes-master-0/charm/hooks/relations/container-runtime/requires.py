from charms.reactive import (
    Endpoint,
    clear_flag,
    data_changed,
    is_data_changed,
    toggle_flag
)


class ContainerRuntimeRequires(Endpoint):
    def manage_flags(self):
        toggle_flag(self.expand_name('endpoint.{endpoint_name}.available'),
                    self.is_joined)
        toggle_flag(self.expand_name('endpoint.{endpoint_name}.reconfigure'),
                    self.is_joined and self._config_changed())

    def _config_changed(self):
        """
        Determine if our received data has changed.

        :return: Boolean
        """
        # NB: this call should match whatever we're tracking in handle_remote_config
        return is_data_changed('containerd.remote_config',
                               [self.get_sandbox_image()])

    def handle_remote_config(self):
        """
        Keep track of received data so we can know if it changes.

        :return: None
        """
        clear_flag(self.expand_name('endpoint.{endpoint_name}.reconfigure'))
        # Presently, we only care about one piece of remote config. Expand
        # the list as needed.
        data_changed('containerd.remote_config',
                     [self.get_sandbox_image()])

    def get_sandbox_image(self):
        """
        Get the sandbox image URI if a remote has published one.

        :return: String: remotely configured sandbox image
        """
        return self.all_joined_units.received.get('sandbox_image')

    def set_config(self, socket, runtime, nvidia_enabled):
        """
        Set the configuration to be published.

        :param socket: String uri to runtime socket
        :param runtime: String runtime executable
        :param nvidia_enabled: Boolean nvidia runtime enabled
        :return: None
        """
        for relation in self.relations:
            relation.to_publish.update({
                'socket': socket,
                'runtime': runtime,
                'nvidia_enabled': nvidia_enabled
            })
