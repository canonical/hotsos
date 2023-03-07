import abc
import builtins
import inspect
import importlib

from propertree import (
    PTreeOverrideBase,
    PTreeMappedOverrideBase,
    PTreeSection,
)

from hotsos.core.log import log

YPropertiesCatalog = []


class ImportPathIsNotAClass(Exception):
    def __init__(self, msg):
        self.msg = msg
        super().__init__()


class YDefsSection(PTreeSection):

    def __init__(self, name, content, context=None):
        """
        @param name: name of defs group
        @param content: defs tree of type dict
        @param context: optional context object. This gets passed to all
                        resolved properties and can be used to share
                        information amongst them. If not provided a new empty
                        one is created.
        """
        super().__init__(name, content, override_handlers=YPropertiesCatalog,
                         context=context or YDefsContext())


def add_to_property_catalog(c):
    """
    Add property implementation to the global catalog.
    """
    YPropertiesCatalog.append(c)
    return c


def cached_yproperty_attr(f):
    """
    This can be used to cache a yproperty attribute property e.g. to avoid
    expensive re-execution of that property with successive calls.
    """
    @property
    def _inner(inst):
        # we prefix the keyname so as to avoid collisions with non attribute
        # items added to the cache.
        key = "__yproperty_attr__{}".format(f.__name__)
        ret = getattr(inst.cache, key)
        if ret is not None:
            return ret

        ret = f(inst)
        inst.cache.set(key, ret)
        return ret

    return _inner


class YDefsContext(object):
    """
    Provides a way to get/set arbitrary information used as context to a yaml
    defs run. This object is typically passed to a YDefsSection and accessible
    from all override properties as attribute "context".
    """
    def __init__(self, initial_state=None):
        """
        @param initial_state: optional dict to use as initial state.
        """
        self._ydefs_context = initial_state or {}

    def __setattr__(self, key, value):
        if key != '_ydefs_context':
            log.debug("%s setting %s=%s", self.__class__.__name__, key, value)
            self._ydefs_context[key] = value
            return

        super().__setattr__(key, value)

    def __getattr__(self, key):
        return self._ydefs_context.get(key)


class PropertyCacheRefResolver(object):
    """
    This class is used to resolve string references to property cache entries.
    """
    def __init__(self, refstr, vars=None, checks=None):
        log.debug("%s: resolving '%s'", self.__class__.__name__, refstr)
        self.refstr = refstr
        if not self.is_valid_cache_ref(refstr):
            msg = ("{} is not a valid property cache reference or variable".
                   format(refstr))
            raise Exception(msg)

        self.vars = vars
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
        elif self.refstr.startswith('@checks.'):
            # This is an implementation of YPropertyChecks
            return "checks"
        else:
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
        if type(refstr) != str:
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

    def apply_renderer_function(self, value):
        """
        The last section of a ref string can be a colon followed by a function
        name which itself can be one of two things; any method supported by
        builtins or "comma_join".
        """
        func = self.property_cache_value_renderer_function
        if func:
            if func == "comma_join":
                # needless to say this will only work with lists, dicts etc.
                return ', '.join(value)

            return getattr(builtins, func)(value)

        return value

    def resolve(self):
        if self.reftype == 'checks':
            check_cache = self.checks[self.check_name].cache
            property_cache = getattr(check_cache, self.property_name)
            val = getattr(property_cache, self.property_cache_key)
        else:
            varname = self.refstr.partition("$")[2]
            varname = varname.partition(':')[0]
            val = self.vars.resolve(varname)

        if val is None:
            return

        return self.apply_renderer_function(val)


class PropertyCache(object):

    def __init__(self):
        self._property_cache_data = {}

    def merge(self, cache):
        if type(cache) != self.__class__:
            log.error("attempt to merge cache failed - provided cache is not "
                      "a %s", type(self.__class__.__name__))
            return

        self._property_cache_data.update(cache.data)

    @property
    def id(self):
        return id(self)

    def set(self, key, data):
        log.debug("%s: caching key=%s with value=%s", id(self), key, data)
        _current = self._property_cache_data.get(key)
        if _current and type(_current) == dict and type(data) == dict:
            self._property_cache_data[key].update(data)
        else:
            self._property_cache_data[key] = data

    @property
    def data(self):
        return self._property_cache_data

    def __getattr__(self, key):
        log.debug("%s: fetching key=%s (exists=%s)", self.id, key,
                  key in self.data)
        if key in self.data:
            return self.data[key]


class YPropertyBase(object):

    def __init__(self, *args, **kwargs):
        whoami = self.__class__.__name__
        log.debug("YPropertyBase %s %s (%s)", args, kwargs, whoami)
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
            if self.context.vars:  # pylint: disable=E1101
                _name = name.partition('$')[2]
                return self.context.vars.resolve(_name)  # noqa, pylint: disable=E1101

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
        if not self.context:  # pylint: disable=E1101
            log.info("context not available - cannot load '%s'")
            return

        # we save all imports in a dict called "import_cache" within the
        # global context so that all properties have access.
        c = getattr(self.context, 'import_cache')  # pylint: disable=E1101
        if c:
            return c.get(key)

    def _get_mod_class_from_path(self, path):
        _mod = path.rpartition('.')[0]
        _cls = path.rpartition('.')[2]
        return _mod, _cls

    def _get_class_property_from_path(self, path, no_property=False):
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
        if not self.context:  # pylint: disable=E1101
            log.info("context not available - cannot save '%s'")
            return

        c = getattr(self.context, 'import_cache')  # pylint: disable=E1101
        if c:
            c[key] = value
        else:
            c = {key: value}
            setattr(self.context, 'import_cache', c)  # pylint: disable=E1101

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

    def get_method(self, import_str):
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

    def get_attribute(self, import_str):
        log.debug("fetching attribute %s", import_str)
        mod = import_str.rpartition('.')[0]
        attr = import_str.rpartition('.')[2]
        try:
            ret = getattr(importlib.import_module(mod), attr)
        except Exception as exc:
            log.exception("failed to get module attribute %s", import_str)

            # propertree.PTreeOverrideBase swallows AttributeError so need to
            # convert to something else.
            if type(exc) == AttributeError:
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
        except TypeError:
            log.debug("get_property failed, trying get_attribute")
        except Exception:
            log.exception("get_property failed for unknown reason")

        return self.get_attribute(import_str)


class YPropertyOverrideBase(YPropertyBase, PTreeOverrideBase):
    pass


class YPropertyMappedOverrideBase(YPropertyBase, PTreeMappedOverrideBase):
    pass


class LogicalCollectionHandler(abc.ABC):
    VALID_GROUP_KEYS = ['and', 'or', 'nand', 'nor', 'xor', 'not']
    FINAL_RESULT_OP = 'and'

    @property
    def and_group_stop_on_first_false(self):
        """
        By default we do not process items in an AND group beyond the first
        False result since they will not change the final result. Some
        implementations may want to override this behaviour.
        """
        return True

    def group_exit_condition_met(self, logical_op, result):
        if type(result) != bool:
            log.error("unexpected result type '%s' - unable to determine exit "
                      "condition for logical op='%s'", type(result),
                      logical_op)
            return False

        if logical_op in ['and']:
            if self.and_group_stop_on_first_false and not result:
                log.debug("exit condition met for op='%s'", logical_op)
                return True

        if logical_op in ['nand', 'not']:
            if self.and_group_stop_on_first_false and result:
                log.debug("exit condition met for op='%s'", logical_op)
                return True

        return False

    def eval_ungrouped_item(self, item):
        """
        This is either a single item or a list of items but a not logical
        grouping and therefore the default logical op applies to the result(s)
        i.e. AND.
        """
        final_results = []
        for entry in item:
            result = self.get_item_result_callback(entry,
                                                   is_default_group=True)
            final_results.append(result)

        return final_results

    @abc.abstractmethod
    def get_item_result_callback(self, item, is_default_group=False):
        """
        Must be implemented to evaluate a single item and return its
        result.
        """

    def _is_op_group(self, property):
        return property._override_name in self.VALID_GROUP_KEYS

    def eval_op_group_items(self, logical_op_group):
        """
        Evaluate single group of items and return their results as a list.

        @return: list of boolean values
        """
        logical_op = logical_op_group._override_name
        log.debug("evaluating op group '%s'", logical_op)
        results = []
        num_nested = 0
        num_list = 0
        num_single = 0
        for i, group in enumerate(logical_op_group):
            group_results = []
            log.debug("op group %s", i)
            for member in group:
                if self._is_op_group(member):
                    nested_logical_op = member._override_name
                    log.debug("start processing nested group (%s)",
                              nested_logical_op)
                    result = self.eval_op_group_items(member)
                    log.debug("finish processing nested group (result=%s)",
                              result)
                    group_results.extend(result)
                    num_nested += 1
                    continue

                log.debug("op group member has %s item(s)", len(member))
                if len(member) == 1:
                    group_results.append(self.get_item_result_callback(member))
                    num_single += 1
                    continue

                prev = None
                for entry in member:
                    if (prev is not None and
                            self.group_exit_condition_met(logical_op, prev)):
                        log.debug("result is %s and logical group '%s' exit "
                                  "condition met so stopping further "
                                  "evaluation if this group",
                                  result, logical_op)
                        break

                    result = self.get_item_result_callback(entry)
                    group_results.append(result)
                    prev = result
                    num_list += 1

            results.append(self.apply_op_to_item(logical_op, group_results))

        log.debug("group results (list=%s, nest=%s, single=%s): %s",
                  num_list, num_nested, num_single, results)
        return results

    def apply_op_to_item(self, logical_op, item):
        op_catalog = {'and': lambda r: all(r),
                      'or': lambda r: any(r),
                      'nand': lambda r: not all(r),
                      'not': lambda r: not all(r),
                      'nor': lambda r: not any(r)}

        if logical_op not in op_catalog:
            raise Exception("unknown logical operator '{}' found".
                            format(logical_op))

        result = op_catalog[logical_op](item)
        log.debug("applying %s(%s) -> %s", logical_op, item, result)
        return result

    def eval_op_groups(self, item):
        """
        Evaluate all groups of items and return their results as a list.

        @return: list of boolean values
        """
        final_results = []
        for op in self.VALID_GROUP_KEYS:
            op_group = getattr(item, op)
            if op_group:
                result = self.eval_op_group_items(op_group)
                if result is not None:
                    final_results.extend(result)

        log.debug("op groups results: %s", final_results)
        return final_results

    def run_level(self, level):
        """
        @return: boolean value
        """
        stop_processing = False
        final_results = []
        for item in level:
            final_results.extend(self.eval_op_groups(item))
            for subitem in item:
                # ignore op grouped
                if self._is_op_group(subitem):
                    continue

                results = self.eval_ungrouped_item(subitem)
                final_results.extend(results)
                if self.group_exit_condition_met(self.FINAL_RESULT_OP,
                                                 all(results)):
                    log.debug("result is %s and logical group '%s' exit "
                              "condition met so stopping further evaluation "
                              "if this group",
                              all(results), self.FINAL_RESULT_OP)
                    stop_processing = True
                    break

            if stop_processing:
                break

        return final_results

    def run_collection(self):
        log.debug("run_collection:start (%s)", self._override_name)  # noqa, pylint: disable=E1101
        all_results = self.run_level(self)
        log.debug("all_results: %s", all_results)
        result = all(all_results)
        log.debug("final result=%s", result)
        log.debug("run_collection:end (%s)", self._override_name)  # noqa, pylint: disable=E1101
        return result
