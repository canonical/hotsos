import os

from charms.unit_test import patch_module, identity, MockKV, flags, MockEndpoint


ch = patch_module("charmhelpers")
ch.core.hookenv.atexit = identity
ch.core.hookenv.charm_dir.return_value = "charm_dir"
ch.core.unitdata.kv.return_value = MockKV()

reactive = patch_module("charms.reactive")
reactive.when.return_value = identity
reactive.when_all.return_value = identity
reactive.when_any.return_value = identity
reactive.when_not.return_value = identity
reactive.when_not_all.return_value = identity
reactive.when_none.return_value = identity
reactive.hook.return_value = identity
reactive.set_flag.side_effect = flags.add
reactive.clear_flag.side_effect = flags.discard
reactive.set_state.side_effect = flags.add
reactive.remove_state.side_effect = flags.discard
reactive.toggle_flag.side_effect = lambda f, s: (
    flags.add(f) if s else flags.discard(f)
)
reactive.is_flag_set.side_effect = lambda f: f in flags
reactive.is_state.side_effect = lambda f: f in flags
reactive.get_flags.side_effect = lambda: sorted(flags)
reactive.get_unset_flags.side_effect = lambda *f: sorted(set(f) - flags)

reactive.Endpoint = MockEndpoint

os.environ["JUJU_MODEL_UUID"] = "test-1234"
os.environ["JUJU_UNIT_NAME"] = "test/0"
os.environ["JUJU_MACHINE_ID"] = "0"
os.environ["JUJU_AVAILABILITY_ZONE"] = ""
