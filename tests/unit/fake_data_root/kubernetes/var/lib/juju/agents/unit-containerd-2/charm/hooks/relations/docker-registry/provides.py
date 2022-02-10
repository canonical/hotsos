"""
This is the provides side of the interface layer, for use only by the
docker-registry charm itself.
The flags that are set by the provides side of this interface are:
* **`endpoint.{endpoint_name}.requested`** This flag is set when there is
  a new or updated request by a remote unit for docker-registry config.
  The docker-registry integration charm should then iterate over each
  request, perform whatever actions are necessary to satisfy those requests,
  and then mark them as complete.
"""

from operator import attrgetter

from charms.reactive import Endpoint
from charms.reactive import when
from charms.reactive import toggle_flag, clear_flag


class DockerRegistryProvides(Endpoint):
    """
    Example usage:
    ```python
    from charms.reactive import when, endpoint_from_flag
    from charms import layer
    @when('endpoint.docker-registry.joined')
    def configure_client():
        registry = endpoint_from_flag('endpoint.docker-registry.joined')
        registry.set_registry_config(netloc, **data)
    @when('endpoint.docker-registry.requests-pending')
    def handle_image_request():
        registry = endpoint_from_flag('endpoint.docker-registry.requests-pending')
        for request in registry.requests:
            request.image_data(name, tag)
        registry.mark_completed()
    ```
    """

    @when('endpoint.{endpoint_name}.changed')
    def check_requests(self):
        toggle_flag(self.expand_name('requests-pending'),
                    len(self.requests) > 0)
        clear_flag(self.expand_name('changed'))

    @property
    def requests(self):
        """
        A list of the new or updated #RegistryRequests that
        have been made.
        """
        if not hasattr(self, '_requests'):
            all_requests = [RegistryRequest(unit)
                            for unit in self.all_joined_units]
            is_changed = attrgetter('is_changed')
            self._requests = list(filter(is_changed, all_requests))
        return self._requests

    def mark_completed(self):
        """
        Mark all requests as completed and remove the `requests-pending` flag.
        """
        clear_flag(self.expand_name('requests-pending'))
        self._requests = []

    def set_registry_config(self, registry_netloc, **kwargs):
        """
        Set the registry config. Minimally, a network location is required.
        Other data (auth, tls, etc) may also be set.
        """
        data = {'registry_netloc': registry_netloc}
        for k, v in kwargs.items():
            data[k] = v
        for relation in self.relations:
            relation.to_publish.update(data)


class RegistryRequest:
    """
    A request from a single remote unit to include an image in our registry.
    """
    def __init__(self, unit):
        self._unit = unit

    @property
    def _to_publish(self):
        return self._unit.relation.to_publish

    @property
    def has_image(self):
        """
        Whether or not an image has been processed via `image_data`.
        """
        return 'image' in self._unit.relation.to_publish

    @property
    def is_changed(self):
        """
        Whether this request has changed since the last time it was
        marked completed (if ever).
        """
        return not self.has_image

    @property
    def unit_name(self):
        return self._unit.unit_name

    def image_data(self, image, tag):
        """
        Set the image characteristics this request.
        """
        data = {
            'image': image,
            'tag': tag,
        }
        self._unit.relation.to_publish.update(data)
