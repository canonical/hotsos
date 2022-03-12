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

class YStructException(Exception):
    pass


class YAMLDefOverrideBase(object):
    KEYS = None

    def __init__(self, name, content, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._override_name = name
        self._content = content

    @property
    def content(self):
        return self._content

    def __getattr__(self, name):
        name = name.replace('_', '-')
        try:
            return self.content[name]
        except KeyError as e:
            raise AttributeError from e


class YAMLDefBase(object):
    # We want these to be global/common to all sections
    _override_handlers = []

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
    def override_keys(self):
        keys = []
        for o in self._override_handlers:
            keys += o.KEYS

        return keys

    def get_override_handler(self, name):
        for o in self._override_handlers:
            if name in o.KEYS:
                return o

    def set_override_handlers(self, override_handlers):
        self._override_handlers += override_handlers


class YAMLDefSection(YAMLDefBase):
    def __init__(self, name, content, overrides=None, parent=None,
                 override_handlers=None, root=None):
        if root is None:
            self.root = self
        else:
            self.root = root

        self.name = name
        self.parent = parent
        self.content = content
        self.sections = []
        self.overrides = {}
        if overrides:
            self.overrides.update(overrides)

        if override_handlers:
            self.set_override_handlers(override_handlers)

        self.run()

    def run(self):
        if type(self.content) != dict:
            raise YStructException("undefined override '{}'".format(self.name))

        # first get all overrides at this level
        for name, content in self.content.items():
            if name in self.override_keys:
                handler = self.get_override_handler(name)
                self.overrides[name] = handler(name, content)

        for name, content in self.content.items():
            if name in self.override_keys:
                continue

            s = YAMLDefSection(name, content, self.overrides, parent=self,
                               root=self.root)
            self.sections.append(s)

    @property
    def is_leaf(self):
        return self.content and len(self.sections) == 0

    def __getattr__(self, name):
        name = name.replace('_', '-')
        return self.overrides.get(name)
