import abc
import os
from dataclasses import dataclass, field
from typing import Any

import yaml
from hotsos.core.config import HotSOSConfig
from hotsos.core.log import log
from hotsos.core.utils import sorted_dict


class IssueContext():
    """ Key value store for machine readable context. """
    def __init__(self, **kwargs):
        self.context = {}
        self.set(**kwargs)

    def set(self, **kwargs):
        self.context.update(kwargs)

    def __len__(self):
        return len(self.context)

    def to_dict(self):
        return self.context


@dataclass(frozen=True)
class IssueEntry:
    """ A single issue object as stored for later use. """

    ref: str
    message: str
    key: str
    context: Any = None
    origin: str = field(
        # We're using default_factory here to defer the evaluation of
        # the "default" value to runtime.
        default_factory=(
            lambda: f"{HotSOSConfig.plugin_name}.{HotSOSConfig.part_name}"
        )
    )

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
    """ Base class for issue store backend implementatios. """
    def __init__(self):
        if not os.path.isdir(HotSOSConfig.plugin_tmp_dir):
            raise FileNotFoundError(
                f"plugin tmp dir '{HotSOSConfig.plugin_tmp_dir}' not found")

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
    """ Known bug backend store """
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

        with open(self.store_path, encoding='utf-8') as fd:
            bugs = yaml.safe_load(fd)
        if bugs and IssuesManager.SUMMARY_OUT_BUGS_ROOT in bugs:
            return bugs

        return {}

    def add(self, issue, context=None):
        #  def __init__(self, ref, message, key, context=None):
        entry = IssueEntry(
            ref=issue.url,
            message=issue.msg,
            key='id',
            context=context
        )
        current = self.load()
        if current:
            current[IssuesManager.SUMMARY_OUT_BUGS_ROOT].append(entry.content)
        else:
            current = {IssuesManager.SUMMARY_OUT_BUGS_ROOT: [entry.content]}

        with open(self.store_path, 'w', encoding='utf-8') as fd:
            fd.write(yaml.dump(current))


class IssuesStore(IssuesStoreBase):
    """ Potential issue backend store """
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

        with open(self.store_path, encoding='utf-8') as fd:
            issues = yaml.safe_load(fd)
        if issues and IssuesManager.SUMMARY_OUT_ISSUES_ROOT in issues:
            return issues

        return {}

    def add(self, issue, context=None):
        """
        Fetch the current plugin issues.yaml if it exists and add new issue.
        """
        entry = IssueEntry(
            ref=issue.name,
            message=issue.msg,
            key='type',
            context=context
        )
        current = self.load()
        key = IssuesManager.SUMMARY_OUT_ISSUES_ROOT
        if current:
            current[key].append(entry.content)
        else:
            current = {key: [entry.content]}

        with open(self.store_path, 'w', encoding='utf-8') as fd:
            fd.write(yaml.dump(current))


class IssuesManager():
    """ Manager for all issue store backends.  """
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
                issue_type = f"{issue['type']}s"
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
