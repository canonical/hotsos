from charms.reactive import (
    Endpoint,
    set_flag,
    clear_flag
)

from charms.reactive import (
    when,
    when_not
)


class ContainerRuntimeRequires(Endpoint):
    @when('endpoint.{endpoint_name}.changed')
    def changed(self):
        set_flag(self.expand_name('endpoint.{endpoint_name}.available'))

    @when_not('endpoint.{endpoint_name}.joined')
    def broken(self):
        clear_flag(self.expand_name('endpoint.{endpoint_name}.available'))

    def set_config(self, name, binary_path):
        """
        Set the configuration to be published.

        :param name: String name of runtime
        :param binary_path: String runtime executable
        :return: None
        """
        for relation in self.relations:
            relation.to_publish.update({
                'name': name,
                'binary_path': binary_path
            })
