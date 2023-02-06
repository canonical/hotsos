import os
import yaml

from jinja2 import FileSystemLoader, Environment

from hotsos.core.config import HotSOSConfig
from hotsos.core.log import log
from hotsos.core.issues import IssuesManager
from hotsos.core.ycheck.scenarios import YScenarioChecker


def summary_entry_offset(offset):
    def _inner(f):
        def _inner2(*args, **kwargs):
            out = f(*args, **kwargs)
            if out is not None:
                return {'data': out, 'offset': offset}

        return _inner2
    return _inner


class HOTSOSDumper(yaml.Dumper):
    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)

    def represent_dict_preserve_order(self, data):
        return self.represent_dict(data.items())


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


class OutputFormatterBase(object):

    def render(self, context, template):
        templates_dir = HotSOSConfig.templates_path
        if not os.path.isdir(templates_dir):
            raise Exception("jinja templates directory not found: '{}'".
                            format(templates_dir))

        env = Environment(loader=FileSystemLoader(templates_dir))
        template = env.get_template(template)
        return template.render(context)


class HTMLFormatter(OutputFormatterBase):
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

    @property
    def header(self):
        return self.render({'hostname': self.hostname}, 'header.html')

    @property
    def footer(self):
        with open(os.path.join(HotSOSConfig.templates_path,
                               'footer.html')) as fd:
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
        elif isinstance(data, list):
            return self._expand_list(data, level)

        return data

    def dump(self, data):
        """Convert the data (dict) into an html document.

        @param dist: The data
        @return: the html document as a string.
        """
        content = self._expand(data, 1)
        return self.header + content + self.footer


class MarkdownFormatter(OutputFormatterBase):

    def _expand_dict(self, data, level):
        level_prefix = ''.join(['#' for i in range(level)])
        markdown_output = ''
        for key in data:
            markdown_output += f'\n{level_prefix} {key}\n'
            markdown_output += self._expand(data[key], level + 1)

        return markdown_output

    def _expand_list(self, data):
        markdown_output = '\n'
        for item in data:
            markdown_output += f'- {item}\n'

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
        elif isinstance(data, list):
            return self._expand_list(data)

        return f'\n{data}\n'

    def dump(self, data):
        """Convert the data (dict) into a markdown document.

        @param data: dict:- The data
        @return: str: The markdown document
        """
        markdown = '# hotsos summary\n' + self._expand(data, 2)
        return markdown.rstrip('\n')


class ApplicationBase(object):

    @property
    def bind_interfaces(self):
        """Implement this method to return a dict of network interfaces used
        by this application.
        """
        raise NotImplementedError


class SummaryEntry(object):

    def __init__(self, data, offset):
        self.data = data
        self.offset = offset

    @staticmethod
    def is_raw_entry(entry):
        if type(entry) != dict:
            return False

        if set(entry.keys()).symmetric_difference(['data', 'offset']):
            return False

        return True


class PartManager(object):

    def save(self, data, offset):
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
                                 "{}.{}.part.yaml".
                                 format(HotSOSConfig.plugin_name,
                                        HotSOSConfig.part_name))

        # don't clobber
        if os.path.exists(part_path):
            newpath = part_path
            i = 0
            while os.path.exists(newpath):
                i += 1
                newpath = "{}.{}".format(part_path, i)

            part_path = newpath

        with open(part_path, 'w') as fd:
            fd.write(out)

        self.add_to_index(offset, part_path)

    @property
    def index(self):
        path = os.path.join(HotSOSConfig.plugin_tmp_dir, "index.yaml")
        index = {}
        if os.path.exists(path):
            with open(path) as fd:
                index = yaml.safe_load(fd.read()) or {}

        return index

    def add_to_index(self, offset, part):
        index = self.index
        if offset in index:
            index[offset].append(part)
        else:
            index[offset] = [part]

        path = os.path.join(HotSOSConfig.plugin_tmp_dir, "index.yaml")
        with open(path, 'w') as fd:
            fd.write(yaml.dump(index))

    def meld_part_output(self, data, existing):
        """
        Don't allow root level keys to be clobbered, instead just
        update them. This assumes that part subkeys will be unique.
        """
        remove_keys = []
        for key in data:
            if key in existing:
                if type(existing[key]) == dict:
                    existing[key].update(data[key])
                    remove_keys.append(key)

        if remove_keys:
            for key in remove_keys:
                del data[key]

        existing.update(data)

    def all(self):
        if not self.index:
            return

        parts = {}
        for offset in sorted(self.index):
            for part in self.index[offset]:
                with open(part) as fd:
                    part_yaml = yaml.safe_load(fd)

                    # Don't allow root level keys to be clobbered, instead just
                    # update them. This assumes that part subkeys will be
                    # unique.
                    self.meld_part_output(part_yaml, parts)

        return {HotSOSConfig.plugin_name: parts}


class PluginPartBase(ApplicationBase):
    # max per part before overlap
    PLUGIN_PART_OFFSET_MAX = 500

    def __init__(self, *args, **kwargs):
        plugin_tmp = HotSOSConfig.plugin_tmp_dir
        if not plugin_tmp or not os.path.isdir(plugin_tmp):
            raise Exception("plugin plugin_tmp_dir not initialised - exiting")

        super().__init__(*args, **kwargs)

    @property
    def plugin_runnable(self):
        """
        Must be implemented by all plugins to define at runtime whether they
        should run.
        """
        raise NotImplementedError

    @property
    def summary_subkey(self):
        """
        This can be optionally implemented in order to have all output of the
        current part placed under the keyname provided by this property i.e.
        <plugin_name>: <subkey>: ...
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

    @property
    def output(self):
        _output = {}
        if self.summary:
            for key, data in self.summary.items():
                _output[key] = SummaryEntry(data, 0)

        for m in dir(self.__class__):
            cls = self.__class__.__name__
            if m.startswith('_{}__summary_'.format(cls)):
                key = m.partition('_{}__summary_'.format(cls))[2]
                key = key.replace('_', '-')
                out = getattr(self, m)()
                if not out:
                    continue

                if SummaryEntry.is_raw_entry(out):
                    out = SummaryEntry(out['data'], out['offset'])
                else:
                    # put at the end
                    out = SummaryEntry(out, self.PLUGIN_PART_OFFSET_MAX - 1)

                _output[key] = out

        return _output

    @property
    def raw_output(self):
        out = self.output
        if out:
            return {key: entry.data for key, entry in out.items()}

    def __call__(self):
        pass


class PluginRunner(object):

    def __init__(self, parts):
        self.parts = parts

    def run(self):
        part_mgr = PartManager()
        failed_parts = []
        # The following are executed as part of each plugin run (but not last).
        ALWAYS_RUN = {'auto_scenario_check': YScenarioChecker}
        for name, always_parts in ALWAYS_RUN.items():
            # update current env to reflect actual part being run
            HotSOSConfig.part_name = name
            try:
                always_parts()()
            except Exception as exc:
                failed_parts.append(name)
                log.exception("part '%s' raised exception: %s", name, exc)

            # NOTE: we don't expect these parts to produce any output
            # for the summary so we wont check for it (they only raise
            # issues and bugs which are handled independently).

        for name, part_info in self.parts.items():
            # update current env to reflect actual part being run
            HotSOSConfig.part_name = name
            for cls in part_info['objects']:
                inst = cls()
                # Only run plugin if it declares itself runnable.
                if not HotSOSConfig.force_mode and not inst.plugin_runnable:
                    log.debug("%s.%s.%s not runnable - skipping",
                              HotSOSConfig.plugin_name, name, cls.__name__)
                    continue

                log.debug("running %s.%s.%s",
                          HotSOSConfig.plugin_name, name, cls.__name__)
                try:
                    inst()
                    # NOTE: since all parts are expected to be implementations
                    # of PluginPartBase we expect them to always define an
                    # output property.
                    output = inst.output
                    subkey = inst.summary_subkey
                except Exception as exc:
                    failed_parts.append(name)
                    log.exception("part '%s' raised exception: %s", name, exc)
                    output = None

                if output:
                    for key, entry in output.items():
                        out = {key: entry.data}
                        if subkey:
                            out = {subkey: out}

                        part_max = PluginPartBase.PLUGIN_PART_OFFSET_MAX
                        part_offset = part_info['part_yaml_offset']
                        offset = ((part_offset * part_max) + entry.offset)
                        part_mgr.save(out, offset=offset)

        if failed_parts:
            # always put these at the top
            part_mgr.save({'failed-parts': failed_parts}, offset=0)

        imgr = IssuesManager()
        bugs = imgr.load_bugs()
        raised_issues = imgr.load_issues()
        summary_end_offset = PluginPartBase.PLUGIN_PART_OFFSET_MAX ** 2

        # Add detected known_bugs and raised issues to end summary.
        if bugs:
            part_mgr.save(bugs, offset=summary_end_offset)

        # Add raised issues to summary.
        if raised_issues:
            part_mgr.save(raised_issues, offset=summary_end_offset)

        return part_mgr.all()
