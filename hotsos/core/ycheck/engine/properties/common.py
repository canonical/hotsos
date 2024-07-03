import builtins
import importlib
import inspect
from collections import UserDict

from propertree.propertree2 import (
    PTreeOverrideBase,
    PTreeMappedOverrideBase,
    PTreeSection,
)
from hotsos.core.log import log
from hotsos.core.host_helpers.config import ConfigBase


class ImportPathIsNotAClass(Exception):
    def __init__(self, msg):
        self.msg = msg
        super().__init__()


class YDefsSection(PTreeSection):

    def __init__(self, name, content, *args, context=None, **kwargs):
        """
        @param name: name of defs group
        @param content: defs tree of type dict
        @param context: optional context object. This gets passed to all
                        resolved properties and can be used to share
                        information amongst them. If not provided a new empty
                        one is created.
        """
        super().__init__(name, content, *args,
                         context=context or YDefsContext(), **kwargs)


class YDefsContext(UserDict):
    """
    Provides a way to get/set arbitrary information used as context to a yaml
    defs run. This object is typically passed to a YDefsSection and accessible
    from all override properties as attribute "context".
    """
    def __init__(self, initial_state=None):
        """
        @param initial_state: optional dict to use as initial state.
        """
        super().__init__(initial_state or {})

    def __setitem__(self, key, item):
        # don't print values as they can be very large and e.g. search
        # results will be expanded re-duplicated.
        log.debug("%s setting %s with value of type '%s'",
                  self.__class__.__name__, key, type(item))
        super().__setitem__(key, item)

    def __getattr__(self, key):
        return self.data.get(key)


class PropertyCacheRefResolver():
    """
    This class is used to resolve string references to property cache entries.
    """
    def __init__(self, refstr, pcrr_vars=None, checks=None):
        log.debug("%s: resolving '%s'", self.__class__.__name__, refstr)
        self.refstr = refstr
        if not self.is_valid_cache_ref(refstr):
            msg = ("{} is not a valid property cache reference or variable".
                   format(refstr))
            raise Exception(msg)

        self.vars = pcrr_vars
        self.checks = checks
        if self.reftype == 'checks' and checks is None:
            msg = ("{} is a checks cache reference but checks dict not "
                   "provided".format(refstr))
            raise Exception(msg)

    @property
    def reftype(self):
        """
        These depict the type of property or propertycollection that can be
        referenced.

        Supported formats:
            $varname[:func]
            @checks.<check_name>.<property_name>.<property_cache_key>[:func]
        """
        if self.refstr.startswith('$'):
            return "variable"
        if self.refstr.startswith('@checks.'):
            # This is an implementation of YPropertyChecks
            return "checks"

        raise Exception("unknown ref type")

    @property
    def _ref_body(self):
        """
        Strip the prefix from the reference string.
        """
        if self.reftype == 'variable':
            prefix = "$"
        elif self.reftype == 'checks':
            prefix = "@checks.{}.".format(self.check_name)

        return self.refstr.partition(prefix)[2]

    @classmethod
    def is_valid_cache_ref(cls, refstr):
        """
        Returns True if refstr is a valid property cache reference.

        The criteria for a valid reference is that it must be a string whose
        first character is @.
        """
        if not isinstance(refstr, str):
            return False

        if not (refstr.startswith('@') or refstr.startswith('$')):
            return False

        return True

    @property
    def check_name(self):
        if self.reftype != 'checks':
            raise Exception("ref does not have type 'checks'")

        return self.refstr.partition('@checks.')[2].partition('.')[0]

    @property
    def property_name(self):
        if self.reftype == 'checks':
            return self._ref_body.partition('.')[0]

    @property
    def property_cache_key(self):
        """ Key for PropertyCache. """
        if self.reftype == 'checks':
            _key = self._ref_body.partition('.')[2]
        else:
            raise Exception("not a check reftype")

        # strip func if exists
        return _key.partition(':')[0]

    @property
    def property_cache_value_renderer_function(self):
        """
        This is an optional function name that can be provided as the last
        item in the reference string seperated by a colon.
        """
        if self.reftype == 'checks':
            _key = self._ref_body.partition('.')[2]
        else:
            _key = self._ref_body

        return _key.partition(':')[2]

    @staticmethod
    def apply_renderer(value, func):
        """
        A cache reference or import path can be suffixed with :<function>
        where <function> can be one of two things; either a builtins function
        or one of the extras defined here. Obviously not all builtins can be
        used and their use depends on the type() of value.

        @param value: value to apply renderer function to
        @param func: function to apply to value
        """
        extras = {'comma_join': {
                    'requirements': [lambda value: isinstance(value, list),
                                     lambda value: isinstance(value, dict)],
                    'action': lambda value: ', '.join(value)},
                  'unique_comma_join': {
                    'requirements': [lambda value: isinstance(value, list),
                                     lambda value: isinstance(value, dict)],
                    'action': lambda value: ', '.join(sorted(set(value)))},
                  'first': {
                    'requirements': [lambda value: isinstance(value, list)],
                    'action': lambda value: value[0]},
                  'int_ranges': {
                    'requirements': [lambda value: isinstance(value, list)],
                    'action': ConfigBase.squash_int_range}}

        if func in extras:
            if not any(req(value) for req in extras[func]['requirements']):
                log.warning("attempted to apply '%s' to value of "
                            "type %s", func, type(value))
                return value

            return extras[func]['action'](value)

        return getattr(builtins, func)(value)

    def _get_search_result_group(self, cache_key):
        """
        Extract values at the given group index from all search results.
        """
        val = []
        group = int(cache_key.partition('results_group_')[2])
        for result in self.checks[self.check_name]._search_results:
            if len(result) >= group:
                val.append(result.get(group))

        return sorted(val)

    def resolve(self):
        """
        Resolve value associated with a check property result or variable.

        Values are then run through an optional renderer function.
        """
        if self.reftype == 'checks':
            cache_key = self.property_cache_key
            # This provides an interface to extract the values of specific
            # search result groups.
            if cache_key.startswith('results_group_'):
                val = self._get_search_result_group(cache_key)
            else:
                check_cache = self.checks[self.check_name].cache
                property_cache = getattr(check_cache, self.property_name)
                val = getattr(property_cache, cache_key)
        else:
            varname = self.refstr.partition("$")[2]
            varname = varname.partition(':')[0]
            val = self.vars.resolve(varname)

        if val is None:
            return

        func = self.property_cache_value_renderer_function
        if not func:
            # noop
            return val

        return self.apply_renderer(val, func)


class PropertyCache(UserDict):

    def merge(self, cache):
        if not isinstance(cache, self.__class__):
            log.error("attempt to merge cache failed - provided cache is not "
                      "a %s", type(self.__class__.__name__))
            return

        self.data.update(cache.data)

    @property
    def id(self):
        return id(self)

    def set(self, key, data):
        log.debug("%s: caching key=%s with value=%s", id(self), key, data)
        _current = self.data.get(key)
        if _current and isinstance(_current, dict) and isinstance(data, dict):
            self.data[key].update(data)
        else:
            self.data[key] = data

    def __getattr__(self, key):
        log.debug("%s: fetching key=%s (exists=%s)", self.id, key,
                  key in self.data)
        if key in self.data:
            return self.data[key]


class YPropertyBase(PTreeOverrideBase):

    def __init__(self, *args, **kwargs):
        self._cache = PropertyCache()
        super().__init__(*args, **kwargs)

    def resolve_var(self, name):
        """
        Resolve variable with name to value. This can be used speculatively and
        will return the name as value if it can't be resolved.
        """
        if not name.startswith('$'):
            return name

        if hasattr(self, 'context'):
            if self.context.vars:
                _name = name.partition('$')[2]
                return self.context.vars.resolve(_name)

        log.warning("could not resolve var '%s' - vars not found in "
                    "context", name)

        return name

    @property
    def cache(self):
        """
        All properties get their own cache object that they can use as they
        wish.
        """
        return self._cache

    def _load_from_import_cache(self, key):
        """ Retrieve from global context if one exists.

        @param key: key to retrieve
        """
        if self.context is None:
            log.info("context not available - cannot load '%s'", key)
            return

        # we save all imports in a dict called "import_cache" within the
        # global context so that all properties have access.
        c = getattr(self.context, 'import_cache')
        if c:
            return c.get(key)

    @staticmethod
    def _get_mod_class_from_path(path):
        _mod = path.rpartition('.')[0]
        _cls = path.rpartition('.')[2]
        return _mod, _cls

    @staticmethod
    def _get_class_property_from_path(path, no_property=False):
        log.debug("fetching class and property from path (no_property=%s)",
                  no_property)
        # first strip any factory class info and add back to prop at end.
        _path, _, factinput = path.rpartition(':')
        if _path:
            path = _path
        else:
            factinput = ''

        if no_property:
            _cls = path
            _prop = ''
        else:
            _cls = path.rpartition('.')[0]
            _prop = path.rpartition('.')[2]

        # now put it back if exists
        if factinput:
            log.debug("path is factory (input=%s)", factinput)
            _prop += ":" + factinput

        return _cls, _prop

    def _add_to_import_cache(self, key, value):
        """ Save in the global context if one exists.

        @param key: key to save
        @param value: value to save
        """
        if self.context is None:
            log.info("context not available - cannot save '%s'", key)
            return

        c = getattr(self.context, 'import_cache')
        if c:
            c[key] = value
        else:
            c = {key: value}
            setattr(self.context, 'import_cache', c)

    def get_cls(self, import_str):
        """ Import and instantiate Python class.

        @param import_str: import path to Python class.
        """
        ret = self._load_from_import_cache(import_str)
        if ret:
            log.debug("instantiating class %s (from_cache=True)", import_str)
            return ret

        log.debug("instantiating class %s (from_cache=False)", import_str)
        mod, cls_name = self._get_mod_class_from_path(import_str)
        try:
            _mod = importlib.import_module(mod)
            ret = getattr(_mod, cls_name)
            # NOTE: we don't use isclass() since it doesn't work with
            # mock.MagicMock in tests.
            if inspect.ismodule(ret):
                log.debug("%s is not a class", ret)
                raise ImportPathIsNotAClass(import_str)
        except ImportPathIsNotAClass:
            raise
        except Exception:
            log.exception("failed to import class %s from %s", cls_name, mod)
            raise

        self._add_to_import_cache(import_str, ret)
        return ret

    def get_property(self, import_str):
        """
        Import and fetch value of a Python property or factory.

        If the path is to a property, the property name is expected to be after
        the last '.' with the preceding name being the parent class.

        A factory path is identified as having a ':' delimiter which denotes
        the input and optional attribute to call on the factory object. In
        this case the field prior to the delim is the path to the factory class
        itself with an optional input.

        @param import_str: a path to a Python property or Factory.
        """
        ret = self._load_from_import_cache(import_str)
        if ret:
            log.debug("calling property %s (from_cache=True)", import_str)
            return ret

        log.debug("calling property %s (from_cache=False)", import_str)
        _cls, _prop = self._get_class_property_from_path(import_str)
        try:
            try:
                cls = self.get_cls(_cls)
            except ImportPathIsNotAClass:
                # support case where factory has no attribute
                log.debug("trying again without property")
                _cls, _prop = self._get_class_property_from_path(
                                                              import_str,
                                                              no_property=True)
                cls = self.get_cls(_cls)
        except Exception:
            log.exception("class '%s' import failed", _cls)
            raise

        key = "{}.object".format(cls)
        cls_inst = self._load_from_import_cache(key)
        if not cls_inst:
            try:
                cls_inst = cls(global_searcher=self.context.global_searcher)
            except TypeError:
                cls_inst = cls()

            self._add_to_import_cache(key, cls_inst)

        if ':' in _prop:
            # property is for a factory object
            fattr, _, finput = _prop.partition(':')
            if fattr:
                properties = [finput, fattr]
            else:
                properties = [finput]
        else:
            properties = [_prop]

        _obj = cls_inst
        for _prop in properties:
            try:
                _obj = getattr(_obj, _prop)
            except Exception:
                log.exception("failed to import and call property %s",
                              import_str)

                raise

        self._add_to_import_cache(import_str, _obj)
        return _obj

    @staticmethod
    def get_method(import_str):
        """ Import and instantiate Python class then call method.

        @param import_str: import path to Python class with method name after
                           the final '.'.
        """
        log.debug("calling method %s", import_str)
        mod = import_str.rpartition('.')[0]
        method = import_str.rpartition('.')[2]
        class_name = mod.rpartition('.')[2]
        mod = mod.rpartition('.')[0]
        cls = getattr(importlib.import_module(mod), class_name)
        try:
            ret = getattr(cls(), method)()
        except Exception:
            log.exception("failed to import and call method %s", import_str)
            raise

        return ret

    @staticmethod
    def get_attribute(import_str):
        log.debug("fetching attribute %s", import_str)
        mod = import_str.rpartition('.')[0]
        attr = import_str.rpartition('.')[2]
        try:
            ret = getattr(importlib.import_module(mod), attr)
        except Exception as exc:
            log.exception("failed to get module attribute %s", import_str)

            # propertree.PTreeOverrideBase swallows AttributeError so need to
            # convert to something else.
            if isinstance(exc, AttributeError):
                raise ImportError from exc

            raise

        return ret

    def get_import(self, import_str):
        """
        First attempt to treat import string as a class property then try
        module attribute.
        """
        try:
            return self.get_property(import_str)
        except TypeError as exc:
            log.debug("get_property failed, trying get_attribute: %s", exc)

        return self.get_attribute(import_str)


class YPropertyOverrideBase(YPropertyBase, PTreeOverrideBase):
    pass


class YPropertyMappedOverrideBase(YPropertyBase, PTreeMappedOverrideBase):
    pass
