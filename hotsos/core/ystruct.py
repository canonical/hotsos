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
    def __init__(self, owner, content):
        self._whoami = "{}.{}".format(owner.__class__.__name__,
                                      self.__class__.__name__)
        log("{}.__init__: id={} content={}".format(self._whoami, id(self),
                                                   content))
        self._content = content

    @property
    def content(self):
        # log("{}.content".format(self._whoami))
        return self._content

    def __getattr__(self, name):
        # log("{}.__getattr__: {}".format(self._whoami, name))
        _name = name.replace('_', '-')
        if type(self.content) != dict or _name not in self.content:
            raise AttributeError("'{}' object has no attribute '{}'".
                                 format(self._whoami, name))

        return self.content[_name]


class OverrideStack(object):
    def __init__(self, owner):
        self._whoami = "{}.{}".format(owner.__class__.__name__,
                                      self.__class__.__name__)
        self.items = []
        log("{}.__init__ id={} (owner={})".format(self._whoami, id(self),
                                                  id(owner)))

    def push(self, item):
        self.items.append(item)
        log("{}: push (stack_id={}) \n{}\n".format(self._whoami, id(self),
                                                   repr(self)))

    def __len__(self):
        return len(self.items)

    def __repr__(self):
        r = []
        for item in self.items:
            if isinstance(item, OverrideState):
                r.append("[{}] type={} content={}".
                         format(id(item), item._whoami, item.content))
            else:
                r.append("[{}] {} depth={}".format(id(item), item._whoami,
                                                   len(item)))

        return '\n'.join(r)

    @property
    def current(self):
        """ Return most recent object if available. """
        if len(self.items) > 0:
            log("{}: using current".format(self._whoami))
            return self.items[-1]

    def __iter__(self):
        log("{}.__iter__ id={}".format(self._whoami, id(self)))
        for item in self.items:
            yield item


class OverrideBase(abc.ABC):

    def __init__(self, name, content, context, resolve_path, state=None):
        self._whoami = self.__class__.__name__
        self._context = context
        log("{}.__init__: id={} name={} content={} resolve_path={} state={}".
            format(self._whoami, id(self), name, content, resolve_path, state))
        self._override_resolved_name = name
        self._override_resolve_path = resolve_path
        log("creating new stack for override id={}".format(id(self)))
        self._stack = OverrideStack(self)
        self.add_state(name, content, state=state)

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
    def _override_path(self):
        path = "{}.{}".format(self._override_resolve_path, self._override_name)
        """ This is the full resolve path for this override object. """
        log("{}._override_path {}".format(self._whoami, path))
        return path

    @classmethod
    def valid_parse_content_types(cls):
        """ Override this if you want to restrict what content can be parsed
        e.g. of the content only contains dicts as properties and not lists of
        properties we can constrain that here.
        """
        return [dict, list]

    @property
    def context(self):
        # log("{}.context".format(self._whoami))
        return self._context

    @property
    def content(self):
        # log("{}.content ({})".format(self._whoami,
        #     len(self._stack)))
        if len(self._stack):
            return self._stack.current.content

    def add_state(self, _name, content, state=None):
        """
        We don't both saving name in state for unmapped overrides.
        """
        log("saving override state")
        if state is None:
            state = OverrideState(self, content)

        self._stack.push(state)

    def __len__(self):
        return len(self._stack)

    def __iter__(self):
        log("{}.__iter__ unmapped".format(self._whoami))
        for item in self._stack:
            yield self.__class__(self._override_name, None, self.context,
                                 self._override_path, state=item)

    @abc.abstractmethod
    def __getattr__(self, name):
        """ Each implementation must have their own means of lookups. """


class YStructOverrideBase(OverrideBase):

    def __getattr__(self, name):
        log("{}.__getattr__: unmapped name={}".format(self._whoami, name))
        if len(self._stack):
            # none is allowed as a return value
            return getattr(self._stack.current, name)

        raise AttributeError("'{}' object has no attribute '{}'".
                             format(self._whoami, name))


class YStructOverrideRawType(OverrideBase):

    @classmethod
    def _override_keys(cls):
        return ['__raw_type__']

    @classmethod
    def check_is_raw_value(cls, content):
        if type(content) in cls.valid_parse_content_types():
            return False

        return True

    def __type__(self):
        return type(self.content)

    def __int__(self):
        return int(self.content)

    def __str__(self):
        return self.content

    def __repr__(self):
        return self.content

    def __getattr__(self, name):
        """ These objects wont have any custom attributes. """
        raise AttributeError("'{}' object has no attribute '{}'".
                             format(self._whoami, name))


class MappedOverrideState(object):

    def __init__(self, owner, content, member_keys):
        self._whoami = "{}.{}".format(owner.__class__.__name__,
                                      self.__class__.__name__)
        self._owner = owner
        self._content = content
        self._stacks = {'member': {}, 'nested': {}}
        self._member_keys = member_keys
        log("{}.__init__: id={} content={}".format(self._whoami, id(self),
                                                   content))

    @property
    def _override_name(self):
        return self._owner._override_name

    @property
    def content(self):
        # log("{}.content".format(self._whoami))
        _content = {}
        for stype in self._stacks:
            for name, stack in self._stacks[stype].items():
                _content.update({name: stack})

        return _content

    def add_obj(self, obj):
        if isinstance(obj, self._owner.__class__):
            log("obj name='{}' is a nested mapping".format(obj._override_name))
            stack_type = 'nested'
        else:
            log("obj name='{}' is a mapping member".format(obj._override_name))
            stack_type = 'member'

        name = obj._override_name
        stack = self._stacks[stack_type]
        log("{}.add_obj: stack_type={} name={} id={}".format(self._whoami,
                                                             stack_type, name,
                                                             id(obj)))
        if name not in stack:
            log("no stack found for {} '{}' so creating new one".
                format(stack_type, name))
            stack[name] = OverrideStack(self)
        else:
            log("using existing stack for {} '{}'".format(stack_type, name))

        stack[name].push(obj)
        log("{} {} stack: \n{}\n".format(self._whoami, stack_type, repr(self)))

    def __len__(self):
        return sum([len(self._stacks[stype]) for stype in self._stacks])

    def __repr__(self):
        log("{}.repr".format(self._whoami))
        r = []
        for stype in self._stacks:
            for name, stack in self._stacks[stype].items():
                r.append("[{}] depth={} ".format(name, len(stack)))

        return '\n'.join(r)

    def __iter__(self):
        log("{}.__iter__".format(self._whoami))
        for stype in self._stacks:
            for obj in self._stacks[stype].values():
                for item in obj:
                    yield item

    def __getattr__(self, name):
        log("{}.__getattr__: mapped state {}".format(self._whoami, name))
        _name = name.replace('_', '-')
        for stype in self._stacks:
            obj = self._stacks[stype].get(_name)
            if obj is not None:
                break

        if obj:
            log("{} found (len={})".format(_name, len(obj)))
            if len(obj) > 1:
                return obj
            else:
                m = obj.current
                try:
                    # Allow overrides to define a property for non-simple
                    # content to be returned as-is.
                    return getattr(m, _name)
                except Exception:
                    log("{} not found in {}".format(_name,
                                                    m.__class__.__name__))
                    if type(m.content) not in [dict, list]:
                        log("returning raw content")
                        return m.content
                    else:
                        return m

        if _name in self._member_keys:
            # allow members to be empty
            return None

        raise AttributeError("'{}' object has no attribute '{}'".
                             format(self._whoami, name))


class YStructMappedOverrideBase(OverrideBase):

    def __init__(self, name, content, *args, **kwargs):
        log("creating new mapped override id={} type={} name={}".
            format(id(self), type(self), name))
        self._current_state_obj = None
        super().__init__(name, content, *args, **kwargs)

    @property
    def _override_name(self):
        """
        We override this to ensure that we return the principle objects name
        even if the name provided is a member name.
        """
        log("{}._override_name".format(self._whoami))
        name = self._override_resolved_name
        if name not in self._override_keys():
            log("'{}' not found in {} so using '{}' for override name".
                format(name, self._override_keys(), self._override_keys()[0]))
            name = self._override_keys()[0]

        return name

    @abc.abstractclassmethod
    def _override_mapped_member_types(cls):
        """ All mapped override implementations must implement this as a list
        of override types that can be found within or in lieu of the primary
        override_keys.
        """

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
    def resolved_member_names(self):
        names = []
        for m in self.members:
            names.append(m._override_name)

        return names

    @property
    def num_members(self):
        return sum([len(item) for item in self._stack])

    @property
    def members(self):
        """
        This combines iterating over the stack with iterating over the stack
        of each item on the stack. This mainly makes sense in scenarios where
        the depth of the local stack is 1.
        """
        log("{}.members (depth={})".format(self._whoami, len(self._stack)))
        for item in self._stack:
            log("{}.__iter__ item={}\n{}".
                format(self._whoami, item._whoami, repr(item)))
            for _item in item:
                yield _item

    def __iter__(self):
        log("{}.__iter__ mappings \n{}".format(self._whoami,
                                               repr(self._stack)))
        for item in self._stack:
            log("{}.__iter__ members item={} ({})".
                format(self._whoami, item._whoami, repr(item)))
            yield item

    def add_state(self, name, content, flush_current=False, state=None):
        """
        @param flush_current: Flush the current state and start a new one.
        """
        log("{}.add_state: name={} content={} current={} flush_current={}".
            format(self._whoami, name, content, self._current_state_obj,
                   flush_current))
        log("saving mapped override state")
        if not self._current_state_obj or flush_current:
            if state is None:
                state = MappedOverrideState(self, content, self.member_keys)

            self._current_state_obj = None
        else:
            state = self._current_state_obj

        if name in self._override_keys():
            log("name is principle ({})".format(name))
            self._current_state_obj = None
            if state is None:
                state = MappedOverrideState(self, content, self.member_keys)

            if type(content) in self.valid_parse_content_types():
                log("resolving contents of mapped override '{}'".
                    format(self._override_name))
                mapping_members = self._override_mapped_member_types()
                mapping_members.append(self.__class__)
                s = YStructSection(name, content,
                                   resolve_path=self._override_path,
                                   override_handlers=mapping_members,
                                   context=self._context)

                # Now see what members got resolved (if any)
                for name in self.member_keys:
                    log("checking for mapping '{}' member '{}'".
                        format(self._override_name, name))
                    try:
                        obj = getattr(s, name)
                        if obj is not None:
                            log("member '{}' found, adding to principle".
                                format(name))
                            state.add_obj(obj)
                        else:
                            log("member '{}' not found".format(name))
                    except AttributeError:
                        log("member '{}' not found and raised AttributeError "
                            "which was unexpected".format(name))

                # Now see what mappings got resolved (if any)
                for key in self._override_keys():
                    log("checking for nested {}".format(key))
                    obj = getattr(s, key)
                    if obj is not None:
                        log("nested mapping '{}' found, adding to principle".
                            format(key))
                        state.add_obj(obj)

                for obj in s.get_resolved_by_type(YStructOverrideRawType):
                    state.add_obj(obj)
            else:
                log("content type '{}' not parsable ({}) so "
                    "treating as {}".format(type(content),
                                            self.valid_parse_content_types(),
                                            YStructOverrideRawType.__name__)),

                if type(content) != list:
                    content = [content]

                for item in content:
                    obj = YStructOverrideRawType(item, item, self.context,
                                                 self._override_path)
                    state.add_obj(obj)

            log("pushing updated mapping state to stack")
            self._stack.push(state)
        else:
            log("name is member ({})".format(name))
            handler = self.get_member_with_key(name)
            obj = handler(name, content, self.context, self._override_path)
            state.add_obj(obj)
            if not self._current_state_obj:
                self._current_state_obj = state
                log("pushing mapping state to stack")
                self._stack.push(state)

    def __getattr__(self, name):
        """
        This should only be used if stack length == 1. Otherwise need to
        iterate over the stack.
        """
        log("{}.__getattr__: mapped name={}".format(self._whoami, name))
        _name = name.replace('_', '-')
        if len(self._stack):
            for stype in self._stack.current._stacks:
                obj = self._stack.current._stacks[stype].get(_name)
                if obj:
                    return obj.current

        if _name in self.member_keys:
            # allow members to be empty
            return None

        raise AttributeError("'{}' object has no attribute '{}'".
                             format(self._whoami, name))


class YStructOverrideManager(object):

    def __init__(self, handlers=None, manager=None, context=None):
        self.allow_stacking = False
        self._resolved = {}
        self._resolved_mapped = {}
        if not handlers:
            handlers = [YStructOverrideRawType]

        if manager:
            # clone it
            self._context = manager._context
            self._handlers = manager._handlers
            self._mappings = manager._mappings
            self._resolved.update(manager._resolved)
        else:
            self._context = context
            self._handlers = []
            self._mappings = []
            for h in handlers:
                if issubclass(h, YStructMappedOverrideBase):
                    self._mappings.append(h)
                else:
                    self._handlers.append(h)

    def switch_to_stacked(self):
        """
        With stacking enabled we say that if an override has already been
        resolved, we can treat further resolves of the same override as extra
        state of the current one rather than treating them as separate
        instances.

        This also clears the set of resolved overrides so that we start afresh.
        """
        log("enabling stacking (clearing resolved={})".format(self._resolved))
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
        log("{}.get_resolved: name={} (total_resolved={})".
            format(self.__class__.__name__, name, len(self._resolved)))
        name = name.replace('_', '-')
        return self._resolved.get(name)

    def add_resolved(self, name, content, handler, resolve_path,
                     member_name=None, flush_mapped=False):
        """
        @param flush_mapped: if True this tells a mapped override to flush it's
        member states and start a new set.
        """
        log("{}.add_resolved: name={} member_name={} content={} handler={} "
            "resolve_path={} flush_mapped={} allow_stacking={}".
            format(self.__class__.__name__, name, member_name, content,
                   handler.__name__, resolve_path, flush_mapped,
                   self.allow_stacking))
        resolved_obj = self._resolved.get(name)
        if resolved_obj:
            log("found existing resolved obj for name={} type={}".
                format(name, resolved_obj.__class__.__name__))

        resolved_name = name
        add_member = False
        if member_name:
            name = member_name
            if resolved_obj:
                add_member = True

        if resolved_obj and (self.allow_stacking or add_member):
            if isinstance(resolved_obj, YStructMappedOverrideBase):
                log("{} is an instance of {}".
                    format(resolved_obj.__class__.__name__,
                           YStructMappedOverrideBase.__name__))
                resolved_obj.add_state(name, content,
                                       flush_current=flush_mapped)
            else:
                log("obj id={}, type={} is not an instance of {} and is "
                    "therefore assumed to "
                    "be a member or unmapped override".
                    format(id(resolved_obj), resolved_obj.__class__.__name__,
                           YStructMappedOverrideBase.__name__))
                resolved_obj.add_state(name, content)
        else:
            obj = handler(name, content, self._context, resolve_path)
            self._resolved[resolved_name] = obj

    def resolve(self, name, content, resolve_path, flush_mapped=False):
        log("{}.resolve: name={} content={} resolve_path={} flush_mapped={}".
            format(self.__class__.__name__, name, content, resolve_path,
                   flush_mapped))
        if name == content:
            log("resolved principle override with raw content")
            self.add_resolved(name, content, YStructOverrideRawType,
                              resolve_path)
            return

        handler = self.get_handler(name)
        if handler:
            log("resolving using unmapped override type={}".format(handler))
            self.add_resolved(name, content, handler, resolve_path)
            return

        mapping, member = self.get_mapping(name)
        if mapping:
            if not member:
                log("resolved mapped override mapping={} (member=None)".
                    format(mapping.__name__))
                self.add_resolved(name, content, mapping, resolve_path)
                return

            log("resolved mapped override mapping={} (member={})".
                format(mapping.__name__, member.__name__))
            member_name = name
            name = mapping._override_keys()[0]
            log("using mapping name '{}' (member={})".format(name,
                                                             member_name))
            self.add_resolved(name, content, mapping, resolve_path,
                              member_name=member_name,
                              flush_mapped=flush_mapped)
            self._resolved_mapped[member_name] = name
            return

        log("nothing to resolve")

    @property
    def resolved_unmapped(self):
        return self._resolved

    @property
    def resolved(self):
        _r = {}
        _r.update(self._resolved)
        _r.update(self._resolved_mapped)
        return _r


class YStructSection(object):
    def __init__(self, name, content, parent=None, root=None,
                 override_handlers=None, override_manager=None,
                 run_hooks=False, resolve_path=None, context=None):
        self.run_hooks = run_hooks
        if root is None:
            self.root = self
        else:
            self.root = root

        log("{}.__init__: name={} content={}".format(self.__class__.__name__,
                                                     name, content))
        self.name = name
        self.parent = parent
        self.content = content
        self.sections = []
        if resolve_path:
            self.resolve_path = resolve_path
        else:
            self.resolve_path = name

        if override_manager:
            self.manager = YStructOverrideManager(manager=override_manager)
        else:
            self.manager = YStructOverrideManager(handlers=override_handlers,
                                                  context=context)

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
        if self.root == self and self.run_hooks:
            log("{}.run: running pre_hook".format(self.__class__.__name__))
            self.pre_hook()

        if type(self.content) == list:
            log("content is list")
            self.manager.switch_to_stacked()
            for _ref, item in enumerate(self.content):
                log("{}.run: item={}".format(self.__class__.__name__, item))
                if YStructOverrideRawType.check_is_raw_value(item):
                    self.manager.resolve(item, item, self.resolve_path)
                else:
                    flush_mapped = True
                    for name, content in item.items():
                        self.manager.resolve(name, content, self.resolve_path,
                                             flush_mapped)
                        flush_mapped = False
        else:
            self.manager.allow_stacking = False
            if type(self.content) != dict:
                raise YStructException("undefined override '{}'".
                                       format(self.name))

            log("content is dict")
            # first get all overrides at this level
            unresolved = {}
            for name, content in self.content.items():
                self.manager.resolve(name, content, self.resolve_path)
                if name not in self.manager.resolved:
                    unresolved[name] = content

            for name, content in unresolved.items():
                if YStructOverrideRawType.check_is_raw_value(content):
                    log("{}.run: terminating override={} with raw content "
                        "'{}'".
                        format(self.__class__.__name__, name, content))
                    continue

                rpath = "{}.{}".format(self.resolve_path, name)
                s = YStructSection(name, content, parent=self, root=self.root,
                                   override_manager=self.manager,
                                   resolve_path=rpath)
                self.sections.append(s)

        if self.root == self and self.run_hooks:
            log("{}.run: running post_hook".format(self.__class__.__name__))
            self.post_hook()

        log("{}.run: {} END\n".format(self.__class__.__name__, self.name))

    def pre_hook(self):
        """
        This can be implemented and will be run before parsing begins.
        """

    def post_hook(self):
        """
        This can be implemented and will be run after parsing has completed.
        """
