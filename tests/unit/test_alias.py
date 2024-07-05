from unittest import mock

from hotsos.core.alias import (
    alias,
    AliasRegistry,
    AliasAlreadyInUseError,
    AliasForbiddenError,
)

from . import utils


def dummy_decoratee_ff():
    pass


@mock.patch.dict(AliasRegistry.registry, {})
class TestAlias(utils.BaseTestCase):
    """Unit tests for aliasing."""

    def dummy_decoratee(self):
        pass

    @staticmethod
    def dummy_decoratee_static():
        pass

    @classmethod
    def dummy_decoratee_clsmethod(cls):
        pass

    @property
    def dummy_decoratee_property(self):
        pass

    def test_register_alias(self):
        AliasRegistry.register(name="test", decoratee=self.dummy_decoratee)

    def test_register_resolve_alias_member_fn(self):
        AliasRegistry.register(name="test", decoratee=self.dummy_decoratee)
        v = AliasRegistry.resolve("test")
        self.assertEqual(v, "tests.unit.test_alias.TestAlias.dummy_decoratee")

    def test_register_resolve_alias_free_fn(self):
        AliasRegistry.register(name="test", decoratee=dummy_decoratee_ff)
        v = AliasRegistry.resolve("test")
        self.assertEqual(v, "tests.unit.test_alias.dummy_decoratee_ff")

    def test_register_resolve_alias_static_fn(self):
        AliasRegistry.register(
            name="test", decoratee=self.dummy_decoratee_static)
        v = AliasRegistry.resolve("test")
        self.assertEqual(
            v, "tests.unit.test_alias.TestAlias.dummy_decoratee_static")

    def test_register_resolve_alias_class_fn(self):
        AliasRegistry.register(
            name="test", decoratee=self.dummy_decoratee_clsmethod)
        v = AliasRegistry.resolve("test")
        self.assertEqual(
            v, "tests.unit.test_alias.TestAlias.dummy_decoratee_clsmethod")

    def test_register_duplicate(self):
        AliasRegistry.register(name="test", decoratee=self.dummy_decoratee)

        with self.assertRaises(AliasAlreadyInUseError):
            AliasRegistry.register(name="test", decoratee=self.dummy_decoratee)

    def test_register_forbidden(self):
        with self.assertRaises(AliasForbiddenError):
            AliasRegistry.register(
                name="hotsos.test", decoratee=dummy_decoratee_ff)

    def test_decorator(self):

        @alias("foo")
        def target_method():
            pass

        v = AliasRegistry.resolve("foo")
        self.assertEqual(
            v,
            "tests.unit.test_alias.TestAlias."
            "test_decorator.<locals>.target_method",
        )
