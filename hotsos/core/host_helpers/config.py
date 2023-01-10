import abc
import os
import re

from hotsos.core.log import log


class ConfigBase(abc.ABC):

    def __init__(self, path):
        self.path = path

    @classmethod
    def squash_int_range(cls, ilist):
        """Takes a list of integers and squashes consecutive values into a
        string range. Returned list contains mix of strings and ints.
        """
        irange = []
        rstart = None
        rprev = None

        sorted(ilist)
        for i, value in enumerate(ilist):
            if rstart is None:
                if i == (len(ilist) - 1):
                    irange.append(value)
                    break

                rstart = value

            if rprev is not None:
                if rprev != (value - 1):
                    if rstart == rprev:
                        irange.append(rstart)
                    else:
                        irange.append("{}-{}".format(rstart, rprev))
                        if i == (len(ilist) - 1):
                            irange.append(value)

                    rstart = value
                elif i == (len(ilist) - 1):
                    irange.append("{}-{}".format(rstart, value))
                    break

            rprev = value

        return ','.join(irange)

    @classmethod
    def expand_value_ranges(cls, ranges):
        """
        Takes a string containing ranges of values such as 1-3 and 4,5,6,7 and
        expands them into a single list.
        """
        if not ranges:
            return ranges

        expanded = []
        ranges = ranges.split(',')
        for subrange in ranges:
            # expand ranges
            subrange = subrange.partition('-')
            if subrange[1] == '-':
                expanded += range(int(subrange[0]), int(subrange[2]) + 1)
            else:
                for val in subrange[0].split():
                    expanded.append(int(val))

        return sorted(expanded)

    @property
    def exists(self):
        if os.path.exists(self.path):
            return True

        return False

    @abc.abstractmethod
    def get(self, key, section=None, expand_to_list=False):
        """ Get a config value. """


class SectionalConfigBase(ConfigBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._sections = {}
        # this provides an easy sectionless lookup but is prone to collisions.
        # always returns the last value for key found in config file.
        self._flattened_config = {}
        self._load()

    @staticmethod
    def bool_str(val):
        if val.lower() == "true":
            return True
        elif val.lower() == "false":
            return False

        return val

    @property
    def all(self):
        return self._sections

    def get(self, key, section=None, expand_to_list=False):
        """ If section is None use flattened """
        if section is None:
            value = self._flattened_config.get(key)
        else:
            if section not in self._sections:
                log.debug("section '%s' not found in config file, "
                          "trying lower case", section)
                section = section.lower()

            value = self._sections.get(section, {}).get(key)

        if expand_to_list:
            return self.expand_value_ranges(value)

        return value

    @property
    def dump(self):
        with open(self.path) as fd:
            return fd.read()

    def _load(self):
        if not self.exists:
            return

        current_section = None
        with open(self.path) as fd:
            for line in fd:
                if re.compile(r"^\s*#").search(line):
                    continue

                # section names are not expected to contain whitespace
                ret = re.compile(r"^\s*\[(\S+)].*").search(line)
                if ret:
                    current_section = ret.group(1)
                    self._sections[current_section] = {}
                    continue

                if current_section is None:
                    continue

                # key names may contain whitespace
                # values may contain whitespace
                expr = r"^\s*(\S+(?:\s+\S+)?)\s*=\s*(.+)\s*"
                ret = re.compile(expr).search(line)
                if ret:
                    key = ret.group(1)
                    val = self.bool_str(ret.group(2))
                    if type(val) == str:
                        val = val.strip()
                        for char in ["'", '"']:
                            val = val.strip(char)

                    self._sections[current_section][key] = val
                    self._flattened_config[key] = val
