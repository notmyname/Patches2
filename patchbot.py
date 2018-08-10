import sopel.module
import requests
import json
import re

REVIEW_SERVER = 'https://review.openstack.org'
KNOWN_BOTS = set([
    'openstack',
    'openstackgerrit',
    'openstackstatus',
])


lr_regex = re.compile(r'^.* in (?:(\d+)h )?(?:(\d+)m )?(\d+)s$')


def tim_time_calc(patch_number):

    def hms_to_i(h, m, s):
        return int(s or '0') + 60 * (int(m or '0') + 60 * int(h or '0'))

    def i_to_hms(i):
        m, s = divmod(i, 60)
        h, m = divmod(m, 60)
        return h, m, s

    c = requests.get('https://review.openstack.org/changes/%s/detail' % patch_number).content
    d = json.loads(c[4:])
    m = [(x['date'], x['message']) for x in d['messages']
         if x.get('author', {}).get('username') in ('zuul', 'jenkins')]
    total_cpu = 0
    total_real = 0
    for d, m in m:
        run_total = 0
        max_for_run = 0
        for l in m.split('\n'):
            lm = lr_regex.match(l)
            if not lm:
                continue
            t = hms_to_i(*lm.groups())
            run_total += t
            if t > max_for_run:
                max_for_run = t
        if not run_total:
            continue
        total_cpu += run_total
        total_real += max_for_run
    return i_to_hms(total_cpu), i_to_hms(total_real)

#TODO: memoize this
def _get_data(patch_number):
    resp = requests.get('%s/changes/%d' % (REVIEW_SERVER, patch_number),
                        headers={'Accept': 'application/json'},
                        stream=True)
    if resp.status_code != 200:
        return None  # Error; patch does not exist?

    if int(resp.headers.get('Content-Length', '1024')) >= 1024:
        return None  # Response too long; this should be real small

    lines = resp.iter_lines()
    next(lines)  # Throw out )]}' line
    try:
        data = json.loads(b''.join(lines))
        return data
    except (ValueError, TypeError, KeyError):
        # Bad JSON, JSON not a hash, or hash doesn't have "subject"
        return None

def get_response(patch_number, already_linked=True):
    data = _get_data(patch_number)
    if not data:
        return 'No data found for patch %d' % patch_number
    pieces = []
    if already_linked:
        pieces.append('patch %d' % patch_number)
    else:
        pieces.append('%s/#/c/%d/' % (REVIEW_SERVER, patch_number))

    project = data.get('project')
    if project:
        if project.startswith('openstack/'):
            project = project[10:]
        branch = data.get('branch', 'master')

        if branch == 'master':
            pieces.append(project)
        else:
            pieces.append('%s (%s)' % (project, branch))

    subject = data.get('subject')
    if subject:
        if len(subject) > 53:
            subject = subject[:50] + '...'
        status = data.get('status', 'NEW')

        if status == 'NEW':
            pieces.append(subject)
        else:
            pieces.append('%s (%s)' % (subject, status))
    cpu_time, wall_time = tim_time_calc(patch_number)
    if any(cpu_time + wall_time):
        # time_message = '%2dh %2dm %2ds cpu' % cpu_time
        # pieces.append(time_message)
        time_message = '%dh %dm %ds spent in CI' % wall_time
        pieces.append(time_message)
    return ' - '.join(pieces)

#TODO: be able to mix the forms
#      maybe have a general .* regex and do our own parsing a la Patches v1?
@sopel.module.rule(r'.*?https://review.openstack.org(?:/#/c)?/(\d+)/?.*?')
@sopel.module.rule(r'(?:.*?\s+?)??(?:p(?:atch)?\s+){1}#?(\d+).*?')
def linkify_patches(bot, trigger):
    if trigger.nick in KNOWN_BOTS:
        return
    try:
        #TODO: somehow not do this?
        patch_numbers = [int(x) for x in trigger.match.re.findall(trigger.args[1])]
    except TypeError:
        return

    for patch_number in patch_numbers:
        resp = get_response(patch_number, already_linked=(REVIEW_SERVER in trigger.match.string))
        if resp:
            bot.say(resp)


@sopel.module.rule(r'#startmeeting infra')
def bail_on_infra_meeting(bot, trigger):
    if 'meeting' in trigger.sender or trigger.sender == '#clouddevs':
        bot.part(trigger.sender, msg="I am leaving. No need to kick me out.")
