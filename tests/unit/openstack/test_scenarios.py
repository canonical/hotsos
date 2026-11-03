from tests.unit import utils
from tests.unit.openstack.test_openstack import TestOpenstackBase


@utils.load_templated_tests('scenarios/openstack')
class TestOpenstackScenarios(TestOpenstackBase):
    """
    Scenario tests can be written using YAML templates that are auto-loaded
    into this test runner. This is the recommended way to write tests for
    scenarios. It is however still possible to write the tests in Python if
    required. See https://hotsos.readthedocs.io/en/latest/contrib/testing.html
    for more information.
    """
