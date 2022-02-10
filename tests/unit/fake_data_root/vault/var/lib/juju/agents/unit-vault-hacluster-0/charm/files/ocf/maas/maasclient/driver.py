# Copyright 2016 Canonical Ltd
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

import logging

log = logging.getLogger('vmaas.main')


class Response(object):
    """Response for the API calls to use internally

    The status_code member is to make it look a bit like a requests Response
    object so that it can be used in the retry decorator.
    """
    def __init__(self, ok=False, data=None, status_code=None):
        self.ok = ok
        self.data = data
        self.status_code = status_code

    def __nonzero__(self):
        """Allow boolean comparison"""
        return bool(self.ok)


class MAASDriver(object):
    """
    Defines the commands and interfaces for generically working with
    the MAAS controllers.
    """

    def __init__(self, api_url, api_key):
        self.api_url = api_url
        self.api_key = api_key

    def _get_system_id(self, obj):
        """
        Returns the system_id from an object or the object itself
        if the system_id is not found.
        """
        if 'system_id' in obj:
            return obj.system_id
        return obj

    def _get_uuid(self, obj):
        """
        Returns the UUID for the MAAS object. If the object has the attribute
        'uuid', then this method will return obj.uuid, otherwise this method
        will return the object itself.
        """
        if hasattr(obj, 'uuid'):
            return obj.uuid
        else:
            log.warning("Attr 'uuid' not found in %s" % obj)

        return obj
