#!/usr/bin/env python3

import csv
import json
import logging
import aiohttp
import asyncio
import signal
from base64 import b64decode
from copy import deepcopy
from pathlib import Path
from yaml import safe_load, YAMLError


AWS_IAM_ENDPOINT = '{{ aws_iam_endpoint if aws_iam_endpoint }}'
KEYSTONE_ENDPOINT = '{{ keystone_endpoint if keystone_endpoint }}'
CUSTOM_AUTHN_ENDPOINT = '{{ custom_authn_endpoint if custom_authn_endpoint }}'

app = aiohttp.web.Application()
routes = aiohttp.web.RouteTableDef()

# Disable the gunicorn arbiter's SIGCHLD handler in this worker. The handler
# gets inherited by worker processes where it appears to serve no useful
# function. It also makes it impossible for workers to make subprocess calls
# safely, so, disable it.
# https://bugs.launchpad.net/charm-kubernetes-master/+bug/1938470
signal.signal(signal.SIGCHLD, signal.SIG_DFL)


async def run(*args, timeout=10, **kwargs):
    '''Run a CLI command.

    Returns retcode, stdout, and stderr (already decoded).

    If the process times out, the exit code will be 124 and stdout and stderr
    will be empty.

    NOTE:
    In Python 3.8+, the default process child watcher, ThreadedChildWatcher,
    appears to have a race condition where it frequently attempts to wait for
    the child process PID before it's visible, leading to a spurious warning
    in the log about "Unknown child process", and a 255 exit code regardless
    of what the child process actually exits with. The stdout and stderr will
    still be available, however.
    '''
    args = [str(arg) for arg in args]
    kwargs.update(
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    async def _run():
        proc = await asyncio.create_subprocess_exec(*args, **kwargs)
        stdout, stderr = await proc.communicate()
        return proc.returncode, stdout.decode('utf8'), stderr.decode('utf8')

    try:
        return await asyncio.wait_for(_run(), timeout=timeout)
    except asyncio.TimeoutError:
        app.logger.exception('Command timed out: {}'.format(' '.join(args)))
        return 124, '', ''


async def kubectl(*args):
    '''Run a kubectl CLI command with a config file.

    Returns retcode, stdout, and stderr.
    '''
    # Try to use our service account kubeconfig; fall back to root if needed
    kubectl_cmd = Path('/snap/bin/kubectl')
    if not kubectl_cmd.is_file():
        # Fall back to anywhere on the path if the snap isn't available
        kubectl_cmd = 'kubectl'
    return await run(kubectl_cmd, '--kubeconfig=/root/.kube/config', *args)


def log_secret(text, obj, hide=True):
    '''Log information about a TokenReview object.

    The message will always be logged at the 'debug' level and will be in the
    form "text: obj". By default, secrets will be hidden. Set 'hide=False' to
    have the secret printed in the output unobfuscated.
    '''
    log_obj = obj
    if obj and hide:
        log_obj = deepcopy(obj)
        try:
            log_obj['spec']['token'] = '********'
        except (KeyError, TypeError):
            # No secret here, carry on
            pass
    app.logger.debug('{}: {}'.format(text, log_obj))


async def check_token(token_review):
    '''Populate user info if token is found in auth-related files.'''
    app.logger.info('Checking token')
    token_to_check = token_review['spec']['token']

    # If we have an admin token, short-circuit all other checks. This prevents us
    # from leaking our admin token to other authn services.
    admin_kubeconfig = Path('/root/.kube/config')
    data = None
    try:
        try:
            data = safe_load(admin_kubeconfig.read_text())
        except Exception:
            # Retry loading the file once, in case the charm was in the
            # middle of rewriting it. See lp:1837930 for more info, but
            # even without it being rewritten on every hook, there will
            # always be a race condition to consider.
            await asyncio.sleep(0.5)
            data = safe_load(admin_kubeconfig.read_text())
    except YAMLError as e:
        # we don't want to use logger.exception() or str(e) because it
        # can leak tokens into the log
        app.logger.error('Invalid kube config file: %s', type(e).__name__)
    except Exception:
        if not admin_kubeconfig.exists():
            app.logger.error('Missing kube config file')
        elif data is None:
            app.logger.error('Empty kube config file')
        else:
            app.logger.exception('Invalid kube config file')
    else:
        admin_token = data['users'][0]['user']['token']
        if token_to_check == admin_token:
            # We have a valid admin
            token_review['status'] = {
                'authenticated': True,
                'user': {
                    'username': 'admin',
                    'uid': 'admin',
                    'groups': ['system:masters']
                }
            }
            return True

    # No admin? We're probably in an upgrade. Check an existing known_tokens.csv.
    csv_fields = ['token', 'username', 'user', 'groups']
    known_tokens = Path('/root/cdk/known_tokens.csv')
    try:
        with known_tokens.open('r') as f:
            data_by_token = {r['token']: r for r in csv.DictReader(f, csv_fields)}
    except FileNotFoundError:
        data_by_token = {}

    if token_to_check in data_by_token:
        record = data_by_token[token_to_check]
        # groups are optional; default to an empty string if we don't have any
        groups = record.get('groups', '').split(',')
        token_review['status'] = {
            'authenticated': True,
            'user': {
                'username': record['username'],
                'uid': record['user'],
                'groups': groups,
            }
        }
        return True
    return False


async def check_secrets(token_review):
    '''Populate user info if token is found in k8s secrets.'''
    # Only check secrets if kube-apiserver is up
    app.logger.info('Checking secret')
    token = token_review['spec']['token']

    if token in app['secrets']:
        token_review['status'] = {
            'authenticated': True,
            'user': app['secrets'][token],
        }
        return True
    else:
        return False


async def check_aws_iam(token_review):
    '''Check the request with an AWS IAM authn server.'''
    app.logger.info('Checking AWS IAM')

    # URL comes from /root/cdk/aws-iam-webhook.yaml
    app.logger.debug('Forwarding to: {}'.format(AWS_IAM_ENDPOINT))

    return await forward_request(token_review, AWS_IAM_ENDPOINT)


async def check_keystone(token_review):
    '''Check the request with a Keystone authn server.'''
    app.logger.info('Checking Keystone')

    # URL comes from /root/cdk/keystone/webhook.yaml
    app.logger.debug('Forwarding to: {}'.format(KEYSTONE_ENDPOINT))

    return await forward_request(token_review, KEYSTONE_ENDPOINT)


async def check_custom(token_review):
    '''Check the request with a user-specified authn server.'''
    app.logger.info('Checking Custom Endpoint')

    # User will set the URL in k8s-master config
    app.logger.debug('Forwarding to: {}'.format(CUSTOM_AUTHN_ENDPOINT))

    return await forward_request(token_review, CUSTOM_AUTHN_ENDPOINT)


async def forward_request(json_req, url):
    '''Forward a JSON TokenReview request to a url.

    Returns True if the request is authenticated; False if the response is
    either invalid or authn has been denied.
    '''
    timeout = 10
    resp_text = ''
    try:
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, json=json_req, timeout=timeout) as resp:
                    resp_text = await resp.text()
            except aiohttp.ClientSSLError:
                app.logger.debug('SSLError with server; skipping cert validation')
                async with session.post(url,
                                        json=json_req,
                                        verify_ssl=False,
                                        timeout=timeout) as resp:
                    resp_text = await resp.text()
    except asyncio.TimeoutError:
        app.logger.error('Timed out contacting server')
        return False
    except Exception:
        app.logger.exception('Failed to contact server')
        return False

    # Check if the response is valid
    try:
        resp = json.loads(resp_text)
        'authenticated' in resp['status']
    except (KeyError, TypeError, ValueError):
        log_secret(text='Invalid response from server', obj=resp_text)
        return False

    # NB: When a forwarded request is authenticated, set the 'status' field to
    # whatever the external server sends us. This ensures any status fields that
    # the server wants to send makes it back to the kube apiserver.
    if resp['status']['authenticated']:
        json_req['status'] = resp['status']
        return True
    return False


def ack(req, **kwargs):
    # Successful checks will set auth and user data in the 'req' dict
    log_secret(text='ACK', obj=req)
    return aiohttp.web.json_response(req, **kwargs)


def nak(req, **kwargs):
    # Force unauthenticated, just in case
    req.setdefault('status', {})['authenticated'] = False
    log_secret(text='NAK', obj=req)
    return aiohttp.web.json_response(req, **kwargs)


@routes.post('/{{ api_ver }}')
async def webhook(request):
    '''Listen on /$api_version for POST requests.

    For a POSTed TokenReview object, check every known authentication mechanism
    for a user with a matching token.

    The /$api_version is expected to be the api version of the authentication.k8s.io
    TokenReview that the k8s-apiserver will be sending.

    Returns:
        TokenReview object with 'authenticated: True' and user attributes if a
        token is found; otherwise, a TokenReview object with 'authenticated: False'
    '''
    try:
        req = await request.json()
    except json.JSONDecodeError:
        app.logger.debug('Unable to parse request')
        return nak({}, status=400)

    # Make the request unauthenticated by deafult
    req['status'] = {'authenticated': False}

    try:
        valid = True if (req['kind'] == 'TokenReview' and
                         req['spec']['token']) else False
    except (KeyError, TypeError):
        valid = False

    if valid:
        log_secret(text='REQ', obj=req)
    else:
        log_secret(text='Invalid request', obj=req)
        return nak({}, status=400)

    if await check_token(req):
        return ack(req)

    if not app['secrets']:
        # If secrets aren't yet available, none of the system accounts will be
        # functional and thus neither will the cluster, so there's no point to
        # going any further. Additionally, we don't want to accidentally leak
        # system account tokens to external auth endpoints.
        app.logger.warning('Secrets not yet available; aborting')
        return nak(req)

    if await check_secrets(req):
        return ack(req)

    if AWS_IAM_ENDPOINT and await check_aws_iam(req):
        return ack(req)

    if KEYSTONE_ENDPOINT and await check_keystone(req):
        return ack(req)

    if CUSTOM_AUTHN_ENDPOINT and await check_custom(req):
        return ack(req)

    return nak(req)


@routes.post('/slow-test')
async def slow_test(request):
    app.logger.debug('Slow request started')
    await asyncio.sleep(5)
    app.logger.debug('Slow request finished')
    return aiohttp.web.json_response({'status': {'authenticated': False}})


async def refresh_secrets(app):
    app.logger.info('Refreshing secrets')
    retcode, stdout, stderr = await run(
        'systemctl', 'is-active', 'snap.kube-apiserver.daemon'
    )
    # See note in run() docstring above about exit 255.
    if retcode not in (0, 255) or stdout.strip() != 'active':
        app.logger.info('Skipping secret refresh: kube-apiserver is not ready '
                        '({}, {})'.format(retcode, stdout.strip()))
        return

    retcode, stdout, stderr = await kubectl(
        'get', 'secrets', '-n', 'kube-system', '-o', 'json'
    )
    # See note in run() docstring above about exit 255.
    if retcode not in (0, 255) or stderr:
        app.logger.warning('Unable to load secrets ({}): {}'.format(retcode, stderr))
        return

    try:
        secrets = json.loads(stdout)
    except json.JSONDecodeError:
        app.logger.exception('Unable to parse secrets')
        return

    new_secrets = {}
    for secret in secrets.get('items', []):
        try:
            data_b64 = secret['data']
            username_b64 = data_b64['username'].encode('UTF-8')
            password_b64 = data_b64['password'].encode('UTF-8')
            groups_b64 = data_b64.get('groups', '').encode('UTF-8')
        except (KeyError, TypeError):
            # CK secrets will have populated 'data', but not all secrets do
            continue

        username = uid = b64decode(username_b64).decode('UTF-8')
        password = b64decode(password_b64).decode('UTF-8')
        groups = b64decode(groups_b64).decode('UTF-8').split(',')

        # NB: CK creates k8s secrets with the 'password' field set as
        # uid::token. Split the decoded password so we can send a 'uid' back.
        # If there is no delimiter, set uid == username.
        # TODO: make the delimeter less magical so it doesn't get out of
        # sync with the function that creates secrets in k8s-master.py.
        pw_delim = '::'
        if pw_delim in password:
            uid = password.rsplit(pw_delim, 1)[0]
        new_secrets[password] = {
            'username': username,
            'uid': uid,
            'groups': groups,
        }
    app['secrets'] = new_secrets


async def startup(app):
    # Log to gunicorn
    glogger = logging.getLogger('gunicorn.error')
    app.logger.handlers = glogger.handlers
    app.logger.setLevel(glogger.level)

    async def _task():
        while True:
            try:
                await refresh_secrets(app)
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                break
            except Exception:
                app.logger.exception('Failed to get secrets')

    app['secrets'] = {}
    app['secrets_task'] = asyncio.ensure_future(_task())


async def cleanup(app):
    task = app.get('secrets_task')
    task.cancel()
    await task


app.add_routes(routes)
app.on_startup.append(startup)
app.on_cleanup.append(cleanup)


if __name__ == '__main__':
    aiohttp.web.run_app(app)
