import abc
import os
import yaml

from hotsos.core.log import log
from hotsos.core.config import HotSOSConfig
from abc import abstractproperty, abstractmethod


class IssueContext(object):
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
    def __init__(self, ref, description, key, context=None):
        self.key = key
        self.context = context
        self.ref = ref
        self.description = description
        self.origin = "{}.{}".format(HotSOSConfig.plugin_name,
                                     HotSOSConfig.part_name)

    @abc.abstractproperty
    def content(self):
        """ The is the final representation of the object. """


class IssueEntry(IssueEntryBase):

    @property
    def content(self):
        _content = {self.key: self.ref,
                    'desc': self.description,
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

    @abstractproperty
    def store_path(self):
        pass

    @abstractmethod
    def load(self):
        pass

    @abstractmethod
    def add(self):
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

        bugs = yaml.safe_load(open(self.store_path))
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

        issues = yaml.safe_load(open(self.store_path))
        if issues and IssuesManager.SUMMARY_OUT_ISSUES_ROOT in issues:
            return issues

        return {}

    def add(self, issue, context=None):
        """
        Fetch the current plugin issues.yaml if it exists and add new issue
        with description of the issue.
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


class IssuesManager(object):
    SUMMARY_OUT_ISSUES_ROOT = 'potential-issues'
    SUMMARY_OUT_BUGS_ROOT = 'bugs-detected'

    def __init__(self):
        self.bugstore = KnownBugsStore()
        self.issuestore = IssuesStore()

    def load_bugs(self):
        return self.bugstore.load()

    def load_issues(self):
        issues = self.issuestore.load()
        if issues and not HotSOSConfig.machine_readable:
            types = {}
            for issue in issues[self.SUMMARY_OUT_ISSUES_ROOT]:
                # pluralise the type for display purposes
                issue_type = "{}s".format(issue['type'])
                if issue_type not in types:
                    types[issue_type] = []

                msg = "{} (origin={})".format(issue['desc'], issue['origin'])
                types[issue_type].append(msg)

            # Sort them to enure consistency in output
            for itype in types:
                types[itype] = sorted(types[itype])

            issues = {self.SUMMARY_OUT_ISSUES_ROOT: types}

        return issues

    def add(self, issue, context=None):
        if issue.ISSUE_TYPE == 'bug':
            log.debug("issue is a bug")
            self.bugstore.add(issue, context=context)
        else:
            self.issuestore.add(issue, context=context)
