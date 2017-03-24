import sopel.module
import requests
import json

REVIEW_SERVER = 'https://review.openstack.org'
KNOWN_BOTS = set([
    'openstack',
    'openstackgerrit',
    'openstackstatus',
])

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
    return ' - '.join(pieces)

#TODO: be able to mix the forms
#      maybe have a general .* regex and do our own parsing a la Patches v1?
@sopel.module.rule(r'https://review.openstack.org(?:/#/c)?/(\d+)/?')
@sopel.module.rule(r'.*?(?:p(?:atch)?\s+){1}#?(\d+).*?')
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
