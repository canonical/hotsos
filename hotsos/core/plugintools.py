import os
from enum import IntEnum, auto
from dataclasses import dataclass

import yaml
from jinja2 import FileSystemLoader, Environment
from hotsos.core.config import HotSOSConfig
from hotsos.core.issues import IssuesManager
from hotsos.core.log import log
from hotsos.core.ycheck.engine.common import YHandlerBase
from hotsos.core.ycheck.scenarios import YScenarioChecker
from hotsos.core.ycheck.common import GlobalSearcher
from hotsos.core.ycheck.events import EventsSearchPreloader
from hotsos.core.ycheck.scenarios import ScenariosSearchPreloader
from hotsos.core.exceptions import NameNotSetError

PLUGINS = {}
PLUGIN_RUN_ORDER = []


class SummaryOffsetConflict(Exception):
    """ If more than one entry competes for the same offset in the summary
    it could give unexpected results so we raise this exception.
    """


class PluginRegistryMeta(type):
    """
    Each plugin that wants to add output to the finally summary must register
    itself by implementing one or more classes that have this class as the
    metaclass at some point in their resolution chain and:

        * class attribute 'plugin_root_index' which should be set once per
          plugin (usually in a high level base class) and defines the order in
          which plugins will be run.

        * class attribute 'summary_part_index' set to the integer index it
          should appear in the summary entry for that plugin. These indexes
          start at 0 and are unique to a plugin.
    """

    def __init__(cls, _name, _mro, members):
        name = members.get('plugin_name')
        if name:
            PLUGINS[name] = []
            PLUGIN_RUN_ORDER.append((name, members['plugin_root_index']))

        for subcls in cls.__mro__:
            index_key = 'summary_part_index'
            if hasattr(subcls, index_key):
                index = subcls.summary_part_index
                existing = [e[index_key] for e in PLUGINS[cls.plugin_name]]
                if index in existing:
                    raise SummaryOffsetConflict(f"plugin {name} has index "
                                                f"conflict {index}")

                PLUGINS[cls.plugin_name].append({index_key: index,
                                                 'runner': subcls})


class HOTSOSDumper(yaml.Dumper):
    """ Custom yaml dumper that preserves order. """
    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)

    def represent_dict_preserve_order(self, data):
        return self.represent_dict(data.items())


def get_plugins_sorted():
    """ Return list of plugin names in the order they are to be run. """
    return [e[0] for e in sorted(PLUGIN_RUN_ORDER, key=lambda e: e[1])]


def yaml_dump(data):
    """
    This is our version of yaml.dump but ensuring the format/style that we
    want.
    """
    HOTSOSDumper.add_representer(
        dict,
        HOTSOSDumper.represent_dict_preserve_order)
    return yaml.dump(data, Dumper=HOTSOSDumper,
                     default_flow_style=False).rstrip("\n")


class HTMLFormatter:
    """
    Format the summary as html.

    Ref: https://iamkate.com/code/tree-views/
    """

    def __init__(self, hostname, max_level=2):
        """
        @param max_level: The HTML will be collapsible up to max_level
        """
        self.hostname = hostname
        self.max_level = max_level

    @staticmethod
    def render(context, template):
        # jinja 2.10.x really needs this to be a str and e.g. not a PosixPath
        templates_dir = str(HotSOSConfig.templates_path)
        if not os.path.isdir(templates_dir):
            raise FileNotFoundError(
                f"jinja templates directory not found: '{templates_dir}'")

        env = Environment(loader=FileSystemLoader(templates_dir))
        template = env.get_template(template)
        return template.render(context)

    @property
    def header(self):
        return self.render({'hostname': self.hostname}, 'header.html')

    @property
    def footer(self):
        with open(os.path.join(HotSOSConfig.templates_path,
                               'footer.html'), encoding='utf-8') as fd:
            return fd.read()

    def _expand_list(self, data, level):
        context = {'list_elements': [], 'indent': '    '}
        for item in data:
            context['list_elements'].append(self._expand(item, level))

        return self.render(context, 'content_list.html')

    def _expand_dict(self, data, level):
        context = {'dict_elements': {},
                   'indent': '    ',
                   'collapsible': level < self.max_level}
        if level == 1:
            context['class'] = 'class="tree"'

        for key, value in data.items():
            context['dict_elements'][key] = self._expand(value, level + 1)

        return self.render(context, 'content_dict.html')

    def _expand(self, data, level):
        """Expand the data object.

        @param data: The data object. This can be a dict, list, or a flat type
                     such as int or str.
        @param level: The current header level
        @return: A string expansion formatted in HTML of the data object.
        """
        if isinstance(data, dict):
            return self._expand_dict(data, level)
        if isinstance(data, list):
            return self._expand_list(data, level)

        return data

    def dump(self, data):
        """Convert the data (dict) into an html document.

        @param dist: The data
        @return: the html document as a string.
        """
        content = self._expand(data, 1)
        return self.header + content + self.footer


class MarkdownFormatter:
    """
    Formatter to convert output to Markdown.
    """

    def _expand_dict(self, data, level):
        level_prefix = ''.join(['#' for i in range(level)])
        markdown_output = ''
        for key in data:
            markdown_output += f'\n{level_prefix} {key}\n'
            markdown_output += self._expand(data[key], level + 1)

        return markdown_output

    @staticmethod
    def _expand_list(data):
        markdown_output = '\n%s' % ''.join(f'- {item}\n' for item in data)

        return markdown_output

    def _expand(self, data, level):
        """Expand the data object.

        @param data: The data object. This can be a dict, list, or a flat type
                     such as int or str.
        @param level: The current header level
        @return: string expansion formatted in markdown of the data object.
        """
        if isinstance(data, dict):
            return self._expand_dict(data, level)
        if isinstance(data, list):
            return self._expand_list(data)

        return f'\n{data}\n'

    def dump(self, data):
        """Convert the data (dict) into a markdown document.

        @param data: dict:- The data
        @return: str: The markdown document
        """
        markdown = '# hotsos summary\n' + self._expand(data, 2)
        return markdown.rstrip('\n')


class ApplicationBase(metaclass=PluginRegistryMeta):
    """
    Base class for all plugins representing an application.
    """
    def __init__(self, *args, **kwargs):
        self.apt = None  # APTPackageHelper
        self.snaps = None  # SnapPackageHelper
        self.docker = None  # DockerImageHelper
        self.pebble = None  # PebbleHelper
        self.systemd = None  # SystemdHelper
        super().__init__(*args, **kwargs)

    @property
    def version(self):
        """ Optional application version. """
        return None

    @property
    def release_name(self):
        """ Optional application release_name. """
        return None

    @property
    def days_to_eol(self):
        """ Optional application days_to_eol. """
        return None

    @property
    def bind_interfaces(self):
        """
        Optionally implement this method to return a dictionary of network
        interfaces used by this application.
        """


@dataclass
class SummaryEntry:
    """ SummaryEntry data type. """

    data: object
    index: int = 0


def summary_entry(name, index=0):
    """Decorate a class member function to indicate that it is a summary
    function. Summary functions are automatically discovered by the
    PluginPartBase class and will be part of the summary output."""

    def real_decorator(func):
        # Store the summary metadata information on the function itself.
        func.__summary_elem_name = name  # pylint: disable=protected-access
        func.__summary_elem_index = index  # pylint: disable=protected-access
        return func
    return real_decorator


def get_min_available_entry_index():
    """ Return first index available after default entries. """
    return DefaultSummaryEntryIndexes.AVAILABLE


class DefaultSummaryEntryIndexes(IntEnum):
    """ Indexes used for default summary entries. """
    VERSION = 0
    RELEASE = auto()
    SERVICES = auto()
    SNAPS = auto()
    DPKG = auto()
    DOCKER_IMAGES = auto()
    # The following index represents the first one that is available for
    # implementations to use and they implement their indexes as an offset from
    # this value so that if it is increased they are automatically increased.
    AVAILABLE = auto()


class SummaryBase(ApplicationBase):
    """ Common structure for application summary output.

    Individual application plugins should implement this class and extend to
    include information specific to their application.
    """
    @classmethod
    def default_summary_entries(cls):
        return [e for e in dir(SummaryBase) if str(e).startswith('summary_')]

    @summary_entry('version', DefaultSummaryEntryIndexes.VERSION)
    def summary_version(self):
        return self.version

    @summary_entry('release', DefaultSummaryEntryIndexes.RELEASE)
    def summary_release(self):
        if not all([self.release_name is not None,
                    self.days_to_eol is not None]):
            return None

        return {'name': self.release_name,
                'days-to-eol': self.days_to_eol}

    @summary_entry('services', DefaultSummaryEntryIndexes.SERVICES)
    def summary_services(self):
        """Get string info for running services."""
        if self.systemd is not None and self.systemd.services:
            return self.systemd.summary

        if self.pebble is not None and self.pebble.services:
            return self.pebble.summary

        return None

    @summary_entry('snaps', DefaultSummaryEntryIndexes.SNAPS)
    def summary_snaps(self):
        if self.snaps is None:
            return None

        return self.snaps.all_formatted or None

    @summary_entry('dpkg', DefaultSummaryEntryIndexes.DPKG)
    def summary_dpkg(self):
        # require at least one core package to be installed to include
        # this in the report.
        if self.apt is not None and self.apt.core:
            return self.apt.all_formatted

        return None

    @summary_entry('docker-images', DefaultSummaryEntryIndexes.DOCKER_IMAGES)
    def summary_docker_images(self):
        if self.docker is None:
            return None

        # require at least one core image to be in-use to include
        # this in the report.
        if self.docker.core:
            return self.docker.all_formatted

        return None


class PartManager():
    """
    Collects output of all parts from a plugin and saves them in YAML format.
    """

    def save(self, data, index):
        """
        Save part output yaml in temporary location. These are collected and
        aggregated at the end of the plugin run.
        """
        HOTSOSDumper.add_representer(
            dict,
            HOTSOSDumper.represent_dict_preserve_order)
        out = yaml.dump(data, Dumper=HOTSOSDumper,
                        default_flow_style=False).rstrip("\n")

        part_path = os.path.join(HotSOSConfig.plugin_tmp_dir,
                                 (f"{HotSOSConfig.plugin_name}."
                                  f"{HotSOSConfig.part_name}.part.yaml"))

        # don't clobber
        if os.path.exists(part_path):
            newpath = part_path
            i = 0
            while os.path.exists(newpath):
                i += 1
                newpath = f"{part_path}.{i}"

            part_path = newpath

        with open(part_path, 'w', encoding='utf-8') as fd:
            fd.write(out)

        self.add_to_index(index, part_path)

    @property
    def indexes(self):
        path = os.path.join(HotSOSConfig.plugin_tmp_dir, "index.yaml")
        if os.path.exists(path):
            with open(path, encoding='utf-8') as fd:
                return yaml.safe_load(fd.read()) or {}

        return {}

    def add_to_index(self, index, part):
        indexes = self.indexes
        path = os.path.join(HotSOSConfig.plugin_tmp_dir, "index.yaml")
        with open(path, 'w', encoding='utf-8') as fd:
            if index in indexes:
                indexes[index].append(part)
            else:
                indexes[index] = [part]

            fd.write(yaml.dump(indexes))

    @staticmethod
    def meld_part_output(data, existing):
        """
        Don't allow root level keys to be clobbered, instead just
        update them. This assumes that part subkeys will be unique.
        """
        remove_keys = []
        for key in data:
            if key in existing:
                if isinstance(existing[key], dict):
                    existing[key].update(data[key])
                    remove_keys.append(key)

        if remove_keys:
            for key in remove_keys:
                del data[key]

        existing.update(data)

    def all(self):
        if not self.indexes:
            return {}

        parts = {}
        for index in sorted(self.indexes):
            for part in self.indexes[index]:
                with open(part, encoding='utf-8') as fd:
                    part_yaml = yaml.safe_load(fd)

                    # Don't allow root level keys to be clobbered, instead just
                    # update them. This assumes that part subkeys will be
                    # unique.
                    self.meld_part_output(part_yaml, parts)

        return {HotSOSConfig.plugin_name: parts}


class PluginPartBase(SummaryBase):
    """ This is the base class used for all plugins.

    Provides a standard set of methods that plugins will need as well as the
    plumbing needed to add their output to the summary.
    """
    # max per part before overlap
    PLUGIN_PART_INDEX_MAX = 500
    # Must be set to the name of the plugin context in which we are
    # running and at runtime should match HotSOSConfig.plugin_name.
    plugin_name = None

    def __init__(self, *args, global_searcher=None, **kwargs):
        """
        @param global_searcher: optional ...
        """
        self.global_searcher = global_searcher
        plugin_tmp = HotSOSConfig.plugin_tmp_dir

        if self.plugin_name is None:
            raise NameNotSetError(
                f"{self.__class__.__name__}.plugin_name must be "
                "set to a value that represents the name of the plugin")

        if not plugin_tmp or not os.path.isdir(plugin_tmp):
            raise FileNotFoundError(
                "plugin plugin_tmp_dir not initialised - exiting")

        super().__init__(*args, **kwargs)

    @property
    def plugin_runnable(self):
        """
        Must be implemented by all plugins to define at runtime whether they
        should run.
        """
        raise NotImplementedError

    @property
    def summary_subkey_include_default_entries(self):
        """
        By default the default/base class summary entries will NOT be included
        in the output of a summary subkey. To override this behaviour you must
        override this property to return True.
        """
        return False

    @property
    def summary_subkey(self):
        """
        This can be optionally implemented in order to have all output of the
        current part placed under the keyname provided by this property i.e.
        <plugin_name>: <subkey>: ...

        By default the default/base class summary entries will NOT be included
        in the output of a summary subkey. To override this behaviour you must
        override summary_subkey_include_default_entries to return True.
        """
        return None

    @property
    def summary(self):
        """
        This can be optionally implemented as a way of pushing all results into
        the summary root for the current plugin part.

        The alternative is to implement methods called __summary_<key> such
        that the returned value is placed under <key>.
        """
        return None

    def get_summary_entries(self):
        """Return a list of summary functions defined in the current class
        and all the derived classes.

        Summary functions are the functions decorated with @summary_entry
        decorator.
        """

        result = {}
        # Iterate through all attributes of BaseClass
        for name in dir(self.__class__):
            # Get the attribute from the current class (self.__class__)
            attr = getattr(self.__class__, name)
            # Check if it's a function and has the specified attribute
            if not (callable(attr) and hasattr(attr, '__summary_elem_name')):
                continue

            if not self.summary_subkey_include_default_entries:
                # Exclude base class (default) entries from subkey parts
                if (self.summary_subkey is not None and
                        attr.__name__ in self.default_summary_entries()):
                    continue

            name = getattr(attr, '__summary_elem_name')
            index = getattr(attr, '__summary_elem_index')
            log.debug("Found summary entry %s with idx %d",
                      name, index)
            result[name] = [attr.__name__, index]
        return result

    @property
    def output(self):
        _output = {}
        if self.summary:
            for key, data in self.summary.items():
                _output[key] = SummaryEntry(data=data)

        # Discover the summary functions
        implicit_summary_fns = self.get_summary_entries()

        if implicit_summary_fns:
            # Sort the functions by their index
            implicit_summary_fns = dict(
                sorted(implicit_summary_fns.items(),
                       key=lambda item: item[1][1])
            )
            for name, (attr_name, index) in implicit_summary_fns.items():
                attr = getattr(self, attr_name)
                result = attr()
                if not result:
                    continue
                _output[name] = SummaryEntry(data=result, index=index)

        return _output

    @property
    def raw_output(self):
        out = self.output
        if not out:
            return {}

        return {key: entry.data for key, entry in out.items()}


class PluginRunner():
    """
    Run a plugin. This will run all requests parts of a plugin including
    defaults, providing a global searcher for the runtime of the plugin.
    """
    def __init__(self, plugin):
        self.parts = PLUGINS[plugin]
        self.failed_parts = []

    def _load_global_searcher(self, global_searcher):
        """ Load event and scenario searches into global searcher. """
        # Load searches into the GlobalSearcher
        for preloader in [EventsSearchPreloader, ScenariosSearchPreloader]:
            try:
                preloader(global_searcher).run()
            # We really do want to catch all here since we don't care why
            # it failed but don't want to fail hard if it does.
            except Exception as exc:  # pylint: disable=W0718
                name = preloader.__name__
                self.failed_parts.append(name)
                log.exception("search preloader '%s' raised exception: %s",
                              name, exc)

    def _run_always_parts(self, global_searcher):
        """
        Execute parts that run regardless of plugin context.

        The following are executed as part of each plugin run (but not last).

        @param global_searcher: GlobalSearcher object
        """
        always_run = {'auto_scenario_check': YScenarioChecker}
        for name, always_parts in always_run.items():
            # update current env to reflect actual part being run
            HotSOSConfig.part_name = name
            try:
                always_parts(global_searcher).run()
            # We really do want to catch all here since we don't care why
            # it failed but don't want to fail hard if it does.
            except Exception as exc:  # pylint: disable=W0718
                self.failed_parts.append(name)
                log.exception("part '%s' raised exception: %s", name, exc)

            # NOTE: we don't expect these parts to produce any output
            # for the summary so we wont check for it (they only raise
            # issues and bugs which are handled independently).

    def _run_plugin_parts(self, global_searcher):
        """ Execute parts for the current plugin context.

        @param global_searcher: GlobalSearcher object
        @return: dictionary summary of output.
        """
        part_mgr = PartManager()
        for part_info in self.parts:
            # update current env to reflect actual part being run
            runner = part_info['runner']
            name = runner.__name__
            HotSOSConfig.part_name = name
            if issubclass(runner, YHandlerBase):
                inst = runner(global_searcher)
            else:
                inst = runner(global_searcher=global_searcher)

            # Only run plugin if it declares itself runnable.
            if not HotSOSConfig.force_mode and not inst.plugin_runnable:
                log.debug("%s.%s.%s not runnable - skipping",
                          HotSOSConfig.plugin_name, name, runner.__name__)
                continue

            log.debug("running %s.%s.%s",
                      HotSOSConfig.plugin_name, name, runner.__name__)
            try:
                # NOTE: since all parts are expected to be implementations
                # of PluginPartBase we expect them to always define an
                # output property.
                output = inst.output
                subkey = inst.summary_subkey
            # We really do want to catch all here since we don't care why
            # it failed but don't want to fail hard if it does.
            except Exception as exc:  # pylint: disable=W0718
                self.failed_parts.append(name)
                log.exception("part '%s' raised exception: %s", name, exc)
                output = None

            if output:
                for key, entry in output.items():
                    out = {key: entry.data}
                    if subkey:
                        out = {subkey: out}

                    part_max = PluginPartBase.PLUGIN_PART_INDEX_MAX
                    part_index = part_info['summary_part_index']
                    index = (part_index * part_max) + entry.index
                    part_mgr.save(out, index=index)

        if self.failed_parts:
            # always put these at the top
            part_mgr.save({'failed-parts': self.failed_parts}, index=0)

        imgr = IssuesManager()
        bugs = imgr.load_bugs()
        raised_issues = imgr.load_issues()
        summary_end_index = PluginPartBase.PLUGIN_PART_INDEX_MAX ** 2

        # Add detected known_bugs and raised issues to end summary.
        if bugs:
            part_mgr.save(bugs, index=summary_end_index)

        # Add raised issues to summary.
        if raised_issues:
            part_mgr.save(raised_issues, index=summary_end_index)

        return part_mgr.all()

    def run(self):
        """ Execute all plugin parts. """
        self.failed_parts = []
        with GlobalSearcher() as global_searcher:
            self._load_global_searcher(global_searcher)

            # Run the searches so that results are ready to be consumed when
            # the parts and handlers are run.
            global_searcher.run()

            self._run_always_parts(global_searcher)

            return self._run_plugin_parts(global_searcher)
