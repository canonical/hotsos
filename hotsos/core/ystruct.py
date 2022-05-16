# Copyright 2021 Edward Hope-Morley
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import abc
import os
import sys

# Set to True to get debug output
# os.environ['YSTRUCT_DEBUG'] = 'True'


def log(msg):
    _dbg = os.environ.get('YSTRUCT_DEBUG')
    if _dbg and _dbg.lower() == 'true':
        sys.stderr.write("DEBUG: {}\n".format(msg))


class YStructException(Exception):
    pass


class OverrideState(object):
    def __init__(self, owner, name, content):
        self._whoami = "{}.{}".format(owner.__class__.__name__,
                                      self.__class__.__name__)
        log("{}.__init__: {}".format(self._whoami, content))
        self._name = name
        self._content = content

    @property
    def name(self):
        # log("{}.name".format(self.__class__.__name__))
        return self._name

    @property
    def content(self):
        # log("{}.content".format(self.__class__.__name__))
        return self._content

    def __getattr__(self, name):
        # log("{}.__getattr__: {}".format(self.__class__.__name__, name))
        name = name.replace('_', '-')
        if name not in self.content:
            raise AttributeError("'{}' object has no attribute '{}'".
                                 format(self, name))

        return self.content[name]


class OverrideStack(object):
    def __init__(self, owner):
        self._whoami = "{}.{}".format(owner.__class__.__name__,
                                      self.__class__.__name__)
        self.items = []

    def add(self, item):
        log("{}.add: {}".format(self._whoami, item))
        self.items.append(item)
        info = "\nsize: {}\ncontents: {}\n".format(len(self), repr(self))
        log("{} stack info: {}".format(self._whoami, info))

    def __len__(self):
        # log("{}.len ({})".format(self.__class__.__name__, len(self.items)))
        # info = "\ncontents:\n{}\n".format(repr(self))
        # log("{} stack info: {}".format(self.__class__.__name__, info))
        return len(self.items)

    def __repr__(self):
        # log("{}.repr".format(self.__class__.__name__))
        r = []
        for i, item in enumerate(self.items):
            if isinstance(item, OverrideState):
                r.append("[{}] {} - {} {}".format(i, item.__class__.__name__,
                                                  item.name,
                                                  item.content))
            else:
                r.append("[{}] {} depth={}".format(i, item.__class__.__name__,
                                                   len(item)))

        return '\n'.join(r)

    @property
    def current(self):
        """ Return most recent object if available. """
        if len(self.items):  # pylint: disable=C1801
            return self.items[-1]

    def __iter__(self):
        log("{}.__iter__".format(self._whoami))
        for item in self.items:
            yield item


class OverrideBase(abc.ABC):

    def __init__(self, name, content, *args, **kwargs):
        self._whoami = self.__class__.__name__
        super().__init__(*args, **kwargs)
        log("{}.__init__: {} {}".format(self._whoami, name, content))
        self._override_resolved_name = name
        self._stack = OverrideStack(self)

    @abc.abstractclassmethod
    def _override_keys(cls):
        """ Must be implemented and return a list of one or more unique keys
        that will be used to identify this override.
        """

    @property
    def _override_name(self):
        """ This is the key name that was used to resolve this override. """
        log("{}._override_name".format(self._whoami))
        return self._override_resolved_name

    @property
    def content(self):
        # log("{}.content ({})".format(self._whoami,
        #     len(self._stack)))
        if len(self._stack):
            return self._stack.current.content

    def add(self, name, content):
        log("{}.add: {} {}".format(self._whoami, name, content))
        self._stack.add(OverrideState(self, name, content))

    def __len__(self):
        return len(self._stack)

    def __iter__(self):
        log("{}.__iter__".format(self._whoami))
        for item in self._stack:
            yield self.__class__(item.name, item.content)

    @abc.abstractmethod
    def __getattr__(self, name):
        """ Each implementation must have their own means of lookups. """


class YStructOverrideBase(OverrideBase):

    def __init__(self, name, content, *args, **kwargs):
        super().__init__(name, content, *args, **kwargs)
        self.add(name, content)

    def __getattr__(self, name):
        log("{}.__getattr__: {}".format(self._whoami, name))
        if len(self._stack):
            # none is allowed as a return value
            return getattr(self._stack.current, name)

        raise AttributeError("'{}' object has no attribute '{}'".
                             format(self, name))


class YStructOverrideSimpleString(OverrideBase):

    @classmethod
    def _override_keys(cls):
        return ['__simple_string__']

    def __init__(self, name, content, *args, **kwargs):
        super().__init__(name, content, *args, **kwargs)
        self.add(name, content)

    def __str__(self):
        return self.content

    def __getattr__(self, name):
        raise AttributeError("'{}' object has no attribute '{}'".
                             format(self, name))


class MappedOverrideState(object):

    def __init__(self, owner, name, content, member_keys):
        self._whoami = "{}.{}".format(owner.__class__.__name__,
                                      self.__class__.__name__)
        self._name = name
        self._content = content
        self._member_stacks = {}
        self._member_keys = member_keys

    @property
    def name(self):
        # log("{}.name".format(self._whoami))
        return self._name

    @property
    def content(self):
        # log("{}.content".format(self._whoami))
        _content = {}
        for name, stack in self._member_stacks.items():
            _content.update({name: stack})

        return _content

    def add_member(self, name, instance):
        log("{}.add_member: {} {}".format(self._whoami, name, instance))
        if name not in self._member_stacks:
            self._member_stacks[name] = OverrideStack(self)

        self._member_stacks[name].add(instance)
        info = "\nsize: {}\ncontents:\n{}\n".format(len(self), repr(self))
        log("{} stack info: {}".format(self._whoami, info))

    def __len__(self):
        return len(self._member_stacks)

    def __repr__(self):
        log("{}.repr".format(self._whoami))
        r = []
        for name, stack in self._member_stacks.items():
            r.append("[{}] depth={} ".format(name, len(stack)))

        return '\n'.join(r)

    def __iter__(self):
        for member in self._member_stacks.values():
            for item in member:
                yield item

    def __getattr__(self, name):
        log("{}.__getattr__: {}".format(self._whoami, name))
        name = name.replace('_', '-')
        if name in self._member_stacks:
            member = self._member_stacks[name]
            if len(member) > 1:
                return member
            else:
                return member.current

        if name in self._member_keys:
            # allow members to be empty
            return None

        raise AttributeError("'{}' object has no attribute '{}'".
                             format(self, name))


class YStructMappedOverrideBase(OverrideBase):

    def __init__(self, name, content, *args, **kwargs):
        super().__init__(name, content, *args, **kwargs)
        self._stack = OverrideStack(self)
        self._current = None
        self.add(name, content)

    @abc.abstractclassmethod
    def _override_mapped_member_types(cls):
        """ All mapped override implementations must implement this as a list
        of override types that can be found within or in lieu of the primary
        override_keys.
        """

    @property
    def valid_parse_content_types(self):
        """ Override this if you want to restrict what content can be parsed
        e.g. of the content only contains dicts as properties and not lists of
        properties we can constrain that here.
        """
        return [dict, list]

    def get_member_with_key(self, key):
        log("{}.get_member_with_key: {}".format(self._whoami, key))
        for m in self._override_mapped_member_types():
            if key in m._override_keys():
                return m

    @property
    def member_keys(self):
        keys = []
        for m in self._override_mapped_member_types():
            keys += m._override_keys()

        return keys

    @property
    def members(self):
        """
        This combines iterating over the stack with iterating over the stack
        of each item on the stack. This mainly makes sense in scenarios where
        the depth of the local stack is 1.
        """
        log("{}.members (depth={})".format(self._whoami, len(self._stack)))
        for item in self._stack:
            log("{}.__iter__ item={} ({})".
                format(self._whoami, item.__class__.__name__, repr(item)))
            for _item in item:
                yield _item

    def __iter__(self):
        log("{}.__iter__ ({})".format(self._whoami, repr(self._stack)))
        for item in self._stack:
            log("{}.__iter__ item={} ({})".
                format(self._whoami, item.__class__.__name__, repr(item)))
            yield item

    def add(self, name, content):
        log("{}.add: {} {} current={}".format(self._whoami, name,
                                              content, self._current))
        if not self._current:
            state = MappedOverrideState(self, name, content, self.member_keys)
        else:
            state = self._current

        if name in self._override_keys():
            self._current = None
            state = MappedOverrideState(self, name, content, self.member_keys)
            if type(content) in self.valid_parse_content_types:
                mapping_members = self._override_mapped_member_types()
                s = YStructSection(name, content,
                                   override_handlers=mapping_members)
                for name in self.member_keys:
                    if hasattr(s, name):
                        obj = getattr(s, name)
                        if obj is not None:
                            state.add_member(name, obj)

                for obj in s.get_resolved_by_type(YStructOverrideSimpleString):
                    state.add_member(obj._override_name, obj)
            else:
                log("{}.add: content type '{}' not parsable ({}) so treating "
                    "as {}".format(self._whoami, type(content),
                                   self.valid_parse_content_types,
                                   YStructOverrideSimpleString.__name__)),
                if type(content) == str:
                    obj = YStructOverrideSimpleString(content, content)
                    state.add_member(content, obj)
                else:
                    for item in content:
                        obj = YStructOverrideSimpleString(item, item)
                        state.add_member(item, obj)

            self._stack.add(state)
        else:
            handler = self.get_member_with_key(name)
            obj = handler(name, content)
            state.add_member(name, obj)
            if not self._current:
                self._current = state
                self._stack.add(state)

    def __getattr__(self, name):
        log("{}.__getattr__: {}".format(self._whoami, name))
        name = name.replace('_', '-')
        if len(self._stack):
            members = self._stack.current._member_stacks
            if name in members:
                return members[name].current

        if name in self.member_keys:
            # allow members to be empty
            return None

        raise AttributeError("'{}' object has no attribute '{}'".
                             format(self, name))


class YStructOverrideManager(object):

    def __init__(self, handlers=None, manager=None):
        self.allow_stacking = False
        self._resolved = {}
        self._resolved_mapped = {}
        if manager:
            # clone it
            self._handlers = manager._handlers
            self._mappings = manager._mappings
            self._resolved.update(manager._resolved)
        else:
            self._handlers = []
            self._mappings = []
            for h in handlers:
                if issubclass(h, YStructMappedOverrideBase):
                    self._mappings.append(h)
                else:
                    self._handlers.append(h)

    def switch_to_stacked(self):
        log("{}.switch_to_stacked".format(self.__class__.__name__))
        self.allow_stacking = True
        self._resolved = {}

    def get_mapping(self, name):
        for mapping in self._mappings:
            if name in mapping._override_keys():
                return mapping, None

            for member in mapping._override_mapped_member_types():
                if name in member._override_keys():
                    return mapping, member

        return None, None

    def get_handler(self, name):
        for h in self._handlers:
            if name in h._override_keys():
                return h

    def get_resolved_by_type(self, otype):
        _results = []
        for item in self._resolved.values():
            if isinstance(item, otype):
                _results.append(item)

        return _results

    def get_resolved(self, name):
        log("{}.get_resolved: {}".format(self.__class__.__name__, name))
        name = name.replace('_', '-')
        return self._resolved.get(name)

    def add_resolved(self, name, content, handler, override_name=None,
                     add_member=False):
        log("{}.add_resolved: {} {} {} {} add_member={}".
            format(self.__class__.__name__, name, content, handler,
                   override_name, add_member))
        resolved_obj = self._resolved.get(name)
        resolved_name = name
        if override_name:
            name = override_name

        if resolved_obj and (self.allow_stacking or add_member):
            resolved_obj.add(name, content)
        else:
            self._resolved[resolved_name] = handler(name, content)

    def resolve(self, name, content):
        log("{}.resolve: {} {}".format(self.__class__.__name__, name,
                                       content))
        if name == content:
            self.add_resolved(name, content, YStructOverrideSimpleString)
            return

        handler = self.get_handler(name)
        if handler:
            self.add_resolved(name, content, handler)
            return

        mapping, member = self.get_mapping(name)
        if mapping:
            if not member:
                self.add_resolved(name, content, mapping)
                return

            map_name = mapping._override_keys()[0]
            add_member = False
            if map_name in self._resolved:
                handler = member
                add_member = True
            else:
                handler = mapping

            self.add_resolved(map_name, content, handler, override_name=name,
                              add_member=add_member)
            self._resolved_mapped[name] = map_name

    @property
    def resolved(self):
        _r = {}
        _r.update(self._resolved)
        _r.update(self._resolved_mapped)
        return _r


class YStructSection(object):
    def __init__(self, name, content, parent=None, root=None,
                 override_handlers=None, override_manager=None):
        if root is None:
            self.root = self
        else:
            self.root = root

        log("\n{}.__init__: {} {}".format(self.__class__.__name__, name,
                                          content))
        self.name = name
        self.parent = parent
        self.content = content
        self.sections = []

        if override_manager:
            self.manager = YStructOverrideManager(manager=override_manager)
        else:
            self.manager = YStructOverrideManager(handlers=override_handlers)

        self.run()

    def _find_leaf_sections(self, section):
        if section.is_leaf:
            return [section]

        leaves = []
        for s in section.sections:
            leaves += self._find_leaf_sections(s)

        return leaves

    @property
    def branch_sections(self):
        return list(set([s.parent for s in self.leaf_sections]))

    @property
    def leaf_sections(self):
        return self._find_leaf_sections(self)

    @property
    def is_leaf(self):
        return self.content and len(self.sections) == 0

    def __getattr__(self, name):
        log("{}.__getattr__: {}".format(self.__class__.__name__, name))
        return self.manager.get_resolved(name)

    def get_resolved_by_type(self, otype):
        return self.manager.get_resolved_by_type(otype)

    def run(self):
        if type(self.content) == list:
            self.manager.switch_to_stacked()
            for _ref, item in enumerate(self.content):
                log("{}.run: item={}".format(self.__class__.__name__, item))
                if type(item) == str:
                    self.manager.resolve(item, item)
                else:
                    for name, content in item.items():
                        self.manager.resolve(name, content)
        else:
            if type(self.content) != dict:
                raise YStructException("undefined override '{}'".
                                       format(self.name))

            # first get all overrides at this level
            for name, content in self.content.items():
                self.manager.resolve(name, content)

            for name, content in self.content.items():
                if name in self.manager.resolved:
                    continue

                s = YStructSection(name, content, parent=self, root=self.root,
                                   override_manager=self.manager)
                self.sections.append(s)

        log("{}.__init__: {} END\n".format(self.__class__.__name__,
                                           self.name))
