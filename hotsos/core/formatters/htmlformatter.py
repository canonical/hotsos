import os
import re
from datetime import datetime

from jinja2 import FileSystemLoader, Environment
from hotsos.core.config import HotSOSConfig
from hotsos.core.issues import IssuesManager
from hotsos.core.formatters.common import yaml_dump


class HTMLFormatter:
    """ Format the summary as html. """

    @staticmethod
    def render(context, template):
        """Render a Jinja2 template with the given context."""
        # jinja 2.10.x really needs this to be a str and e.g. not a PosixPath
        templates_dir = str(HotSOSConfig.templates_path)
        if not os.path.isdir(templates_dir):
            raise FileNotFoundError(
                f"jinja templates directory not found: '{templates_dir}'")

        env = Environment(loader=FileSystemLoader(templates_dir))
        template = env.get_template(template)
        return template.render(context)

    def header(self, hostname):
        """Return rendered HTML header for the given hostname."""
        return self.render({'hostname': hostname}, 'header.html')

    @property
    def footer(self):
        """Return raw HTML footer content."""
        with open(os.path.join(HotSOSConfig.templates_path,
                               'footer.html'), encoding='utf-8') as fd:
            return fd.read()

    def _expand_list(self, data, level):
        context = {'list_elements': [], 'indent': '    '}
        for item in data:
            context['list_elements'].append(self._expand(item, level))

        return self.render(context, 'content_list.html')

    def _expand_dict(self, data, level):
        # Split entries into plain key/value fields (rendered as a compact
        # description list) and nested branches (rendered as collapsible
        # disclosure groups). This makes each section far easier to scan than
        # a single interleaved tree of keys and values.
        fields = []
        branches = []
        for key, value in data.items():
            # Keep package/process sections visually consistent with other
            # listings by rendering their flat mappings as list entries.
            if (str(key).lower() in ('dpkg', 'ps') and
                    isinstance(value, dict) and
                    all(not isinstance(v, (dict, list))
                        for v in value.values())):
                value = [f"{k}: {v}" for k, v in value.items()]

            if isinstance(value, (dict, list)):
                tone = self._key_tone(key)
                branches.append({
                    'key': key,
                    'content': self._expand(value, level + 1),
                    'tone': tone,
                    'count': self._count_leaf_nodes(value),
                    'open': True,
                })
            else:
                fields.append({
                    'key': key,
                    'value': '' if value is None else str(value),
                })

        context = {'fields': fields,
                   'branches': branches,
                   'indent': '    ',
                   'level': level}

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

    @staticmethod
    def _anchor_id(name):
        anchor = re.sub(r'[^a-zA-Z0-9]+', '-', str(name).strip().lower())
        return anchor.strip('-') or 'section'

    @staticmethod
    def _monogram(name):
        """ Return a single-character monogram used for plugin cards. """
        for char in str(name):
            if char.isalnum():
                return char.upper()

        return '#'

    @staticmethod
    def _key_tone(key):
        """ Return a colour tone for keys that carry special emphasis. """
        if key == IssuesManager.SUMMARY_OUT_BUGS_ROOT:
            return 'bug'
        if key == IssuesManager.SUMMARY_OUT_ISSUES_ROOT:
            return 'issue'

        return None

    @staticmethod
    def _count_leaf_nodes(data):
        if isinstance(data, dict):
            return sum(HTMLFormatter._count_leaf_nodes(value)
                       for value in data.values())

        if isinstance(data, list):
            return sum(HTMLFormatter._count_leaf_nodes(item)
                       for item in data)

        return 1

    @staticmethod
    def _count_items(data):
        if isinstance(data, dict):
            return len(data)

        if isinstance(data, list):
            return len(data)

        return 1

    @staticmethod
    def _count_known_issues(summary):
        count = 0

        if not isinstance(summary, dict):
            return count

        for key, value in summary.items():
            if key in (IssuesManager.SUMMARY_OUT_ISSUES_ROOT,
                       IssuesManager.SUMMARY_OUT_BUGS_ROOT):
                if isinstance(value, dict):
                    for entries in value.values():
                        if isinstance(entries, list):
                            count += len(entries)
                        else:
                            count += 1
                elif isinstance(value, list):
                    count += len(value)
                else:
                    count += 1
                continue

            count += HTMLFormatter._count_known_issues(value)

        return count

    @staticmethod
    def _section_issue_count(key, value):
        """ Count known issues/bugs contained within a section. """
        if key in (IssuesManager.SUMMARY_OUT_ISSUES_ROOT,
                   IssuesManager.SUMMARY_OUT_BUGS_ROOT):
            return HTMLFormatter._count_known_issues({key: value})

        return HTMLFormatter._count_known_issues(value)

    # Ordering used when sorting/displaying findings by severity.
    SEVERITY_ORDER = ('high', 'medium', 'low')

    @staticmethod
    def _severity(tone, category):
        """ Map a finding to a severity level.

        Bugs and errors are treated as high severity, warnings as medium
        severity and everything else as low severity.
        """
        if tone == 'bug':
            return 'high'

        label = str(category).lower()
        if 'error' in label:
            return 'high'
        if 'warning' in label:
            return 'medium'

        return 'low'

    @classmethod
    def _flatten_issue_root(cls, plugin, data, tone):
        """ Flatten a potential-issues/bugs-detected node into findings. """
        findings = []
        if isinstance(data, dict):
            for category, messages in data.items():
                severity = cls._severity(tone, category)
                if isinstance(messages, list):
                    for message in messages:
                        findings.append({'plugin': plugin, 'tone': tone,
                                         'severity': severity,
                                         'category': str(category),
                                         'message': str(message)})
                else:
                    findings.append({'plugin': plugin, 'tone': tone,
                                     'severity': severity,
                                     'category': str(category),
                                     'message': str(messages)})
        elif isinstance(data, list):
            category = ('Known bug' if tone == 'bug' else 'Potential issue')
            severity = cls._severity(tone, category)
            for message in data:
                findings.append({'plugin': plugin, 'tone': tone,
                                 'severity': severity,
                                 'category': category,
                                 'message': str(message)})

        return findings

    @classmethod
    def _extract_findings(cls, plugin, value):
        """ Recursively collect issues and bugs within a plugin section. """
        findings = []
        if not isinstance(value, dict):
            return findings

        for key, sub in value.items():
            if key == IssuesManager.SUMMARY_OUT_ISSUES_ROOT:
                findings.extend(cls._flatten_issue_root(plugin, sub, 'issue'))
            elif key == IssuesManager.SUMMARY_OUT_BUGS_ROOT:
                findings.extend(cls._flatten_issue_root(plugin, sub, 'bug'))
            else:
                findings.extend(cls._extract_findings(plugin, sub))

        return findings

    @classmethod
    def _collect_findings(cls, data):
        """ Collect all issues and bugs across plugins with attribution. """
        findings = []
        if not isinstance(data, dict):
            return findings

        for plugin, value in data.items():
            findings.extend(cls._extract_findings(plugin, value))

        # highest severity first so the most severe findings surface at the top
        order = {s: i for i, s in enumerate(cls.SEVERITY_ORDER)}
        findings.sort(key=lambda f: (order.get(f['severity'], len(order)),
                                     f['plugin']))
        return findings

    @staticmethod
    def _health(findings):
        """ Derive an overall health status from collected findings. """
        bugs = sum(1 for f in findings if f['tone'] == 'bug')
        issues = sum(1 for f in findings if f['tone'] == 'issue')
        if bugs:
            detail = f"{bugs} known bug(s) and {issues} potential issue(s)"
            return {'status': 'Action required', 'tone': 'negative',
                    'detail': detail, 'bugs': bugs, 'issues': issues}
        if issues:
            return {'status': 'Needs attention', 'tone': 'caution',
                    'detail': f"{issues} potential issue(s) detected",
                    'bugs': bugs, 'issues': issues}

        return {'status': 'Healthy', 'tone': 'positive',
                'detail': 'No known issues or bugs detected',
                'bugs': 0, 'issues': 0}

    def _sections(self, data):
        if not isinstance(data, dict):
            return [{
                'name': 'summary',
                'id': 'summary',
                'monogram': self._monogram('summary'),
                'items': self._count_items(data),
                'leaves': self._count_leaf_nodes(data),
                'issues': self._count_known_issues(data),
                'content': self._expand(data, 2),
            }]

        sections = []
        for key, value in data.items():
            findings = self._extract_findings(key, value)
            sections.append({
                'name': key,
                'id': self._anchor_id(key),
                'monogram': self._monogram(key),
                'items': self._count_items(value),
                'leaves': self._count_leaf_nodes(value),
                'issues': self._section_issue_count(key, value),
                'bugs': sum(1 for f in findings if f['tone'] == 'bug'),
                'warnings': sum(1 for f in findings if f['tone'] == 'issue'),
                'content': self._expand(value, 2),
            })

        return sections

    def _summary_stats(self, data, sections=None):
        if sections is None:
            sections = self._sections(data)

        known_issues = self._count_known_issues(data)
        return [
            {'label': 'Plugins', 'value': len(sections), 'tone': 'info'},
            {'label': 'Known issues/bugs', 'value': known_issues,
             'tone': 'negative' if known_issues else 'positive'},
        ]

    # Keys emitted by the system plugin to surface in the banner, in the
    # order they should be displayed along with a human friendly label.
    SYSTEM_BANNER_KEYS = (
        ('os', 'OS'),
        ('num-cpus', 'CPUs'),
        ('load', 'Load average'),
        ('virtualisation', 'Virtualisation'),
        ('rootfs', 'Root fs'),
        ('uptime', 'Uptime'),
        ('unattended-upgrades', 'Unattended upgrades'),
        ('date', 'Snapshot date'),
    )

    @classmethod
    def _system_banner(cls, data):
        """ Extract key system information for the banner.

        Pulls a curated set of fields from the 'system' plugin summary (if
        present) so that the most important host details are surfaced at the
        top of the report.
        """
        if not isinstance(data, dict):
            return []

        system = data.get('system')
        if not isinstance(system, dict):
            return []

        items = []
        for key, label in cls.SYSTEM_BANNER_KEYS:
            if key not in system:
                continue

            value = system[key]
            if isinstance(value, dict):
                # e.g. ubuntu-pro is a nested object - fall back to a status.
                value = value.get('status', yaml_dump(value))

            if value is None or str(value).strip() == '':
                continue

            items.append({'label': label, 'value': str(value).strip()})

        return items

    @classmethod
    def _finding_counts(cls, findings):
        """ Return counts of findings by severity for the severity filters. """
        counts = {'all': len(findings)}
        for severity in cls.SEVERITY_ORDER:
            counts[severity] = sum(1 for f in findings
                                   if f['severity'] == severity)
        return counts

    def dump(self, data):
        """Convert the data (dict) into an html document.

        @param dist: The data
        @return: the html document as a string.
        """
        sections = self._sections(data)
        findings = self._collect_findings(data)
        hostname = data.get('system', {}).get('hostname', '')
        content = self.render({
            'hostname': hostname,
            'generated_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%SZ'),
            'sections': sections,
            'findings': findings,
            'finding_counts': self._finding_counts(findings),
            'system_info': self._system_banner(data),
            'health': self._health(findings),
            'summary_stats': self._summary_stats(
                data, sections=sections)},
            'dashboard.html')
        return self.header(hostname) + content + self.footer
