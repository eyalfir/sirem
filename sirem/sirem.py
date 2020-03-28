import re
import pypandoc
import random
from functools import partial
import argparse
import itertools
import subprocess
import os
import configargparse
import logging
import sys
from datetime import datetime, date
from jira import JIRA
import requests
import yaml
from jinja2 import Template

EXIT_CODE_VERSION_NOT_FOUND = 1
EXIT_CODE_BAD_VERSION_FILE = 2
EXIT_CODE_VERSION_EXIST = 3
TIME_PATTERN = '%Y-%m-%d'
requests.warnings.filterwarnings('ignore')


def get_jira(options):
    return JIRA(options.jira_baseurl, basic_auth=(options.jira_username, options.jira_password))

def jira_issue_to_dict(issue):
    return {
            'ref': issue.key,
            'summary': issue.fields.summary,
            'labels': ['type:' + issue.fields.issuetype.name, 'priority:' + issue.fields.priority.name]
            }
def func_set_description(options):
    version = options.versions[options.tag]
    version.description = options.description
    dump(options)

def func_set_milestone(options):
    version = options.versions[options.tag]
    version.set_milestone(options.milestone, to_date(options.date))
    dump(options)

def func_remove_milestone(options):
    version = options.versions[options.tag]
    version.remove_milestone(options.milestone)
    dump(options)

ALL_EMOJIS=['sushi', 'rice', 'cookie', 'grapes', 'peach', 'pear', 'banana', 'cherries', 'watermelon', 'pizza', 'beer', 'cake', 'egg', 'green_apple', 'apple', 'icecream', 'meat_on_bone', 'hamburger', 'poultry_leg', 'dango', 'doughnut', 'ice_cream', 'birthday', 'candy', 'lollipop', 'lemon']
def label_to_emoji(label, current_mapping={}, free_emojis=ALL_EMOJIS):
    if label in current_mapping:
        emoji = current_mapping[label]
    else:
        emoji = random.choice(free_emojis)
        free_emojis.remove(emoji)
        current_mapping[label] = emoji
    return ':' + emoji + ':' + label

def func_import_scope(options):
    jira_version = options.jira_version_template.format(version=options.version)
    logging.debug('jira_version = %s', jira_version)
    jql = 'fixVersion = "{jira_version}" and ({jql})'.format(jira_version=jira_version, jql=options.jql)
    logging.debug('jql = %s', jql)
    issues = get_all_tickets_for_filter(options, jql)
    logging.debug('got %d issues: %s', len(issues), str([x.key for x in issues]))
    current_versions = options.current_context['versions']
    if options.version not in options.versions:
        sys.stderr.write('ERROR: Version %s not found in %s.\n' % (options.version, options.versions_file))
        sys.exit(EXIT_CODE_VERSION_NOT_FOUND)
    version = options.versions[options.version]
    if options.milestone not in version.get_milestones():
        version.set_milestone(options.milestone, datetime.now().date())
    scope_entries = [jira_issue_to_dict(x) for x in issues]
    version.get_milestones()[options.milestone].scope = scope_entries
    dump(options)

def dump(options):
    yaml.dump(options.current_context, open(options.versions_file, 'w'), sort_keys=True, default_flow_style=False)

def func_sync_jira(options):
    jira = get_jira(options)
    jira_versions_list = jira.project(options.jira_project).versions
    jira_versions = {x.name: x for x in jira_versions_list}
    for version in options.versions.values():
        jira_version = options.jira_version_template.format(version=version.tag)
        if jira_version not in jira_versions:
            logging.debug('adding version %s', version.tag)
            if not options.dry_run:
                jira.create_version(project=options.jira_project, name=jira_version, description=version.description, releaseDate=version.release_date)
            continue
        jira_version_content = jira_versions[jira_version]
        if re.sub('^None$', '', jira_version_content.raw.get('description', '')) != version.description:
            logging.debug('updating description of version %s from "%s" to "%s"', version.tag, jira_version_content.raw.get('description'), version.description)
            if not options.dry_run:
                jira_version_content.update(description=version.description)
        if to_date(jira_version_content.raw.get('releaseDate')) != version.release_date:
            logging.debug('updating releaseDate of version %s from %s to %s', version.tag, jira_version_content.raw.get('releaseDate'), version.release_date)
            if not options.dry_run:
                jira_version_content.update(releaseDate=version.release_date.strftime(TIME_PATTERN))

def get_all_tickets_for_filter(options, jql):
    jira = get_jira(options)
    issues = jira.search_issues(jql, maxResults=1000, fields='summary,issuetype,priority')
    return issues

def func_create_version(options):
    if options.tag in options.versions:
        logging.error('version %s already exists', options.tag)
        sys.exit(EXIT_CODE_VERSION_EXIST)
    version = {'tag': options.tag}
    if options.description:
        version['description'] = options.description
    if options.release_date:
        version['milestones'] = {'release': options.release_date}
    options.current_context['versions'].append(version)
    dump(options)

def func_reorder_version(options):
    try:
        entry = next(i for i, x in enumerate(options.current_context['versions']) if x['tag'] == options.tag)
    except StopIteration:
        logging.error('no entry found with tag %s', options.tag)
        sys.exit(EXIT_CODE_VERSION_NOT_FOUND)
    versions = options.current_context['versions']
    moving_version = versions[entry]
    new_versions = versions[:entry] + versions[entry + 1:]
    new_versions.insert(entry + int(options.places), moving_version)
    options.current_context['versions'] = new_versions
    dump(options)

def func_remove_version(options):
    try:
        entry = next(x for x in options.current_context['versions'] if x['tag'] == options.tag)
    except StopIteration:
        logging.error('no entry found with tag %s', options.tag)
        sys.exit(EXIT_CODE_VERSION_NOT_FOUND)
    options.current_context['versions'].remove(entry)
    dump(options)

def valid_date(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        msg = "Not a valid date: '{0}'.".format(s)
        raise argparse.ArgumentTypeError(msg)

def dir_route(path):
    up = os.path.realpath(os.path.join(path, '..'))
    if up == os.path.realpath(path):
        return []
    else:
        return dir_route(up) + [path]

def func_list_versions(options):
    print('\n'.join(x for x in options.versions.keys()))

def parse_arguments():
    config_files = [os.path.join(x, '.sirem') for x in dir_route(os.getcwd())]
    parser = configargparse.ArgParser(default_config_files=[os.path.join(os.environ['HOME'], '.sirem')] + config_files)
    parser.add_argument('-c', '--config', is_config_file=True, help='config file path')
    parser.add_argument('-f', '--versions-file', help='path of versions file. defaults to VERSIONS.yaml', default='VERSIONS.yaml')
    parser.add_argument('-v', '--verbose', help='debug level set to DEBUG', action='store_true')
    parser.add_argument('--jira-baseurl', help='base url of the jira instance')
    parser.add_argument('--jira-username', help='jira username to use')
    parser.add_argument('--jira-password', help='jira password to use')
    parser.add_argument('--jira-project', help='jira password to use')
    parser.add_argument('--content-regex', default='^.*$')
    parser.add_argument('--jql', help='jql to use to get issues', default='issuetype != sub-task')
    parser.add_argument('--jira-version-template', help='template to create versions in Jira. use {version} to indicate the original version tag. For example, if the template is "Release {version}", then the version "v1.0.0" will be called "Release v1.0.0" in Jira', default='{version}')

    subparsers = parser.add_subparsers(dest='command', required=True)
    jira_parser = subparsers.add_parser('jira')
    jira_subparser = jira_parser.add_subparsers(dest='jira_sub_command', required=True)
    parser_import_scope = jira_subparser.add_parser('import-scope', help='contact jira to find the scope of a version, then populate the `scope` of a milestone')
    parser_import_scope.add_argument('version', help='the version to import')
    parser_import_scope.add_argument('milestone', help='the milestone associated with the imported scope')
    parser_import_scope.set_defaults(func=func_import_scope)

    parser_sync_jira = jira_subparser.add_parser('sync', help='update jira versions according to the versions file')
    parser_sync_jira.add_argument('-n', '--dry-run', help='just print the actions, dont execute them', action='store_true')
    parser_sync_jira.set_defaults(func=func_sync_jira)

    versions_parser = subparsers.add_parser('versions')
    versions_subparser = versions_parser.add_subparsers(dest='versions_sub_command', required=True)

    parser_versions_create = versions_subparser.add_parser('list', help='list versions')
    parser_versions_create.set_defaults(func=func_list_versions)

    parser_versions_create = versions_subparser.add_parser('create', help='create new version')
    parser_versions_create.add_argument('tag')
    parser_versions_create.add_argument('--release-date', type=valid_date)
    parser_versions_create.add_argument('--description')
    parser_versions_create.set_defaults(func=func_create_version)

    parser_versions_remove = versions_subparser.add_parser('remove', help='remove version')
    parser_versions_remove.add_argument('tag')
    parser_versions_remove.set_defaults(func=func_remove_version)

    parser_versions_set_milestone = versions_subparser.add_parser('set-milestone', help='create new milestone for version')
    parser_versions_set_milestone.add_argument('tag')
    parser_versions_set_milestone.add_argument('milestone')
    parser_versions_set_milestone.add_argument('date')
    parser_versions_set_milestone.set_defaults(func=func_set_milestone)

    parser_versions_remove_milestone = versions_subparser.add_parser('remove-milestone', help='remove milestone from version')
    parser_versions_remove_milestone.add_argument('tag')
    parser_versions_remove_milestone.add_argument('milestone')
    parser_versions_remove_milestone.set_defaults(func=func_remove_milestone)

    parser_versions_set_description = versions_subparser.add_parser('set-description', help='set description of a versino')
    parser_versions_set_description.add_argument('tag')
    parser_versions_set_description.add_argument('--description', required=True)
    parser_versions_set_description.set_defaults(func=func_set_description)

    parser_versions_set_reorder = versions_subparser.add_parser('reorder', help='move vesion up or down')
    parser_versions_set_reorder.add_argument('tag')
    parser_versions_set_reorder.add_argument('places', help='how many places to move down (positive number) or up (negative number)')
    parser_versions_set_reorder.set_defaults(func=func_reorder_version)

    report_parser = subparsers.add_parser('report')
    report_parser.add_argument('tag', nargs='?')
    report_parser.add_argument('--format', choices=['yaml', 'html', 'markdown'], default='html')
    report_parser.set_defaults(func=func_report)

    options = parser.parse_args(sys.argv[1:])
    return options


def get_tags(prefix):
    out, err = subprocess.Popen(['git', 'for-each-ref', '--format=%(refname:short);%(taggerdate:short)%(committerdate:short)', 'refs/tags/%s*' % prefix], stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
    return [{"tag": x.split(';')[0], "date": datetime.strptime(x.split(';')[1], TIME_PATTERN).date()} for x in out.decode('UTF-8').splitlines()]

def get_commit(tag):
    return subprocess.Popen(['git', 'log', tag, '-1', '--format="%H"'], stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()[0].decode('UTF-8')

def get_diff(previous_ref, current_ref):
    out, err = subprocess.Popen(['git', 'log', '{t1}..{t2}'.format(t1=previous_ref, t2=current_ref), '--format=%s'], stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
    lines = [x for x in out.decode('UTF-8').splitlines()]
    return lines

    

def get_version_status(options, tag, version):
    status = {'tag': tag}
    ms = version._raw.get('milestones', {})
    milestones = [dict(name=name, **x) for name, x in ms.items()]
    sorted_milestones = sorted(milestones, key=lambda x: datetime.strptime(x['date'], TIME_PATTERN))
    status['milestones'] = sorted_milestones
    tags = get_tags(tag)
    release_tag = next((x for x in tags if x['tag'] == tag), None)
    status['released'] = any(x for x in tags if tag == x['tag'])
    release_candidates_tags = [x for x in tags if re.match('^.*-rc.([0-9]*)$', x['tag'])]
    scope_status = {}
    for ms in reversed(milestones):
        for content in ms['scope']:
            scope_status.setdefault(content['ref'], {'ref': content['ref'], 'summary': content['summary'], 'labels': content['labels'], 'milestones': []})
            scope_status[content['ref']]['milestones'].append(ms['name'])
    status['scope_status'] = list(scope_status.values())
    for x in release_candidates_tags:
        x['release_candidate_number'] = int(re.match('^.*-rc.([0-9]*)$', x['tag']).groups()[0])
        x['status'] = 'rejected'
    if not release_candidates_tags:
        return status
    release_candidates_tags.sort(key=lambda x: x['release_candidate_number'])
    if release_tag:
        if get_commit(release_candidates_tags[-1]['tag']) == get_commit(release_tag['tag']):
            release_candidates_tags[-1]['status'] = 'approved'
        else:
            release_candidates_tags[-1]['status'] = 'rejected'
    else:
        release_candidates_tags[-1]['status'] = 'pending'
    status['release_candidates'] = release_candidates_tags
    for i in range(1, len(release_candidates_tags)):
        release_candidates_tags[i]['commits'] = get_diff(release_candidates_tags[i - 1]['tag'], release_candidates_tags[i]['tag'])
        release_candidates_tags[i]['content'] = list(set(itertools.chain(*[re.findall(options.content_regex, x) for x in release_candidates_tags[i]['commits']])))

    return status


MARKDOWN_TEMPLATE = Template(open(os.path.join(os.path.dirname(__file__), 'report.template.md')).read())

def get_status(options):
    if options.tag:
        return [get_version_status(options, options.tag, options.versions[options.tag])]
    else:
        return [get_version_status(options, x.tag, x) for x in options.versions.values()]

def content_link(ref, options):
    if options.jira_baseurl:
        return '[{ref}]({jira}/browse/{ref})'.format(jira=options.jira_baseurl.rstrip('/'), ref=ref)
    else:
        return ref

def func_report(options):
    status = get_status(options)
    if options.format == 'yaml':
        yaml.dump(status, sys.stdout)
    elif options.format in {'markdown', 'html'}:
        markdown = MARKDOWN_TEMPLATE.render(status=status, options=options, content_link=content_link, partial=partial, map=map, label_to_emoji=label_to_emoji)
        if options.format == 'markdown':
            sys.stdout.write(markdown)
        elif options.format == 'html':
            html = pypandoc.convert_text(source=markdown, to='html', format='gfm', extra_args=('--include-in-header=' + os.path.realpath(os.path.join(os.path.dirname(__file__), 'github-pandoc.css')),))
            sys.stdout.write(html)

def main():
    options = parse_arguments()
    logging.basicConfig(stream=sys.stdout,
                        format='%(asctime)s | %(levelname)-8.8s | %(filename)s | %(process)d | %(message).10000s',
                        datefmt='%Y/%m/%d %H:%M:%S',
                        level=logging.DEBUG if options.verbose else logging.INFO)
    logging.getLogger('urllib3').setLevel(logging.INFO)
    logging.debug('got options:')
    logging.debug(options)
    if not os.path.isfile(options.versions_file):
        logging.debug('creating versions file %s', options.versions_file)
        yaml.dump({'versions': []}, open(options.versions_file, 'w'))
    options.current_context = yaml.load(open(options.versions_file))
    options.versions = load_versions(options.current_context['versions'])
    options.func(options)

class Version:

    def __init__(self, raw_entry):
        self.tag = raw_entry['tag']
        self._raw = raw_entry
        try:
            self.get_milestones()
        except Exception:
            logging.exception('cannot parse version entry for %s', raw_entry['tag'])
            sys.exit(EXIT_CODE_BAD_VERSION_FILE)

    @property
    def description(self):
        return self._raw.get('description', '')

    @description.setter
    def description(self, value):
        self._raw['description'] = value

    @property
    def release_date(self):
        if 'release' not in self.get_milestones():
            return None
        else:
            return self.get_milestones()['release'].date

    @release_date.setter
    def release_date(self, value):
        if not value and 'release' in self.get_milestones():
            self.remove_milestone('release')
        else:
            self.set_milestone('release', value)

    def get_milestones(self):
        return {name: Milestone(x) for name, x in self._raw.get('milestones', {}).items()}

    def set_milestone(self, milestone, date):
        self._raw.setdefault('milestones', {})[milestone] = {'date': date.strftime(TIME_PATTERN)}

    def remove_milestone(self, milestone):
        del self._raw['milestones'][milestone]

class Milestone:

    def __init__(self, raw_entry):
        self._raw = raw_entry

    @property
    def date(self):
        return to_date(self._raw['date'])

    @property
    def scope(self):
        return self._raw.get('scope', [])

    @scope.setter
    def scope(self, value):
        self._raw['scope'] = value

def to_date(val):
    if not val:
        return None
    elif isinstance(val, date):
        return val
    else:
        try:
            return datetime.strptime(val, TIME_PATTERN).date()
        except Exception:
            logging.exception('unable to parse %s as date', val)
            sys.exit(EXIT_CODE_BAD_VERSION_FILE)

def version_tuple_from_raw(raw_version_entry):
    try:
        tag = raw_version_entry['tag']
    except KeyError:
        logging.exception('unable to find tag for a version')
        sys.exit(EXIT_CODE_BAD_VERSION_FILE)
    version = Version(raw_version_entry)
    return (tag, version)

def load_versions(raw_versions_list):
    return dict(version_tuple_from_raw(x) for x in raw_versions_list)
