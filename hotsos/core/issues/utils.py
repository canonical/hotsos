import abc
import os

import yaml
from hotsos.core.config import HotSOSConfig
from hotsos.core.log import log
from hotsos.core.utils import sorted_dict


class IssueContext():
    def __init__(self, **kwargs):
        self.context = {}
        self.set(**kwargs)

    def set(self, **kwargs):
        self.context.update(kwargs)

    def __len__(self):
        return len(self.context)

    def to_dict(self):
        return self.context


class IssueEntryBase(abc.ABC):
    def __init__(self, ref, message, key, context=None):
        self.key = key
        self.context = context
        self.ref = ref
        self.message = message
        self.origin = "{}.{}".format(HotSOSConfig.plugin_name,
                                     HotSOSConfig.part_name)

    @property
    @abc.abstractmethod
    def content(self):
        """ The is the final representation of the object. """


class IssueEntry(IssueEntryBase):

    @property
    def content(self):
        _content = {self.key: self.ref,
                    'message': self.message,
                    'origin': self.origin}
        if HotSOSConfig.machine_readable:
            if len(self.context or {}):
                _content['context'] = self.context.to_dict()

        return _content


class IssuesStoreBase(abc.ABC):

    def __init__(self):
        if not os.path.isdir(HotSOSConfig.plugin_tmp_dir):
            raise Exception("plugin tmp dir  '{}' not found".
                            format(HotSOSConfig.plugin_tmp_dir))

    @property
    @abc.abstractmethod
    def store_path(self):
        pass

    @abc.abstractmethod
    def load(self):
        pass

    @abc.abstractmethod
    def add(self, issue):
        pass


class KnownBugsStore(IssuesStoreBase):

    @property
    def store_path(self):
        return os.path.join(HotSOSConfig.plugin_tmp_dir, 'known_bugs.yaml')

    def load(self):
        """
        Fetch the current plugin known_bugs.yaml if it exists and return its
        contents or None if it doesn't exist yet.
        """
        if not os.path.exists(self.store_path):
            return {}

        with open(self.store_path) as fd:
            bugs = yaml.safe_load(fd)
        if bugs and IssuesManager.SUMMARY_OUT_BUGS_ROOT in bugs:
            return bugs

        return {}

    def add(self, issue, context=None):
        entry = IssueEntry(issue.url, issue.msg, 'id', context=context)
        current = self.load()
        if current:
            current[IssuesManager.SUMMARY_OUT_BUGS_ROOT].append(entry.content)
        else:
            current = {IssuesManager.SUMMARY_OUT_BUGS_ROOT: [entry.content]}

        with open(self.store_path, 'w') as fd:
            fd.write(yaml.dump(current))


class IssuesStore(IssuesStoreBase):

    @property
    def store_path(self):
        return os.path.join(HotSOSConfig.plugin_tmp_dir, 'issues.yaml')

    def load(self):
        """
        Fetch the current plugin issues.yaml if it exists and return its
        contents or None if it doesn't exist yet.
        """
        if not os.path.exists(self.store_path):
            return {}

        with open(self.store_path) as fd:
            issues = yaml.safe_load(fd)
        if issues and IssuesManager.SUMMARY_OUT_ISSUES_ROOT in issues:
            return issues

        return {}

    def add(self, issue, context=None):
        """
        Fetch the current plugin issues.yaml if it exists and add new issue.
        """
        entry = IssueEntry(issue.name, issue.msg, 'type', context=context)
        current = self.load()
        key = IssuesManager.SUMMARY_OUT_ISSUES_ROOT
        if current:
            current[key].append(entry.content)
        else:
            current = {key: [entry.content]}

        with open(self.store_path, 'w') as fd:
            fd.write(yaml.dump(current))


class IssuesManager():
    SUMMARY_OUT_ISSUES_ROOT = 'potential-issues'
    SUMMARY_OUT_BUGS_ROOT = 'bugs-detected'

    def __init__(self):
        self.bugstore = KnownBugsStore()
        self.issuestore = IssuesStore()

    def load_bugs(self):
        bugs = self.bugstore.load()
        if bugs and not HotSOSConfig.machine_readable:
            urls = {}
            for bug in bugs[self.SUMMARY_OUT_BUGS_ROOT]:
                urls[bug['id']] = bug['message']

            bugs = {self.SUMMARY_OUT_BUGS_ROOT: sorted_dict(urls)}

        return bugs

    def load_issues(self):
        issues = self.issuestore.load()
        if issues and not HotSOSConfig.machine_readable:
            types = {}
            for issue in issues[self.SUMMARY_OUT_ISSUES_ROOT]:
                # pluralise the type for display purposes
                issue_type = "{}s".format(issue['type'])
                if issue_type not in types:
                    types[issue_type] = []

                types[issue_type].append(issue['message'])

            # Sort them to ensure consistency in output
            for issue_type, issues in types.items():
                types[issue_type] = sorted(issues)

            issues = {self.SUMMARY_OUT_ISSUES_ROOT: sorted_dict(types)}

        return issues

    def add(self, issue, context=None):
        if issue.ISSUE_TYPE in ('bug', 'cve'):
            log.debug("issue is a %s", issue.ISSUE_TYPE)
            self.bugstore.add(issue, context=context)
        else:
            self.issuestore.add(issue, context=context)
