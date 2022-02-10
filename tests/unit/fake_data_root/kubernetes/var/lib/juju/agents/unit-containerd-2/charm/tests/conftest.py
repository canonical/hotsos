import os
import sys
from unittest.mock import MagicMock


def identity(x):
    return x


# mock dependencies which we don't care about covering in our tests
ch = MagicMock()
sys.modules['charmhelpers'] = ch
sys.modules['charmhelpers.core'] = ch.core
sys.modules['charmhelpers.core.unitdata'] = ch.core.unitdata
sys.modules['charmhelpers.core.hookenv'] = ch.core.hookenv
sys.modules['charmhelpers.core.host'] = ch.core.host
sys.modules['charmhelpers.core.templating'] = ch.core.templating
sys.modules['charmhelpers.contrib'] = ch.contrib
sys.modules['charmhelpers.contrib.charmsupport'] = ch.contrib.charmsupport

reactive = MagicMock()
sys.modules['charms.reactive'] = reactive
reactive.when.return_value = identity
reactive.when_any.return_value = identity
reactive.when_not.return_value = identity
reactive.when_none.return_value = identity
reactive.hook.return_value = identity

leadership = MagicMock()
sys.modules['charms.leadership'] = leadership

charms = MagicMock()
sys.modules['charms'] = charms
sys.modules['charms.coordinator'] = charms.coordinator
sys.modules['charms.layer'] = charms.layer
sys.modules['charms.layer.hacluster'] = charms.layer.hacluster
sys.modules['charms.layer.kubernetes_common'] = charms.layer.kubernetes_common
sys.modules['charms.layer.nagios'] = charms.layer.nagios

os.environ['JUJU_MODEL_UUID'] = 'test-1234'
