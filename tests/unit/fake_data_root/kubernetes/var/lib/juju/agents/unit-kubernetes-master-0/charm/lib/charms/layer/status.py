import inspect
import errno
import subprocess
import yaml
from enum import Enum
from functools import wraps
from pathlib import Path

from charmhelpers.core import hookenv
from charms import layer


_orig_call = subprocess.call
_statuses = {'_initialized': False,
             '_finalized': False}


class WorkloadState(Enum):
    """
    Enum of the valid workload states.

    Valid options are:

      * `WorkloadState.MAINTENANCE`
      * `WorkloadState.BLOCKED`
      * `WorkloadState.WAITING`
      * `WorkloadState.ACTIVE`
    """
    # note: order here determines precedence of state
    MAINTENANCE = 'maintenance'
    BLOCKED = 'blocked'
    WAITING = 'waiting'
    ACTIVE = 'active'


def maintenance(message):
    """
    Set the status to the `MAINTENANCE` state with the given operator message.

    # Parameters
    `message` (str): Message to convey to the operator.
    """
    status_set(WorkloadState.MAINTENANCE, message)


def maint(message):
    """
    Shorthand alias for
    [maintenance](status.md#charms.layer.status.maintenance).

    # Parameters
    `message` (str): Message to convey to the operator.
    """
    maintenance(message)


def blocked(message):
    """
    Set the status to the `BLOCKED` state with the given operator message.

    # Parameters
    `message` (str): Message to convey to the operator.
    """
    status_set(WorkloadState.BLOCKED, message)


def waiting(message):
    """
    Set the status to the `WAITING` state with the given operator message.

    # Parameters
    `message` (str): Message to convey to the operator.
    """
    status_set(WorkloadState.WAITING, message)


def active(message):
    """
    Set the status to the `ACTIVE` state with the given operator message.

    # Parameters
    `message` (str): Message to convey to the operator.
    """
    status_set(WorkloadState.ACTIVE, message)


def status_set(workload_state, message):
    """
    Set the status to the given workload state with a message.

    # Parameters
    `workload_state` (WorkloadState or str): State of the workload.  Should be
        a [WorkloadState](status.md#charms.layer.status.WorkloadState) enum
        member, or the string value of one of those members.
    `message` (str): Message to convey to the operator.
    """
    if not isinstance(workload_state, WorkloadState):
        workload_state = WorkloadState(workload_state)
    if workload_state is WorkloadState.MAINTENANCE:
        _status_set_immediate(workload_state, message)
        return
    layer = _find_calling_layer()
    _statuses.setdefault(workload_state, []).append((layer, message))
    if not _statuses['_initialized'] or _statuses['_finalized']:
        # We either aren't initialized, so the finalizer may never be run,
        # or the finalizer has already run, so it won't run again. In either
        # case, we need to manually invoke it to ensure the status gets set.
        _finalize()


def _find_calling_layer():
    for frame in inspect.stack():
        # switch to .filename when trusty (Python 3.4) is EOL
        fn = Path(frame[1])
        if fn.parent.stem not in ('reactive', 'layer', 'charms'):
            continue
        layer_name = fn.stem
        if layer_name == 'status':
            continue  # skip our own frames
        return layer_name
    return None


def _initialize():
    if not _statuses['_initialized']:
        if layer.options.get('status', 'patch-hookenv'):
            _patch_hookenv()
        hookenv.atexit(_finalize)
        _statuses['_initialized'] = True


def _finalize():
    if _statuses['_initialized']:
        # If we haven't been initialized, we can't truly be finalized.
        # This makes things more efficient if an action sets a status
        # but subsequently starts the reactive bus.
        _statuses['_finalized'] = True
    charm_name = hookenv.charm_name()
    charm_dir = Path(hookenv.charm_dir())
    with charm_dir.joinpath('layer.yaml').open() as fp:
        includes = yaml.safe_load(fp.read()).get('includes', [])
    layer_order = includes + [charm_name]

    for workload_state in WorkloadState:
        if workload_state not in _statuses:
            continue
        if not _statuses[workload_state]:
            continue

        def _get_key(record):
            layer_name, message = record
            if layer_name in layer_order:
                return layer_order.index(layer_name)
            else:
                return 0

        sorted_statuses = sorted(_statuses[workload_state], key=_get_key)
        layer_name, message = sorted_statuses[-1]
        _status_set_immediate(workload_state, message)
        break


def _status_set_immediate(workload_state, message):
    workload_state = workload_state.value
    try:
        hookenv.log('status-set: {}: {}'.format(workload_state, message),
                    hookenv.INFO)
        ret = _orig_call(['status-set', workload_state, message])
        if ret == 0:
            return
    except OSError as e:
        # ignore status-set not available on older controllers
        if e.errno != errno.ENOENT:
            raise


def _patch_hookenv():
    # we can't patch hookenv.status_set directly because other layers may have
    # already imported it into their namespace, so we have to patch sp.call
    subprocess.call = _patched_call


@wraps(_orig_call)
def _patched_call(cmd, *args, **kwargs):
    if not isinstance(cmd, list) or cmd[0] != 'status-set':
        return _orig_call(cmd, *args, **kwargs)
    _, workload_state, message = cmd
    status_set(workload_state, message)
    return 0  # make hookenv.status_set not emit spurious failure logs
