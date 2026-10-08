"""
Collect upstream bug candidates for the upstream-bug-scout agentic workflow.

Queries Launchpad and GitHub (issues and security advisories) for recently
updated bugs in the projects listed in the scout config, drops anything
hotsos already has a scenario for or that a previous scout run has already
judged, and writes the remaining candidates to a JSON file for the agent.
"""
import argparse
import datetime
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

import yaml

LP_API = 'https://api.launchpad.net/devel'
GH_API = 'https://api.github.com'
ALLOWED_URL_PREFIXES = (LP_API + '/', GH_API + '/')
IMPORTANCE_RANK = {'Critical': 0, 'High': 1, 'Medium': 2, 'Low': 3}
MAX_PAGES = 10
DESC_LIMIT = 3000
COMMENT_LIMIT = 800
MAX_COMMENTS = 3

COVERED_PATTERNS = (
    ('lp', re.compile(r'bug-id:\s*(\d+)')),
    ('cve', re.compile(r'cve-id:\s*(CVE-\d+-\d+)')),
    ('gh', re.compile(r'github\.com/([\w.-]+/[\w.-]+)/issues/(\d+)')),
    ('ghsa', re.compile(r'(GHSA(?:-[a-z0-9]{4}){3})')),
)


def truncate(text, limit):
    """ Truncate text to limit characters, marking that it was cut. """
    text = text or ''
    if len(text) <= limit:
        return text
    return text[:limit] + '\n[...truncated]'


class Fetcher():
    """ Minimal JSON-over-HTTPS client restricted to the known APIs. """

    def __init__(self, gh_token=None):
        self.gh_token = gh_token
        self.errors = []

    def get(self, url):
        """ GET url and decode the JSON response. """
        if not url.startswith(ALLOWED_URL_PREFIXES):
            raise ValueError(f"refusing to fetch unexpected url {url}")

        headers = {'Accept': 'application/json',
                   'User-Agent': 'hotsos-upstream-scout'}
        if url.startswith(GH_API):
            headers['Accept'] = 'application/vnd.github+json'
            if self.gh_token:
                headers['Authorization'] = f'Bearer {self.gh_token}'

        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.load(resp)

    def try_get(self, url, context):
        """ Like get() but records failures instead of raising. """
        try:
            return self.get(url)
        except (urllib.error.URLError, ValueError,
                json.JSONDecodeError) as exc:
            self.errors.append(f"{context}: {exc}")
            return None


def find_covered_keys(scenarios_dir):
    """ Return keys of bugs/CVEs already referenced by hotsos scenarios. """
    keys = set()
    for root, _, files in os.walk(scenarios_dir):
        for name in files:
            if not name.endswith('.yaml'):
                continue

            with open(os.path.join(root, name), encoding='utf-8') as fd:
                content = fd.read()

            for prefix, pattern in COVERED_PATTERNS:
                for match in pattern.finditer(content):
                    if prefix == 'gh':
                        keys.add(f'gh:{match.group(1)}#{match.group(2)}')
                    else:
                        keys.add(f'{prefix}:{match.group(1)}')

    return keys


def load_seen_keys(path):
    """ Return keys already judged by previous scout runs. """
    keys = set()
    if not path or not os.path.exists(path):
        return keys

    with open(path, encoding='utf-8') as fd:
        for line in fd:
            line = line.strip()
            if not line:
                continue
            try:
                keys.add(json.loads(line)['key'])
            except (json.JSONDecodeError, KeyError):
                continue

    return keys


class LaunchpadSource():
    """ Finds candidate bugs on Launchpad. """

    def __init__(self, fetcher, config, since):
        self.fetcher = fetcher
        self.config = config
        self.since = since

    def _search(self, target, extra_params):
        params = [('ws.op', 'searchTasks'), ('ws.size', '75'),
                  ('omit_duplicates', 'true'),
                  ('modified_since', self.since.isoformat())]
        params += [('status', s) for s in self.config['statuses']]
        params += extra_params
        url = f'{LP_API}/{target}?{urllib.parse.urlencode(params)}'
        pages = 0
        while url and pages < MAX_PAGES:
            data = self.fetcher.try_get(url, f'launchpad {target}')
            if not data:
                return
            yield from data.get('entries', [])
            url = data.get('next_collection_link')
            pages += 1

    def find(self):
        """ Return {key: summary} for matching bug tasks. """
        found = {}
        queries = [
            [('importance', i) for i in self.config['importances']],
            [('tags', t) for t in self.config['tags']] +
            [('tags_combinator', 'Any')],
        ]
        for target, plugin in self.config['targets'].items():
            for extra in queries:
                for task in self._search(target, extra):
                    bug_id = task['bug_link'].rstrip('/').rsplit('/', 1)[-1]
                    key = f'lp:{bug_id}'
                    entry = found.setdefault(key, {
                        'key': key,
                        'source': 'launchpad',
                        'bug_id': int(bug_id),
                        'plugin': plugin,
                        'bug_link': task['bug_link'],
                        'importance': task['importance'],
                        'matched_targets': [],
                    })
                    if target not in entry['matched_targets']:
                        entry['matched_targets'].append(target)
                    if (IMPORTANCE_RANK.get(task['importance'], 9) <
                            IMPORTANCE_RANK.get(entry['importance'], 9)):
                        entry['importance'] = task['importance']

        return found

    def enrich(self, entry):
        """ Add bug details, affected series tasks and first comments. """
        bug = self.fetcher.try_get(entry['bug_link'],
                                   f"launchpad bug {entry['bug_id']}")
        if not bug:
            return entry

        entry.update({
            'url': bug['web_link'],
            'title': bug['title'],
            'description': truncate(bug.get('description'), DESC_LIMIT),
            'tags': bug.get('tags', []),
            'date_last_updated': bug.get('date_last_updated'),
        })
        tasks = self.fetcher.try_get(bug['bug_tasks_collection_link'],
                                     f"launchpad tasks {entry['bug_id']}")
        entry['tasks'] = [{'target': t['bug_target_name'],
                           'status': t['status'],
                           'importance': t['importance']}
                          for t in (tasks or {}).get('entries', [])]
        msgs_url = (f"{bug['messages_collection_link']}?ws.size="
                    f"{MAX_COMMENTS + 1}")
        msgs = self.fetcher.try_get(msgs_url,
                                    f"launchpad comments {entry['bug_id']}")
        # First message is always the bug description.
        entry['comments'] = [truncate(m.get('content'), COMMENT_LIMIT)
                             for m in (msgs or {}).get('entries', [])[1:]]
        del entry['bug_link']
        return entry


class GitHubIssueSource():
    """ Finds fixed bug issues on GitHub. """

    def __init__(self, fetcher, config, since):
        self.fetcher = fetcher
        self.config = config
        self.since = since

    def find(self):
        """ Return {key: summary} for closed-as-fixed bug issues. """
        found = {}
        for repo_cfg in self.config:
            repo = repo_cfg['repo']
            query = (f"repo:{repo} is:issue is:closed reason:completed "
                     f"closed:>={self.since.date().isoformat()}")
            query += ''.join(f' label:"{label}"'
                             for label in repo_cfg.get('labels', []))
            for page in range(1, 4):
                params = urllib.parse.urlencode({'q': query, 'per_page': 100,
                                                 'page': page})
                data = self.fetcher.try_get(f'{GH_API}/search/issues?{params}',
                                            f'github issues {repo}')
                items = (data or {}).get('items', [])
                for item in items:
                    key = f"gh:{repo}#{item['number']}"
                    found[key] = {
                        'key': key,
                        'source': 'github-issue',
                        'plugin': repo_cfg['plugin'],
                        'url': item['html_url'],
                        'title': item['title'],
                        'description': truncate(item.get('body'), DESC_LIMIT),
                        'labels': [lbl['name'] for lbl in item['labels']],
                        'closed_at': item.get('closed_at'),
                        'comments_url': item['comments_url'],
                    }
                if len(items) < 100:
                    break

        return found

    def enrich(self, entry):
        """ Add the first few issue comments. """
        comments = self.fetcher.try_get(
            f"{entry.pop('comments_url')}?per_page={MAX_COMMENTS}",
            f"github comments {entry['key']}")
        entry['comments'] = [truncate(c.get('body'), COMMENT_LIMIT)
                             for c in (comments or [])]
        return entry


class GitHubAdvisorySource():
    """ Finds published repository security advisories on GitHub. """

    def __init__(self, fetcher, config, since):
        self.fetcher = fetcher
        self.config = config
        self.since = since

    def find(self):
        """ Return {key: summary} for advisories updated in the window. """
        found = {}
        for repo_cfg in self.config:
            repo = repo_cfg['repo']
            params = urllib.parse.urlencode({'state': 'published',
                                             'sort': 'updated',
                                             'direction': 'desc',
                                             'per_page': 100})
            data = self.fetcher.try_get(
                f'{GH_API}/repos/{repo}/security-advisories?{params}',
                f'github advisories {repo}')
            for adv in data or []:
                updated = datetime.datetime.fromisoformat(
                    adv['updated_at'].replace('Z', '+00:00'))
                if updated < self.since:
                    continue

                key = (f"cve:{adv['cve_id']}" if adv.get('cve_id')
                       else f"ghsa:{adv['ghsa_id']}")
                found[key] = {
                    'key': key,
                    'source': 'github-advisory',
                    'plugin': repo_cfg['plugin'],
                    'url': adv['html_url'],
                    'ghsa_id': adv['ghsa_id'],
                    'cve_id': adv.get('cve_id'),
                    'title': adv['summary'],
                    'severity': adv.get('severity'),
                    'description': truncate(adv.get('description'),
                                            DESC_LIMIT),
                    'vulnerabilities': [
                        {'package': (v.get('package') or {}).get('name'),
                         'vulnerable_version_range':
                             v.get('vulnerable_version_range'),
                         'patched_versions': v.get('patched_versions')}
                        for v in adv.get('vulnerabilities') or []],
                    'updated_at': adv['updated_at'],
                }

        return found

    @staticmethod
    def enrich(entry):
        """ Advisories are complete as listed. """
        return entry


def priority(entry):
    """ Advisories first, then Launchpad by importance (newest first), then
    GitHub issues. """
    order = {'github-advisory': 0, 'launchpad': 1, 'github-issue': 2}
    return (order[entry['source']],
            IMPORTANCE_RANK.get(entry.get('importance'), 9),
            -entry.get('bug_id', 0),
            entry['key'])


def is_excluded(entry, excluded):
    """ True if the entry (or its GHSA alias) is in the excluded keys. """
    if entry['key'] in excluded:
        return True
    return bool(entry.get('ghsa_id') and
                f"ghsa:{entry['ghsa_id']}" in excluded)


def partition(sources, covered, seen):
    """ Split everything found into new matches and excluded keys. """
    matched = {}
    stats = {'matched': {}, 'excluded_covered': [], 'excluded_seen': []}
    for name, source in sources.items():
        found = source.find()
        stats['matched'][name] = len(found)
        for key, entry in found.items():
            if is_excluded(entry, covered):
                stats['excluded_covered'].append(key)
            elif is_excluded(entry, seen):
                stats['excluded_seen'].append(key)
            else:
                matched[key] = entry

    return matched, stats


def select(sources, matched, max_candidates, exclude_tags):
    """ Enrich the highest priority matches up to max_candidates. """
    ordered = sorted(matched.values(), key=priority)
    candidates = []
    excluded_by_tag = []
    # Tags are only known after enrichment so bound the extra fetches.
    for entry in ordered[:max_candidates * 2]:
        if len(candidates) >= max_candidates:
            break
        entry = sources[entry['source']].enrich(entry)
        if exclude_tags.intersection(entry.get('tags', [])):
            excluded_by_tag.append(entry['key'])
            continue
        candidates.append(entry)

    not_examined = len(ordered) - len(candidates) - len(excluded_by_tag)
    return candidates, excluded_by_tag, not_examined


def parse_args():
    """ Parse command line arguments. """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default='.github/aw/upstream-scout.yaml')
    parser.add_argument('--scenarios', default='hotsos/defs/scenarios')
    parser.add_argument('--seen', help='jsonl file of previously judged keys')
    parser.add_argument('--lookback-days', type=int)
    parser.add_argument('--max-candidates', type=int)
    parser.add_argument('--out', default='-')
    return parser.parse_args()


def write_output(result, out):
    """ Write result as JSON to out, or stdout if out is '-'. """
    output = json.dumps(result, indent=2) + '\n'
    if out == '-':
        sys.stdout.write(output)
        return

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, 'w', encoding='utf-8') as fd:
        fd.write(output)


def main():
    """ Collect candidates and write them out. """
    args = parse_args()
    with open(args.config, encoding='utf-8') as fd:
        config = yaml.safe_load(fd)

    lookback = args.lookback_days or config['defaults']['lookback_days']
    max_candidates = (args.max_candidates or
                      config['defaults']['max_candidates'])
    since = (datetime.datetime.now(datetime.timezone.utc) -
             datetime.timedelta(days=lookback))

    fetcher = Fetcher(os.environ.get('GITHUB_TOKEN') or
                      os.environ.get('GH_TOKEN'))
    sources = {
        'launchpad': LaunchpadSource(fetcher, config['launchpad'], since),
        'github-issue': GitHubIssueSource(fetcher,
                                          config['github']['issues'], since),
        'github-advisory': GitHubAdvisorySource(
            fetcher, config['github']['advisories'], since),
    }
    matched, stats = partition(sources,
                               find_covered_keys(args.scenarios),
                               load_seen_keys(args.seen))
    candidates, excluded_by_tag, not_examined = select(
        sources, matched, max_candidates,
        set(config['launchpad'].get('exclude_tags', [])))

    write_output({
        'generated_at': datetime.datetime.now(
            datetime.timezone.utc).isoformat(),
        'since': since.isoformat(),
        'summary': {
            'matched_per_source': stats['matched'],
            'excluded_already_covered_by_scenarios':
                sorted(stats['excluded_covered']) or 'none',
            'excluded_already_judged_by_scout':
                len(stats['excluded_seen']),
            'excluded_by_tag': excluded_by_tag or 'none',
            'candidates_emitted': len(candidates),
            'candidates_not_examined_over_limit': not_examined,
            'fetch_errors': fetcher.errors or 'none',
        },
        'candidates': candidates,
    }, args.out)


if __name__ == '__main__':
    main()
