import sys
from importlib import import_module
from pathlib import Path


def import_layer_libs():
    """
    Ensure that all layer libraries are imported.

    This makes it possible to do the following:

        from charms import layer

        layer.foo.do_foo_thing()

    Note: This function must be called after bootstrap.
    """
    for module_file in Path('lib/charms/layer').glob('*'):
        module_name = module_file.stem
        if module_name in ('__init__', 'basic', 'execd') or not (
            module_file.suffix == '.py' or module_file.is_dir()
        ):
            continue
        import_module('charms.layer.{}'.format(module_name))


# Terrible hack to support the old terrible interface.
# Try to get people to call layer.options.get() instead so
# that we can remove this garbage.
# Cribbed from https://stackoverfLow.com/a/48100440/4941864
class OptionsBackwardsCompatibilityHack(sys.modules[__name__].__class__):
    def __call__(self, section=None, layer_file=None):
        if layer_file is None:
            return self.get(section=section)
        else:
            return self.get(section=section,
                            layer_file=Path(layer_file))


def patch_options_interface():
    from charms.layer import options
    if sys.version_info.minor >= 5:
        options.__class__ = OptionsBackwardsCompatibilityHack
    else:
        # Py 3.4 doesn't support changing the __class__, so we have to do it
        # another way.  The last line is needed because we already have a
        # reference that doesn't get updated with sys.modules.
        name = options.__name__
        hack = OptionsBackwardsCompatibilityHack(name)
        hack.get = options.get
        sys.modules[name] = hack
        sys.modules[__name__].options = hack


try:
    patch_options_interface()
except ImportError:
    # This may fail if pyyaml hasn't been installed yet. But in that
    # case, the bootstrap logic will try it again once it has.
    pass
