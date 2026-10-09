import os
import re
from dataclasses import dataclass
from datetime import datetime

from jinja2 import FileSystemLoader, Environment
from hotsos.core.config import HotSOSConfig
from hotsos.core.issues import IssuesManager
from hotsos.core.formatters.common import yaml_dump


@dataclass
class StackPlotSettings:
    """ Settings for a stackplot graph. """
    totals: dict
    peak: int

    @property
    def labels(self):
        """ Plot labels. """
        return sorted(self.totals, key=self.totals.get, reverse=True)


class HTMLFormatter:
    """ Format the summary as html. """

    # Colours used, in order, for bar chart bars.
    BAR_COLOURS = (
        '#e95420', '#772953', '#0e8420', '#2c7ef8', '#c19b00',
        '#007aa6', '#a01b16', '#5e2750', '#19a33a', '#6b7280',
    )

    # Keys that identify a statistics mapping (min/max/avg/...) rather than a
    # distribution of counts. These must never be rendered as a bar chart.
    STATS_KEYS = frozenset({'min', 'max', 'stdev', 'stddev', 'avg', 'mean',
                            'median', 'samples'})

    # Keys whose descendant distributions are rendered as pie charts rather
    # than bar charts (e.g. the OpenStack API http request/status breakdowns).
    PIE_CHART_KEYS = frozenset({'http-requests', 'http-status'})

    # Matches labels that begin with an ISO-style date (optionally followed by
    # a time), used to recognise the timestamp keys of a time series.
    TIMESTAMP_RE = re.compile(r'^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2})?')

    # Matches shortened top-N result keys (e.g. top5) emitted when a date has
    # more entries than the per-date display limit.
    TOP_N_RE = re.compile(r'^top\d+$')

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

    def _expand_list(self, data, level, chart_type='bar'):
        context = {'list_elements': [], 'indent': '    '}
        for item in data:
            context['list_elements'].append(
                self._expand(item, level, chart_type))

        return self.render(context, 'content_list.html')

    def _expand_dict(self, data, level, chart_type='bar'):
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
                child_chart_type = self._child_chart_type(key, chart_type)
                branches.append({
                    'key': key,
                    'content': self._expand(value, level + 1,
                                            child_chart_type),
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

    def _expand(self, data, level, chart_type='bar'):
        """Expand the data object.

        @param data: The data object. This can be a dict, list, or a flat type
                     such as int or str.
        @param level: The current header level
        @param chart_type: Chart style to use for numeric distributions ('bar'
                           or 'pie').
        @return: A string expansion formatted in HTML of the data object.
        """
        if isinstance(data, dict):
            return self._expand_mapping(data, level, chart_type)
        if isinstance(data, list):
            return self._expand_list(data, level, chart_type)

        return data

    def _expand_mapping(self, data, level, chart_type):
        """ Expand a dict, choosing a plot or plain structure as appropriate.

        Pie charts always plot (even for a single date/time). Time series count
        data is plotted whether it is grouped by date ({timestamp: {label:
        count}} or {timestamp: count}) or by label ({label: {timestamp:
        count}}), as produced by the various categorise_events groupings. It is
        drawn as a stackplot when it spans at least two dates/times; a single
        date/time cannot form a stackplot so it is graphed as a bar chart
        instead (one bar per date for a scalar, one bar per label for a
        breakdown). A per-date top-N result ({timestamp: {total, topN}}) plots
        its daily totals as a time series with the top-N breakdown kept below.
        Non-timestamp (category) distributions stay as bar charts.
        """
        # Pie charts are rendered for specific keys and always plot, even for
        # a single date/time.
        if chart_type == 'pie':
            if self._is_count_mapping(data):
                return self._expand_distribution(data, 'pie')
        # chart_type 'none' disables plotting for this branch and its
        # descendants (e.g. the contents of a top-N result).
        elif chart_type != 'none':
            timeseries = self._timeseries_data(data)
            if timeseries is None:
                timeseries = self._label_keyed_timeseries(data)
            if timeseries is not None:
                chart = self._graph_timeseries(data, timeseries)
                if chart is not None:
                    return chart
                return self._expand_dict(data, level, 'none')
            if self._is_numeric_distribution(data):
                return self._expand_distribution(data, chart_type)
            # A per-date top-N result plots its daily totals over time with the
            # top-N breakdown kept as detail below the chart.
            totals = self._topn_totals(data)
            if totals is not None:
                chart = self._graph_timeseries(totals,
                                               self._timeseries_data(totals))
                if chart is not None:
                    return chart + self._expand_dict(data, level, 'none')

        return self._expand_dict(data, level, chart_type)

    def _graph_timeseries(self, data, timeseries):
        """ Render normalised time series as a chart.

        Two or more dates/times give a stackplot (a single series is drawn as a
        line); a single date/time gives a bar chart. Returns None when a
        multi-date stackplot would be degenerate.
        """
        if len(timeseries) >= 2:
            return self._expand_stackplot(timeseries)

        return self._expand_distribution(
            self._single_date_bars(data, timeseries), 'bar')

    @classmethod
    def _topn_totals(cls, data):
        """ Return {timestamp: total} for a per-date top-N result.

        categorise_events shortens a date with more entries than the display
        limit to {'total': N, 'topN': {...}} but leaves quieter dates as
        ordinary {label: count} mappings. Recognise both shapes across all
        dates and return the per-date totals so they can be plotted over time:
        a shortened date contributes its recorded 'total' while an unshortened
        date contributes len(value) to match the producer's count of distinct
        entries. Returns None if the data is not a per-date top-N result (i.e.
        no date is shortened).
        """
        if not isinstance(data, dict) or not data:
            return None

        totals = {}
        shortened = False
        for ts, value in data.items():
            if not cls.TIMESTAMP_RE.match(str(ts)) or not isinstance(value,
                                                                     dict):
                return None

            total = value.get('total')
            has_topn = any(cls.TOP_N_RE.match(str(k)) for k in value)
            if has_topn:
                # bool is a subclass of int but is not a count.
                if isinstance(total, bool) or not isinstance(total, int):
                    return None
                totals[ts] = total
                shortened = True
            elif cls._is_count_mapping(value):
                totals[ts] = len(value)
            else:
                return None

        if not shortened:
            return None

        return totals

    @classmethod
    def _single_date_bars(cls, data, timeseries):
        """ Return the {label: count} bars for a single-date time series.

        A scalar value per date gives one bar per date; a {label: count}
        breakdown (date- or label-keyed) gives one bar per label.
        """
        if all(not isinstance(v, dict) for v in data.values()):
            return {ts: inner['count'] for ts, inner in timeseries.items()}

        return cls._sum_by_label(timeseries)

    def _child_chart_type(self, key, chart_type):
        """ Return the chart style to use for the value of the given key. """
        key = str(key)
        # Never render the contents of a top-N (e.g. top5) result as a plot.
        if chart_type == 'none' or self.TOP_N_RE.match(key):
            return 'none'
        if key in self.PIE_CHART_KEYS:
            return 'pie'

        return chart_type

    @classmethod
    def _is_count_mapping(cls, data):
        """ Return True if data maps labels to non-negative integer counts.

        Statistics mappings (min/max/avg/...) and mappings containing non-count
        values are explicitly excluded.
        """
        if not isinstance(data, dict) or not data:
            return False

        if {str(k) for k in data}.issubset(cls.STATS_KEYS):
            return False

        total = 0
        for value in data.values():
            # bool is a subclass of int but is not a count.
            if isinstance(value, bool) or not isinstance(value, int):
                return False
            if value < 0:
                return False
            total += value

        return total > 0

    @classmethod
    def _is_numeric_distribution(cls, data):
        """ Return True if data is a distribution of counts.

        A distribution is a mapping of labels (e.g. dates or other categories)
        to non-negative integer counts, such as the time series tallies emitted
        by plugin extensions. These are rendered as bar charts.
        """
        return len(data) >= 2 and cls._is_count_mapping(data)

    @classmethod
    def _timeseries_data(cls, data):
        """ Normalise timestamp-keyed count data for plotting.

        Accepts both nested {timestamp: {label: count}} and flat
        {timestamp: count} data (the latter plotted as a single 'count'
        series). Returns None if the data is not timestamp-keyed count data,
        or if it contains a shortened {'total': N, 'topN': {...}} top-N result
        (which must not be rendered as a plot).
        """
        if not isinstance(data, dict) or not data:
            return None

        normalised = {}
        for ts, value in data.items():
            if not cls.TIMESTAMP_RE.match(str(ts)):
                return None

            if isinstance(value, dict):
                if not cls._is_count_mapping(value):
                    return None
                normalised[ts] = value
            elif isinstance(value, bool) or not isinstance(value, int):
                # bool is a subclass of int but is not a count.
                return None
            elif value < 0:
                return None
            else:
                normalised[ts] = {'count': value}

        return normalised

    @classmethod
    def _label_keyed_timeseries(cls, data):
        """ Normalise label-keyed time series data for plotting.

        categorise_events can group a time series by label at the top level
        (key_by_date=False), producing {label: {timestamp: count}} - the
        transpose of the {timestamp: {label: count}} date-keyed form. Recognise
        that shape and transpose it to {timestamp: {label: count}} so it can be
        plotted over time as a single chart rather than fragmented into one
        chart per label (or buried a level down when there is a single label).
        Returns None if the data is not label-keyed time series count data.
        """
        if not isinstance(data, dict) or not data:
            return None

        # A date-keyed mapping is handled by _timeseries_data, not here.
        if any(cls.TIMESTAMP_RE.match(str(key)) for key in data):
            return None

        transposed = {}
        for label, series in data.items():
            if not isinstance(series, dict) or not series:
                return None

            for ts, count in series.items():
                if not cls.TIMESTAMP_RE.match(str(ts)):
                    return None
                # bool is a subclass of int but is not a count.
                if (isinstance(count, bool) or not isinstance(count, int) or
                        count < 0):
                    return None

                transposed.setdefault(ts, {})[str(label)] = count

        return transposed

    @staticmethod
    def _sum_by_label(data):
        """ Sum counts for each label across the timestamp mappings. """
        totals = {}
        for inner in data.values():
            for label, count in inner.items():
                totals[label] = totals.get(label, 0) + count

        return totals

    @classmethod
    def _bar_rows(cls, data):
        """ Build the metadata for each bar of a bar chart.

        Returns a list of bar descriptors (label, value, width relative to the
        largest value and colour) that the content_barchart.html template
        renders.
        """
        total = sum(data.values())
        if total <= 0:
            return []

        largest = max(data.values())
        rows = []
        for idx, (label, value) in enumerate(data.items()):
            rows.append({
                'label': str(label),
                'value': value,
                'width': round(value / largest * 100, 1) if largest else 0,
                'colour': cls.BAR_COLOURS[idx % len(cls.BAR_COLOURS)],
            })

        return rows

    @classmethod
    def _pie_slices(cls, data):
        """ Build the metadata for each slice of a pie chart.

        Returns a list of slice descriptors (label, value, percentage of the
        total and colour) along with a CSS conic-gradient describing the pie,
        both consumed by the content_piechart.html template.
        """
        total = sum(data.values())
        if total <= 0:
            return [], ''

        slices = []
        stops = []
        start = 0.0
        last_idx = len(data) - 1
        for idx, (label, value) in enumerate(data.items()):
            colour = cls.BAR_COLOURS[idx % len(cls.BAR_COLOURS)]
            # Force the final slice to end exactly at 100% so rounding never
            # leaves a seam or overlap between adjacent gradient stops.
            end = 100.0 if idx == last_idx else start + (value / total * 100)
            stops.append(f"{colour} {start}% {end}%")
            slices.append({
                'label': str(label),
                'value': value,
                'percent': round(value / total * 100, 1),
                'colour': colour,
            })
            start = end

        gradient = 'conic-gradient(' + ', '.join(stops) + ')'
        return slices, gradient

    def _expand_distribution(self, data, chart_type='bar'):
        """ Render a distribution of counts as a bar or pie chart. """
        if chart_type == 'pie':
            slices, gradient = self._pie_slices(data)
            if slices:
                return self.render({'slices': slices, 'gradient': gradient},
                                   'content_piechart.html')

        rows = self._bar_rows(data)
        if not rows:
            return self._expand_dict(data, 0)

        return self.render({'rows': rows}, 'content_barchart.html')

    @staticmethod
    def _y(value, peak):
        """ Map a stacked value to an SVG y coordinate (0 at the top). """
        return round(100 - value / peak * 100, 2)

    @classmethod
    def _parse_timestamp(cls, ts):
        """ Parse the date (and optional time) prefix of a timestamp label.

        Returns a datetime, or None if the label cannot be parsed.
        """
        match = cls.TIMESTAMP_RE.match(str(ts))
        if not match:
            return None

        text = match.group(0).replace('T', ' ')
        fmt = '%Y-%m-%d %H:%M' if ' ' in text else '%Y-%m-%d'
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            return None

    @classmethod
    def _stackplot_columns(cls, timestamps):
        """ Return the (sample timestamps, x coordinates) for each column.

        x coordinates are scaled by the elapsed time between timestamps so a
        sparse series (e.g. events on non-consecutive days) is spaced
        proportionally to real time rather than at equal intervals - otherwise
        a gap such as a missing day would be drawn as continuous activity.
        Falls back to equal spacing when the labels cannot be parsed as dates.
        """
        parsed = [cls._parse_timestamp(ts) for ts in timestamps]
        if all(p is not None for p in parsed) and parsed[-1] != parsed[0]:
            start = parsed[0]
            span = (parsed[-1] - start).total_seconds()
            xs = [round((p - start).total_seconds() / span * 100, 2)
                  for p in parsed]
        else:
            span = len(timestamps) - 1
            xs = [round(j / span * 100, 2) for j in range(len(timestamps))]

        return list(timestamps), xs

    @classmethod
    def _stackplot_series(cls, data):
        """ Build the SVG geometry for a stacked area chart (stackplot).

        data maps timestamps to {label: count}. Returns the ordered timestamp
        axis labels (each paired with the SVG x coordinate of its sample so
        labels align with the plotted points rather than being spaced evenly)
        and, for each label (series), a polygon of stacked points, a standalone
        line of its own (unstacked) values for isolating a single series, its
        colour and total. Returns (None, None) when there are fewer than two
        timestamps to plot.
        """
        timestamps = sorted(data)
        if len(timestamps) < 2:
            return None, None

        # Order series by total count so the stack and legend are stable.
        settings = StackPlotSettings(cls._sum_by_label(data),
                                     max(sum(data[ts].values())
                                         for ts in timestamps) or 1)
        samples, xs = cls._stackplot_columns(timestamps)

        lower = [0.0] * len(samples)
        series = []
        for idx, label in enumerate(settings.labels):
            upper = [lower[j] + data[samples[j]].get(label, 0)
                     for j in range(len(samples))]
            # Top edge left->right (also used on its own as a line for a
            # single series) then bottom edge right->left to close the area.
            top = [f"{xs[j]},{cls._y(upper[j], settings.peak)}"
                   for j in range(len(samples))]
            points = top + [f"{xs[j]},{cls._y(lower[j], settings.peak)}"
                            for j in range(len(samples) - 1, -1, -1)]
            # This series' own values plotted from the baseline, used when it
            # is isolated from the stack.
            own = [f"{xs[j]},{cls._y(upper[j] - lower[j], settings.peak)}"
                   for j in range(len(samples))]
            series.append({
                'label': str(label),
                'total': settings.totals[label],
                'colour': cls.BAR_COLOURS[idx % len(cls.BAR_COLOURS)],
                'points': ' '.join(points),
                'line': ' '.join(top),
                'own': ' '.join(own),
            })
            lower = upper

        axis = [{'label': str(samples[j]), 'x': xs[j]}
                for j in range(len(samples))]
        return axis, series

    def _expand_stackplot(self, data):
        """ Render {timestamp: {label: count}} data as a time series chart.

        A single series is drawn as a line; multiple series are drawn as a
        stacked area chart. Returns None if the data cannot be plotted (too
        few timestamps).
        """
        if not data:
            return None

        axis, series = self._stackplot_series(data)
        if not series:
            return None

        # Peak stacked column height sets the top of the value (y) axis.
        peak = max((sum(inner.values()) for inner in data.values()),
                   default=0) or 1
        return self.render({'axis': axis, 'series': series,
                            'single': len(series) == 1,
                            'yticks': self._yaxis_ticks(peak)},
                           'content_stackplot.html')

    @staticmethod
    def _format_count(value):
        """ Format a count compactly for axis labels (e.g. 1.2k, 3.4M). """
        value = float(value)
        for suffix, threshold in (('M', 1e6), ('k', 1e3)):
            if abs(value) >= threshold:
                return f'{value / threshold:.1f}'.rstrip('0').rstrip('.') + \
                    suffix

        return str(int(round(value)))

    @classmethod
    def _yaxis_ticks(cls, peak, count=5):
        """ Return value-axis tick labels from the peak down to zero. """
        return [cls._format_count(peak * (count - 1 - i) / (count - 1))
                for i in range(count)]

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

    @classmethod
    def _cluster_by_category(cls, findings):
        """ Cluster a plugin's findings by issue type (category).

        When more than one finding shares the same category, they are merged
        into a single cluster so the issue type is shown once with all of its
        messages listed together. Clusters are ordered by severity then
        category.
        """
        order = {s: i for i, s in enumerate(cls.SEVERITY_ORDER)}
        clusters = {}
        for finding in findings:
            key = (finding['tone'], finding['category'])
            cluster = clusters.get(key)
            if cluster is None:
                cluster = {
                    'category': finding['category'],
                    'tone': finding['tone'],
                    'severity': finding['severity'],
                    'messages': [],
                }
                clusters[key] = cluster

            cluster['messages'].append(finding['message'])

        result = list(clusters.values())
        for cluster in result:
            cluster['count'] = len(cluster['messages'])
            cluster['multiple'] = cluster['count'] > 1

        result.sort(key=lambda c: (order.get(c['severity'], len(order)),
                                   c['category']))
        return result

    # Plugin names that should be displayed as upper-case acronyms rather
    # than title-cased.
    PLUGIN_ACRONYMS = {'maas': 'MAAS'}

    @classmethod
    def _plugin_label(cls, plugin):
        """ Return the display label for a plugin name. """
        return cls.PLUGIN_ACRONYMS.get(str(plugin).lower(), plugin)

    @classmethod
    def _group_findings(cls, findings):
        """ Group findings by plugin for display at the top of the report.

        Groups are ordered by their most severe finding then plugin name, and
        findings within each group are ordered by severity.
        """
        order = {s: i for i, s in enumerate(cls.SEVERITY_ORDER)}
        groups = {}
        for finding in findings:
            groups.setdefault(finding['plugin'], []).append(finding)

        grouped = []
        for plugin, items in groups.items():
            items.sort(key=lambda f: order.get(f['severity'], len(order)))
            grouped.append({
                'plugin': plugin,
                'label': cls._plugin_label(plugin),
                'findings': items,
                'clusters': cls._cluster_by_category(items),
                'count': len(items),
                'bugs': sum(1 for f in items if f['tone'] == 'bug'),
                'issues': sum(1 for f in items if f['tone'] == 'issue'),
            })

        grouped.sort(key=lambda g: (
            min(order.get(f['severity'], len(order)) for f in g['findings']),
            g['plugin']))
        return grouped

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
            'finding_groups': self._group_findings(findings),
            'finding_counts': self._finding_counts(findings),
            'system_info': self._system_banner(data),
            'health': self._health(findings),
            'summary_stats': self._summary_stats(
                data, sections=sections)},
            'dashboard.html')
        return self.header(hostname) + content + self.footer
