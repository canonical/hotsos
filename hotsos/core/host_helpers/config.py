import abc
import os
import configparser

from hotsos.core.log import log


class ConfigBase(abc.ABC):

    def __init__(self, path):
        self.path = path

    @classmethod
    def squash_int_range(cls, ilist):
        """Takes a list of integers and squashes consecutive values into a
        string range.
        """
        irange = []
        rstart = None
        rprev = None

        sorted(ilist)
        for i, value in enumerate(ilist):
            if rstart is None:
                if i == (len(ilist) - 1):
                    irange.append(str(value))
                    break

                rstart = value

            if rprev is not None:
                if rprev != (value - 1):
                    if rstart == rprev:
                        irange.append(str(rstart))
                    else:
                        irange.append(f"{rstart}-{rprev}")
                        if i == (len(ilist) - 1):
                            irange.append(str(value))

                    rstart = value
                elif i == (len(ilist) - 1):
                    irange.append(f"{rstart}-{value}".format(rstart, value))
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


class IniConfigBase(ConfigBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.config = None
        self._load()

    def __bool__(self):
        return self.config is not None

    @staticmethod
    def bool_str(val):
        if val.lower() == "true":
            return True
        if val.lower() == "false":
            return False

        return val

    @classmethod
    def post_processing(cls, v, expand_to_list=False):
        # Sanitize the string and perform
        # boolean type conversion if needed
        if isinstance(v, str):
            v = v.strip()
            for char in ["'", '"']:
                v = v.strip(char)
            v = cls.bool_str(v)

        if expand_to_list:
            return cls.expand_value_ranges(v)

        return v

    @property
    def all_sections(self):
        return self.config.sections() + ["DEFAULT"]

    @property
    def all_keys(self):
        return [x for option in self.config.items()
                for x in list(option[1].keys())]

    def get(self, key, section=None, expand_to_list=False):
        """ If section is None, then search all sections and return first
        match. """
        log.debug("ini read call -> %s:%s", section, key)

        if not self.config:
            return None

        # 1: Section is specified.
        if section is not None:
            # Look for section name, case-insensitive
            for sect in self.all_sections:
                if section.upper() == sect.upper():
                    return self.post_processing(
                        self.config.get(sect, key, fallback=None),
                        expand_to_list
                    )
            return None

        # 2: No section specified.
        # The default section is not included in the section
        # set so append it
        for sec in self.all_sections:
            v = self.config.get(sec, key, fallback=None)
            log.debug("ini read value -> %s:%s = %s", section, key, v)
            if v:
                return self.post_processing(v, expand_to_list)

        return None

    def _load(self):
        if not self.exists:
            log.debug("config file %s does not exist", self.path)
            self.config = None
            return

        self.config = configparser.ConfigParser(strict=False)
        if self.path not in self.config.read(self.path):
            log.error("cannot parse config file `%s`", self.path)
            self.config = None
            return


class GenericIniConfig(IniConfigBase):
    pass
