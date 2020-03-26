import re
import itertools
import subprocess
import os
import argparse
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
DEFAFULT_CONFIG_FILE = '.sirem'
requests.warnings.filterwarnings('ignore')


def get_jira(options):
    return JIRA(options.jira_baseurl, basic_auth=(options.jira_username, options.jira_password))

def issue_to_dict(issue):
    return {
            'ref': issue.key,
            'summary': issue.fields.summary,
            'priority': issue.fields.priority.name
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

def func_import_scope(options):
    jira_version = options.jira_version_template.format(version=options.version)
    logging.debug('jira_version = %s', jira_version)
    jql = 'fixVersion = "{jira_version}" and ({jql})'.format(jira_version=jira_version, jql=options.jql)
    logging.debug('jql = %s', jql)
    issues = get_all_tickets_for_filter(options, jql)
    logging.debug('got %d issues: %s', len(issues), str([x.key for x in issues]))
    current_versions = options.current_context['versions']
    version = next(version for version in options.versions.values() if version.tag == options.version)
    if not version:
        sys.stderr.write('ERROR: Version %s not found in %s.\n' % (options.version, options.versions_file))
        sys.exit(EXIT_CODE_VERSION_NOT_FOUND)
    version['scoping_date'] = datetime.now().strftime('%Y-%m-%d')
    version['scope'] = [issue_to_dict(x) for x in issues]
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
        if jira_version_content.raw.get('description') != version.description:
            logging.debug('updating description of version %s from "%s" to "%s"', version.tag, jira_version_content.raw.get('description'), version.description)
            if not options.dry_run:
                jira_version_content.update(description=version.description)
        if to_date(jira_version_content.raw.get('releaseDate')) != version.release_date:
            logging.debug('updating releaseDate of version %s from %s to %s', version.tag, jira_version_content.raw.get('releaseDate'), version.release_date)
            if not options.dry_run:
                jira_version_content.update(releaseDate=version.release_date.strftime(TIME_PATTERN))

def get_all_tickets_for_filter(options, jql):
    jira = get_jira(options)
    issues = jira.search_issues(jql, maxResults=1000, fields='summary,priority')
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

def parse_arguments():
    parser = argparse.ArgumentParser(fromfile_prefix_chars='@')
    parser.add_argument('-f', '--versions-file', help='path of versions file. defaults to VERSIONS.yaml', default='VERSIONS.yaml')
    parser.add_argument('-v', '--verbose', help='debug level set to DEBUG', action='store_true')

    subparsers = parser.add_subparsers(dest='command', required=True)
    jira_parser = subparsers.add_parser('jira')
    jira_parser.add_argument('--jira-baseurl', help='base url of the jira instance')
    jira_parser.add_argument('--jira-username', help='jira username to use')
    jira_parser.add_argument('--jira-password', help='jira password to use')
    jira_parser.add_argument('--jira-project', help='jira password to use')
    jira_parser.add_argument('--jql', help='jql to use to get issues', default='issuetype != sub-task')
    jira_parser.add_argument('--jira-version-template', help='template to create versions in Jira. use {version} to indicate the original version tag. For example, if the template is "Release {version}", then the version "v1.0.0" will be called "Release v1.0.0" in Jira', default='{version}')
    jira_subparser = jira_parser.add_subparsers(dest='jira_sub_command', required=True)
    parser_import_scope = jira_subparser.add_parser('import-scope', help='contact jira to find the scope of a version, then populate the `scope` and `scoping date` fields of that version')
    parser_import_scope.add_argument('version', help='the version to import')
    parser_import_scope.set_defaults(func=func_import_scope)

    parser_sync_jira = jira_subparser.add_parser('sync', help='update jira versions according to the versions file')
    parser_sync_jira.add_argument('-n', '--dry-run', help='just print the actions, dont execute them', action='store_true')
    parser_sync_jira.set_defaults(func=func_sync_jira)

    versions_parser = subparsers.add_parser('versions')
    versions_subparser = versions_parser.add_subparsers(dest='versions_sub_command', required=True)

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

    parser_versions_set_description = versions_subparser.add_parser('remove-milestone', help='remove milestone from version')
    parser_versions_set_description.add_argument('tag')
    parser_versions_set_description.add_argument('--description', required=True)
    parser_versions_set_description.set_defaults(func=func_set_description)

    report_parser = subparsers.add_parser('report')
    report_parser.add_argument('tag', nargs='?')
    report_parser.add_argument('--format', choices=['yaml', 'html'], default='html')
    report_parser.add_argument('--content-regex', default='^.*$')
    report_parser.set_defaults(func=func_report)

    options = parser.parse_args((['@' + DEFAFULT_CONFIG_FILE] if os.path.isfile(DEFAFULT_CONFIG_FILE) else []) + sys.argv[1:])
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
    status = {'tag': tag,
              'milestones': version.get_milestones(),
              'scope': version.scope}
    tags = get_tags(tag)
    release_tag = next((x for x in tags if x['tag'] == tag), None)
    status['released'] = any(x for x in tags if tag == x['tag'])
    release_candidates_tags = [x for x in tags if re.match('^.*-rc.([0-9]*)$', x['tag'])]
    for x in release_candidates_tags:
        x['release_candidate_number'] = re.match('^.*-rc.([0-9]*)$', x['tag']).groups()[0]
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


HTML_TEMPLATE = Template(open(os.path.join(os.path.dirname(__file__), 'report.template.html')).read())

def get_status(options):
    if options.tag:
        return [get_version_status(options, options.tag, options.versions[options.tag])]
    else:
        return [get_version_status(options, x.tag, x) for x in options.versions.values()]

def func_report(options):
    status = get_status(options)
    if options.format == 'yaml':
        yaml.dump(status, sys.stdout)
    elif options.format == 'html':
        sys.stdout.write(HTML_TEMPLATE.render(status=status))

def main():
    options = parse_arguments()
    logging.basicConfig(stream=sys.stdout,
                        format='%(asctime)s | %(levelname)-8.8s | %(filename)s | %(process)d | %(message).10000s',
                        datefmt='%Y/%m/%d %H:%M:%S',
                        level=logging.DEBUG if options.verbose else logging.INFO)
    logging.getLogger('urllib3').setLevel(logging.INFO)
    logging.debug('got options:')
    logging.debug(options)
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
        return to_date(self.get_milestones().get('release'))

    @release_date.setter
    def release_date(self, value):
        if not value and 'release' in self.get_milestones():
            self.remove_milestone('release')
        else:
            self.set_milestone('release', value)

    @property
    def scope(self):
        return self._raw.get('scope', [])

    def get_milestones(self):
        return {x: to_date(y) for x, y in self._raw.get('milestones', {}).items()}

    def set_milestone(self, milestone, date):
        self._raw.setdefault('milestones', {})[milestone] = date.strftime(TIME_PATTERN)

    def remove_milestone(self, milestone):
        del self._raw['milestones'][milestone]

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
