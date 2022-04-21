import abc
import builtins
import copy
import importlib

from hotsos.core.log import log
from hotsos.core.ystruct import YAMLDefOverrideBase


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


class PropertyCacheRefResolver(object):
    """
    This class is used to resolve string references to property cache entries.
    """
    def __init__(self, refstr, property=None, checks=None):
        self.refstr = refstr
        if not self.is_valid_cache_ref(refstr):
            msg = ("{} is not a valid property cache reference".format(refstr))
            raise Exception(msg)

        self.property = property
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
            @checks.<check_name>.<property_name>.<property_cache_key>[:func]
            @<property_name>.<property_cache_key>[:func]
        """
        if self.refstr.startswith('@checks.'):
            # This is an implementation of YPropertyChecks
            return "checks"
        else:
            # This is any implementation of YPropertyOverrideBase
            return "property"

    @property
    def _ref_body(self):
        """
        Strip the prefix from the reference string.
        """
        if self.reftype == 'checks':
            prefix = "@checks.{}.".format(self.check_name)
        else:
            prefix = "@{}.".format(self.property.property_name)

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

        if not refstr.startswith('@'):
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

        return self.property.property_name

    @property
    def property_cache_key(self):
        """ Key for PropertyCache. """
        if self.reftype == 'checks':
            _key = self._ref_body.partition('.')[2]
        else:
            _key = self._ref_body

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
        if self.property is None:
            if not self.checks:
                raise Exception("property required in order to resolve cache "
                                "ref")

            check_cache = self.checks[self.check_name].cache
            property_cache = getattr(check_cache, self.property_name)
        else:
            property_cache = self.property.cache

        val = getattr(property_cache, self.property_cache_key)
        if val is None:
            return

        return self.apply_renderer_function(val)


class PropertyCache(object):

    def __init__(self):
        self._data = {}

    def merge(self, cache):
        if type(cache) != PropertyCache:
            log.error("attempt to merge cache failed - provided cache is not "
                      "a %s", type(self))
            return

        self._data.update(cache.cache)

    def set(self, key, data):
        log.debug("%s: caching key=%s with value=%s", id(self), key, data)
        _current = self._data.get(key)
        if _current and type(_current) == dict and type(data) == dict:
            self._data[key].update(data)
        else:
            self._data[key] = data

    @property
    def cache(self):
        return self._data

    def __getattr__(self, key):
        log.debug("%s: fetching key=%s (exists=%s)", id(self), key,
                  key in self.cache)
        if key in self.cache:
            return self.cache[key]


class YPropertyBase(object):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cache = PropertyCache()

    @property
    def cache(self):
        return self._cache

    def get_cls(self, import_str):
        log.debug("instantiating class %s", import_str)
        mod = import_str.rpartition('.')[0]
        class_name = import_str.rpartition('.')[2]
        try:
            return getattr(importlib.import_module(mod), class_name)
        except Exception:
            log.exception("failed to import class %s from %s", class_name, mod)
            raise

    def get_property(self, import_str):
        log.debug("calling property %s", import_str)
        mod = import_str.rpartition('.')[0]
        property = import_str.rpartition('.')[2]
        class_name = mod.rpartition('.')[2]
        mod = mod.rpartition('.')[0]
        cls = getattr(importlib.import_module(mod), class_name)
        try:
            ret = getattr(cls(), property)
        except Exception:
            log.exception("failed to import and call property %s",
                          import_str)

            raise

        return ret

    def get_method(self, import_str):
        log.debug("calling method %s", import_str)
        mod = import_str.rpartition('.')[0]
        property = import_str.rpartition('.')[2]
        class_name = mod.rpartition('.')[2]
        mod = mod.rpartition('.')[0]
        cls = getattr(importlib.import_module(mod), class_name)
        try:
            ret = getattr(cls(), property)()
        except Exception:
            log.exception("failed to import and call method %s",
                          import_str)
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

            # ystruct.YAMLDefOverrideBase swallows AttributeError so need to
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
        except Exception:
            pass

        return self.get_attribute(import_str)


class YPropertyOverrideBase(abc.ABC, YAMLDefOverrideBase, YPropertyBase):

    @abc.abstractproperty
    def property_name(self):
        """
        Every property override must implement this. This name must be unique
        across all properties and will be used to link the property in a
        PropertyCacheRefResolver.
        """


class YPropertyCollectionBase(YPropertyOverrideBase):

    @abc.abstractproperty
    def property_name(self):
        """
        Every property override must implement this. This name must be unique
        across all properties and will be used to link the property in a
        PropertyCacheRefResolver.
        """


class LogicalCollectionMap(object):

    def __init__(self, raw, backend, cache=None):
        self.raw = raw
        self.backend = backend
        self.cache = cache

    def apply(self, item, copy_cache=False):
        if type(item) != dict:
            # i.e. it must be a string
            key = value = item
        else:
            # dict should only have one key
            key, value = copy.deepcopy(item).popitem()

        ret = self.backend[key](value)
        result = ret.result
        if copy_cache and self.cache:
            log.debug("merging cache with item of type %s",
                      ret.__class__.__name__)
            self.cache.merge(ret.cache)

        return result


class LogicalCollectionHandler(object):
    VALID_GROUP_KEYS = ['and', 'or', 'not']
    FINAL_RESULT_OP = 'and'

    def __init__(self, logicmap):
        self.logicmap = logicmap

    def is_group(self, item):
        if type(item) != dict:
            return False

        if set(list(item.keys())).intersection(self.VALID_GROUP_KEYS):
            return True

        return False

    def process_single(self, item, copy_cache=False):
        log.debug("SINGLE: %s", item)
        return self.logicmap.apply(item, copy_cache=copy_cache)

    def process_group(self, item):
        results = {}
        for op, _items in item.items():
            if op not in results:
                results[op] = []

            if type(_items) != list:
                results[op].append(self.process_single(_items))
            else:
                log.debug("op=%s has %s items(s)", op, len(_items))
                for _item in _items:
                    results[op].append(self.process_single(_item))

        return results

    def process_list(self, items):
        results = {}
        for item in items:
            if self.is_group(item):
                log.debug("list:group")
                for op, _results in self.process_group(item).items():
                    if op not in results:
                        results[op] = []

                    results[op].extend(_results)
            else:
                log.debug("list:single")
                # final results always get anded.
                op = self.FINAL_RESULT_OP
                if op not in results:
                    results[op] = []

                results[op].append(self.process_single(item))

        return results

    def __call__(self):
        if type(self.logicmap.raw) == dict:
            if self.is_group(self.logicmap.raw):
                log.debug("items groups provided")
                results = self.process_group(self.logicmap.raw)
            else:
                log.debug("single items provided")
                results = {self.FINAL_RESULT_OP:
                           [self.process_single(self.logicmap.raw,
                                                copy_cache=True)]}
        elif type(self.logicmap.raw) == list:
            log.debug("list of %s items provided", len(self.logicmap.raw))
            results = self.process_list(self.logicmap.raw)
        else:
            results = {self.FINAL_RESULT_OP:
                       [self.process_single(self.logicmap.raw,
                                            copy_cache=True)]}

        final_results = []
        for op in results:
            if op == 'and':
                final_results.append(all(results[op]))
            elif op == 'or':
                final_results.append(any(results[op]))
            elif op == 'not':
                # this is a NOR
                final_results.append(not any(results[op]))
            else:
                log.debug("unknown operator '%s' found in requirement", op)

        result = all(final_results)
        log.debug("final result=%s", result)
        return result
