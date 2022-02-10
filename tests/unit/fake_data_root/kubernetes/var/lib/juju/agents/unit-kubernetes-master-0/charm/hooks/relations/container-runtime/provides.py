from charms.reactive import (
    Endpoint,
    toggle_flag
)


class ContainerRuntimeProvides(Endpoint):
    def manage_flags(self):
        toggle_flag(self.expand_name('endpoint.{endpoint_name}.available'),
                    self.is_joined)

    def _get_config(self, key):
        """
        Get the published configuration for a given key.

        :param key: String dict key
        :return: String value for given key
        """
        return self.all_joined_units.received.get(key)

    def get_nvidia_enabled(self):
        """
        Get the published nvidia config.

        :return: String
        """
        return self._get_config(key='nvidia_enabled')

    def get_runtime(self):
        """
        Get the published runtime config.

        :return: String
        """
        return self._get_config(key='runtime')

    def get_socket(self):
        """
        Get the published socket config.

        :return: String
        """
        return self._get_config(key='socket')

    def set_config(self, sandbox_image=None):
        """
        Set the configuration to be published.

        :param sandbox_image: String to optionally override the sandbox image
        :return: None
        """
        for relation in self.relations:
            relation.to_publish.update({
                'sandbox_image': sandbox_image
            })
