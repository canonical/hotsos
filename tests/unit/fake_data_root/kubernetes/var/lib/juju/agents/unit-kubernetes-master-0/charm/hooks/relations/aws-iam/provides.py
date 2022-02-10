from charms.reactive import Endpoint
from charms.reactive import toggle_flag


# kubernetes-master side
class AWSIAMProvides(Endpoint):

    # called automagically before any decorated handlers, but after
    # flags are set
    def manage_flags(self):
        # we want to make sure all the templates and stuff are written
        # and pods started before we switch the API server over to
        # use the webhook. This is critical for the webhook template
        # since the API server will crash if the file isn't there.
        toggle_flag(self.expand_name('endpoint.{endpoint_name}.available'),
                    self.is_joined)
        toggle_flag(self.expand_name('endpoint.{endpoint_name}.ready'),
                    self.is_joined and all(unit.received['webhook_status']
                                           for unit in self.all_joined_units))

    def get_cluster_id(self):
        """ Gets randomly generated cluster ID. """

        return self.all_joined_units.received['cluster_id']

    def set_api_server_status(self, status):
        """ Sets the status of the Kubernetes API server.

            Args:
                status: Boolean value. True when API server is started
                        and ready to receive requests.
        """

        for relation in self.relations:
            relation.to_publish['api_server_state'] = status
