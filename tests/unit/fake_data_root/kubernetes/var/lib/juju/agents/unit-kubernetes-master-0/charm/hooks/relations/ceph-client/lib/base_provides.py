# from charmhelpers.core import hookenv
from charmhelpers.core.hookenv import (
    relation_set,
)
from charms.reactive import RelationBase
from charms.reactive import hook
from charms.reactive import scopes
# from charms.reactive import is_state
# from charms.reactive import not_unless


class CephProvides(RelationBase):
    scope = scopes.UNIT

    @hook('{provides:ceph-client}-relation-{joined,changed}')
    def changed(self):
        self.set_state('{relation_name}.connected')
        # service = hookenv.remote_service_name()
        conversation = self.conversation()
        if conversation.get_remote('broker_req'):
            self.set_state('{relation_name}.broker_requested')

    def provide_auth(self, service, key, auth_supported, public_address):
        """
        Provide a token to a requesting service.
        :param str service: The service which requested the key
        :param str key: The key to access Ceph
        :param str auth_supported: Supported auth methods
        :param str public_address: Ceph's public address
        """
        conversation = self.conversation(scope=service)
        # print("Conversation is ", conversation)
        # key is a keyword argument to the set_remote function so we have to
        # set it separately.
        relation_set(
            relation_id=conversation.namespace,
            relation_settings={'key': key})
        opts = {
            'auth': auth_supported,
            'ceph-public-address': public_address,
        }
        conversation.set_remote(**opts)

    def requested_keys(self):
        """
        Return a list of tuples mapping a service name to the key name
        requested by that service.
        Example usage::
            for service, key in ceph.requested_keys():
                ceph.provide_auth(service, key, auth, public_address)
        """
        for conversation in self.conversations():
            service = conversation.scope
            key = self.requested_key(service)
            if key is None:
                yield service

    def requested_key(self, service):
        """
        Return the key provided to the requesting service.
        """
        return self.conversation(scope=service).get_remote('key')

    def provide_broker_token(self, service, unit_response_key, token):
        """
        Provide a token to a requesting service.
        :param str service: The service which requested the key
        :param str unit_response_key: The unique key for the unit
        :param str token: Broker token top provide
        """
        conversation = self.conversation(scope=service)

        # broker_rsp is being left for backward compatibility,
        # unit_response_key superscedes it
        conversation.set_remote(**{
            'broker_rsp': token,
            unit_response_key: token,
        })

    def requested_tokens(self):
        """
        Return a list of tuples mapping a service name to the token name
        requested by that service.
        Example usage::
            for service, token in ceph.requested_tokens():
                ceph.provide_auth(service, token, auth, public_address)
        """
        for conversation in self.conversations():
            service = conversation.scope
            token = self.requested_token(service)
            yield service, token

    def requested_token(self, service):
        """
        Return the token provided to the requesting service.
        """
        return self.conversation(scope=service).get_remote('broker_req')
