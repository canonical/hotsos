from subprocess import check_output
from time import sleep


def retry(times, delay_secs):
    """ Decorator for retrying a method call.
    Args:
        times: How many times should we retry before giving up
        delay_secs: Delay in secs
    Returns: A callable that would return the last call outcome
    """

    def retry_decorator(func):
        """ Decorator to wrap the function provided.
        Args:
            func: Provided function should return either True od False
        Returns: A callable that would return the last call outcome
        """
        def _wrapped(*args, **kwargs):
            res = func(*args, **kwargs)
            attempt = 0
            while not res and attempt < times:
                sleep(delay_secs)
                res = func(*args, **kwargs)
                if res:
                    break
                attempt += 1
            return res
        return _wrapped

    return retry_decorator


def arch():
    '''Return the package architecture as a string.'''
    # Get the package architecture for this system.
    architecture = check_output(['dpkg', '--print-architecture']).rstrip()
    # Convert the binary result into a string.
    architecture = architecture.decode('utf-8')
    return architecture
