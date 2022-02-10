# Copyright 2014-2015 Canonical Limited.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

#
# Copyright 2014 Canonical Ltd.
#
# Authors:
#  Edward Hope-Morley <opentastic@gmail.com>
#

import time

from charmhelpers.core.hookenv import (
    log,
    INFO,
)


def retry_on_exception(num_retries, base_delay=0, exc_type=Exception):
    """If the decorated function raises exception exc_type, allow num_retries
    retry attempts before raise the exception.
    """
    def _retry_on_exception_inner_1(f):
        def _retry_on_exception_inner_2(*args, **kwargs):
            retries = num_retries
            multiplier = 1
            while True:
                try:
                    return f(*args, **kwargs)
                except exc_type:
                    if not retries:
                        raise

                delay = base_delay * multiplier
                multiplier += 1
                log("Retrying '%s' %d more times (delay=%s)" %
                    (f.__name__, retries, delay), level=INFO)
                retries -= 1
                if delay:
                    time.sleep(delay)

        return _retry_on_exception_inner_2

    return _retry_on_exception_inner_1


def retry_on_predicate(num_retries, predicate_fun, base_delay=0):
    """Retry based on return value

    The return value of the decorated function is passed to the given predicate_fun. If the
    result of the predicate is False, retry the decorated function up to num_retries times

    An exponential backoff up to base_delay^num_retries seconds can be introduced by setting
    base_delay to a nonzero value. The default is to run with a zero (i.e. no) delay

    :param num_retries: Max. number of retries to perform
    :type num_retries: int
    :param predicate_fun: Predicate function to determine if a retry is necessary
    :type predicate_fun: callable
    :param base_delay: Starting value in seconds for exponential delay, defaults to 0 (no delay)
    :type base_delay: float
    """
    def _retry_on_pred_inner_1(f):
        def _retry_on_pred_inner_2(*args, **kwargs):
            retries = num_retries
            multiplier = 1
            delay = base_delay
            while True:
                result = f(*args, **kwargs)
                if predicate_fun(result) or retries <= 0:
                    return result
                delay *= multiplier
                multiplier += 1
                log("Result {}, retrying '{}' {} more times (delay={})".format(
                    result, f.__name__, retries, delay), level=INFO)
                retries -= 1
                if delay:
                    time.sleep(delay)

        return _retry_on_pred_inner_2

    return _retry_on_pred_inner_1
