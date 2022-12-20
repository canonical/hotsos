import abc
import hashlib
import os
import re
import uuid

from datetime import datetime, timedelta

from hotsos.core.host_helpers.cli import CLIHelper
from hotsos.core.log import log
from hotsos.core.config import HotSOSConfig
from hotsos.core.utils import cached_property, MPCache


class ConstraintBase(abc.ABC):

    @cached_property
    def id(self):
        """
        A unique identifier for this constraint.
        """
        return uuid.uuid4()

    @abc.abstractmethod
    def apply_to_line(self, line):
        """
        Apply constraint to a single line.

        @param fd: file descriptor
        """

    @abc.abstractmethod
    def apply_to_file(self, fd):
        """
        Apply constraint to an entire file.

        @param fd: file descriptor
        """

    @abc.abstractmethod
    def stats(self):
        """ provide runtime stats for this object. """

    @abc.abstractmethod
    def __repr__(self):
        """ provide string repr of this object. """


class SkipRangeOverlapException(Exception):
    def __init__(self, ln):
        msg = ("the current and previous skip ranges overlap which "
               "suggests that we have re-entered a range by skipping "
               "line {}.".format(ln))
        super().__init__(msg)


class SkipRange(object):
    # skip directions
    SKIP_BWD = 0
    SKIP_FWD = 1

    def __init__(self):
        self.direction = self.SKIP_BWD
        self.current = set()
        self.prev = set()

    def re_entered(self):
        if self.prev.intersection(self.current):
            return True

        return False

    def add(self, ln):
        self.current.add(ln)
        if self.prev.intersection(self.current):
            raise SkipRangeOverlapException(ln)

    def __len__(self):
        return len(self.current)

    def save_and_reset(self):
        if self.current:
            self.prev = self.current
            self.current = set()
            self.direction = self.SKIP_BWD

    def __repr__(self):
        if self.current:
            _r = sorted(list(self.current))
            if self.direction == self.SKIP_BWD:
                _dir = '<-'
            else:
                _dir = '->'

            return "+skip({}{}{})".format(_r[0], _dir, _r[-1])

        return ""


class BinarySearchState(object):
    # max contiguous skip lines before bailing on file search
    SKIP_MAX = 500

    RC_FOUND_GOOD = 0
    RC_FOUND_BAD = 1
    RC_SKIPPING = 2
    RC_ERROR = 3

    def __init__(self, fd_info, cur_pos):
        self.fd_info = fd_info
        self.rc = self.RC_FOUND_GOOD
        self.cur_ln = 0
        self.cur_pos = cur_pos
        self.next_pos = 0

    def start(self):
        """ Must be called before starting searches beyond the first line of
        a file.

        This is not done in __init__ since it will load file markers, a
        potentially expensive operation that should only be done if necessary.
        """
        self.search_range_start = 0
        self.search_range_end = len(self.fd_info.markers) - 1
        self.update_pos_pointers()
        self.invalid_range = SkipRange()
        self.last_known_good_ln = None

    def save_last_known_good(self):
        self.last_known_good_ln = self.cur_ln

    def skip_current_line(self):
        if len(self.invalid_range) == self.SKIP_MAX - 1:
            self.rc = self.RC_ERROR
            log.warning("reached max contiguous skips (%d) - skipping "
                        "constraint for file %s", self.SKIP_MAX,
                        self.fd_info.fd.name)
            return

        self.rc = self.RC_SKIPPING
        try:
            self.invalid_range.add(self.cur_ln)
            if (self.invalid_range.direction == SkipRange.SKIP_BWD and
                    self.cur_ln > self.search_range_start):
                self.cur_ln -= 1
            elif self.cur_ln < self.search_range_end:
                if self.invalid_range.direction == SkipRange.SKIP_BWD:
                    log.debug("changing skip direction to fwd")

                self.invalid_range.direction = SkipRange.SKIP_FWD
                self.cur_ln += 1

            self.update_pos_pointers()
        except SkipRangeOverlapException:
            if self.last_known_good_ln is not None:
                self.rc = self.RC_FOUND_GOOD
                self.cur_ln = self.last_known_good_ln
                self.update_pos_pointers()
                log.debug("re-entered skip range so good line is %s",
                          self.cur_ln)
                self.fd_info.fd.seek(self.cur_pos)
            else:
                self.rc = self.RC_ERROR
                log.error("last known good not set so not sure where to "
                          "go after skip range overlap.")

    def update_pos_pointers(self):
        if len(self.fd_info.markers) == 0:
            log.debug("file %s has no markers - skipping update pos pointers",
                      self.fd_info.fd.name)
            return

        ln = self.cur_ln
        self.cur_pos = self.fd_info.markers[ln]
        if len(self.fd_info.markers) > ln + 1:
            self.next_pos = self.fd_info.markers[ln + 1]
        else:
            self.next_pos = self.fd_info.eof_pos

    def get_next_midpoint(self):
        """
        Given two line numbers in a file, find the mid point.
        """
        start = self.search_range_start
        end = self.search_range_end
        if start == end:
            return start, self.fd_info.markers[start]

        range = end - start
        mid = start + int(range / 2) + (range % 2)
        log.debug("midpoint: start=%s, mid=%s, end=%s", start, mid, end)
        self.cur_ln = mid

    def __repr__(self):
        return ("start={}{}, end={}, cur_pos={}, cur_ln={}, rc={}".format(
                self.search_range_start,
                self.invalid_range,
                self.search_range_end,
                self.cur_pos,
                self.cur_ln,
                self.rc))


class SeekInfo(object):

    def __init__(self, fd):
        self.fd = fd
        self.iterations = 0
        self._orig_pos = self.fd.tell()
        self.cache = MPCache('file_markers_{}'.format(self.fname_hash),
                             'search_constraints')

    @cached_property
    def fname_hash(self):
        hash = hashlib.sha256()
        hash.update(self.fd.name.encode('utf-8'))
        return hash.hexdigest()

    @property
    def fmtime_size(self):
        """
        Criteria used to determine if file contents changed since markers were
        last generated.
        """
        if not os.path.exists(self.fd.name):
            return 0

        mtime = os.path.getmtime(self.fd.name)
        size = os.path.getsize(self.fd.name)
        return "{}+{}".format(mtime, size)

    @cached_property
    def markers(self):
        """
        Creates a list of positions of each start of line. Starts at current
        position in the file and is non-destructive i.e. original position is
        restored.

        Since this is an expensive operation we only want to do it once per
        file/path so the results are cached on disk and loaded when needed.

        NOTE: this is only safe to use if the file does not change between
              calls.
        """
        log.debug("loading markers for '%s'", self.fd.name)
        fname = self.fd.name
        fmtime_size = self.fmtime_size
        if fmtime_size:
            cached = self.cache.get(fmtime_size)
            if cached:
                log.debug("finished loading markers for '%s' with mtime %s",
                          fname, fmtime_size)
                return cached

        log.debug("no cached markers for '%s' - generating new set",
                  self.fd.name)

        self.fd.seek(self.orig_pos)
        _markers = [self.fd.tell()]
        for _ in self.fd:
            _markers.append(self.fd.tell())

        # pop EOF
        _markers.pop()

        # restore
        self.fd.seek(self.orig_pos)
        if fmtime_size:
            self.cache.set(fmtime_size, _markers)
        else:
            log.warning("not caching markers for file '%s' since mtime not "
                        "valid", self.fd.name)

        log.debug("finished loading markers for '%s'", fname)
        return _markers

    @cached_property
    def eof_pos(self):
        """
        Returns file EOF position.
        """
        orig = self.fd.tell()
        eof = self.fd.seek(0, 2)
        self.fd.seek(orig)
        return eof

    @cached_property
    def orig_pos(self):
        """
        The original position of the file descriptor.

        NOTE: cannot be called when iterating over an fd. Must be called before
        any destructive operations take place.
        """
        return self._orig_pos

    def reset(self):
        log.debug("restoring file position to start (%s)",
                  self.orig_pos)
        self.fd.seek(self.orig_pos)


class BinarySeekSearchBase(ConstraintBase):
    """
    Provides a way to seek to a point in a file using a binary search and a
    given condition.
    """

    @abc.abstractmethod
    def extracted_datetime(self, line):
        """
        Extract datetime from line. Returns a datetime object or None if unable
        to extract one from the line.

        @param line: text line to extract a datetime from.
        """

    def _seek_and_validate(self, datetime_obj):
        """
        Seek to position and validate. If the line at pos is valid the new
        position is returned otherwise None.

        NOTE: this operation is destructive and will always point to the next
              line after being called.

        @param pos: position in a file.
        """
        if self._line_date_is_valid(datetime_obj):
            return self.fd_info.fd.tell()

    def _check_line(self, search_state):
        """
        Attempt to read and validate datetime from line.

        @return new position or -1 if we were not able to validate the line.
        """
        self.fd_info.fd.seek(search_state.cur_pos)
        # don't read the whole line since we only need the date at the start.
        # hopefully 64 bytes is enough for any date+time format.
        datetime_obj = self.extracted_datetime(self.fd_info.fd.read(64))
        self.fd_info.fd.seek(search_state.next_pos)
        if datetime_obj is None:
            return -1

        return self._seek_and_validate(datetime_obj)

    def _seek_next(self, state):
        log.debug("seek %s", state)
        newpos = self._check_line(state)
        if newpos == -1:
            # until we get out of a skip range we want to leave the pos at the
            # start but we rely on the caller to enforce this so that we don't
            # have to seek(0) after every skip.
            state.skip_current_line()
            return state

        if newpos is None:
            state.rc = state.RC_FOUND_BAD
            if state.cur_ln == 0:
                log.debug("first line is not valid, checking last line")
                state.cur_ln = state.search_range_end
                state.update_pos_pointers()
            elif (state.search_range_end - state.search_range_start) >= 1:
                # _start_ln = state.search_range_start
                state.search_range_start = state.cur_ln
                # log.debug("going forwards (%s->%s:%s)", _start_ln,
                #           state.search_range_start, state.search_range_end)
                state.invalid_range.save_and_reset()
                state.get_next_midpoint()
                state.update_pos_pointers()
        else:
            state.save_last_known_good()
            state.rc = state.RC_FOUND_GOOD
            if state.cur_ln == 0:
                log.debug("first line is valid so assuming same for rest of "
                          "file")
                self.fd_info.reset()
            elif state.search_range_end - state.search_range_start <= 1:
                log.debug("found final good ln=%s", state.cur_ln)
                self.fd_info.fd.seek(state.cur_pos)
            elif (len(state.invalid_range) > 0 and
                  state.invalid_range.direction == SkipRange.SKIP_FWD):
                log.debug("found good after skip range")
                self.fd_info.fd.seek(state.cur_pos)
            else:
                # set rc to bad since we are going to a new range
                state.rc = state.RC_FOUND_BAD
                # _end_ln = state.search_range_end
                state.search_range_end = state.cur_ln
                # log.debug("going backwards (%s:%s->%s)",
                #           state.search_range_start, _end_ln,
                #           state.search_range_end)
                self.fd_info.fd.seek(state.cur_pos)
                state.invalid_range.save_and_reset()
                state.get_next_midpoint()
                state.update_pos_pointers()

        return state

    def _seek_to_first_valid(self, destructive=True):
        """
        Find first valid line in file using binary search. By default this is a
        destructive and will actually seek to the line. If no line is found the
        descriptor will be at EOF.

        Returns offset at which valid line was found.

        @param destructive: by default this seek operation is destructive i.e.
                            it will find the least valid point and stay there.
                            If that is not desired this can be set to False.
        """
        search_state = BinarySearchState(self.fd_info, self.fd_info.fd.tell())
        offset = 0

        # check first line before going ahead with full search which requires
        # generating file markers that is expensive for large files.
        search_state.next_pos = search_state.cur_pos + 1
        if self._check_line(search_state) == search_state.next_pos:
            self.fd_info.reset()
            log.debug("first line is valid so assuming same for rest of "
                      "file")
            log.debug("seek %s finished (skipped %d lines) current_pos=%s, "
                      "offset=%s iterations=%s",
                      self.fd_info.fd.name, offset,
                      self.fd_info.fd.tell(), offset, self.fd_info.iterations)

            return offset

        search_state.start()
        if len(self.fd_info.markers) > 0:
            while True:
                self.fd_info.iterations += 1
                search_state = self._seek_next(search_state)
                if search_state.rc == search_state.RC_ERROR:
                    offset = 0
                    self.fd_info.reset()
                    break

                if (search_state.search_range_end -
                        search_state.search_range_start) < 1:
                    # we've reached the end of all ranges but the result in
                    # undetermined.
                    if search_state.rc != search_state.RC_FOUND_BAD:
                        self.fd_info.reset()
                        offset = 0
                    else:
                        offset = search_state.cur_ln

                    break

                # log.debug(search_state)
                if search_state.rc == search_state.RC_FOUND_GOOD:
                    # log.debug("seek ended at offset=%s", search_state.cur_ln)
                    offset = search_state.cur_ln
                    break

                if search_state.rc == search_state.RC_SKIPPING:
                    if ((search_state.cur_ln >= search_state.search_range_end)
                            and (len(search_state.invalid_range) ==
                                 search_state.search_range_end)):
                        # offset and pos should still be SOF so we
                        # make this the same
                        search_state.cur_ln = 0
                        self.fd_info.reset()
                        break

                if self.fd_info.iterations >= len(self.fd_info.markers):
                    log.warning("exiting seek loop since limit reached "
                                "(eof=%s)", self.fd_info.eof_pos)
                    offset = 0
                    self.fd_info.reset()
                    break
        else:
            log.debug("file %s is empty", self.fd_info.fd.name)

        if not destructive:
            self.fd_info.fd.reset()

        log.debug("seek %s finished (skipped %d lines) current_pos=%s, "
                  "offset=%s iterations=%s",
                  self.fd_info.fd.name, offset,
                  self.fd_info.fd.tell(), offset, self.fd_info.iterations)

        return offset


class SearchConstraintSearchSince(BinarySeekSearchBase):

    def __init__(self, exprs=None, hours=None):
        """
        A search expression is provided that allows us to identify a datetime
        on each line and check whether it is within a given time period. The
        time period used defaults to 24 hours if use_all_logs is false, 7 days
        if it is true and max_logrotate_depth is default otherwise whatever
        value provided. This can be overridden by providing a specific number
        of hours.

        @param exprs: a list of search/regex expressions used to identify a
                      date/time in.
        each line in the file we are applying this constraint to.
        @param hours: override default period with number of hours
        """
        super().__init__()
        if hours == 0:
            log.warning("search constraint created with hours=%s", hours)

        self.fd_info = None
        self._line_pass = 0
        self._line_fail = 0
        self.exprs = exprs
        self.hours = hours
        self.date_format = '%Y-%m-%d %H:%M:%S'
        self._results = {}

    def extracted_datetime(self, line):
        """
        Validate if the given line falls within the provided constraint. In
        this case that's whether it has a datetime that is >= to the "since"
        date.

        @param line: text line to extract a datetime from.
        """
        if type(line) == bytes:
            # need this for e.g. gzipped files
            line = line.decode("utf-8")

        for expr in self.exprs:
            # log.debug("attempting to extract from line using expr '%s'",
            #           expr)
            ret = re.search(expr, line)
            if ret:
                # log.debug("expr '%s' successful", expr)
                break

        if not ret:
            # log.info("all exprs unsuccessful: %s", self.exprs)
            return

        str_date = ""
        for g in ret.groups():
            str_date += "{} ".format(g)

        str_date = str_date.strip()
        try:
            return datetime.strptime(str_date, self.date_format)
        except ValueError:
            log.exception("")

    @property
    def _is_valid(self):
        return self._since_date is not None

    @cached_property
    def _current_date(self):
        current_date = CLIHelper().date(format="+{}".format(self.date_format))
        if not current_date:
            log.warning("date() returned unexpected value '%s'",
                        current_date)
            return None

        return datetime.strptime(current_date, self.date_format)

    @cached_property
    def _since_date(self):
        """
        Reflects the date from which we will start to apply searches.
        """
        if not self._current_date:
            return

        days = 0
        if self.hours is None:
            days = 1
            if HotSOSConfig.use_all_logs:
                days = HotSOSConfig.max_logrotate_depth

        return self._current_date - timedelta(days=days, hours=self.hours or 0)

    def _line_date_is_valid(self, extracted_datetime):
        """
        Validate if the given line falls within the provided constraint. In
        this case that's whether it has a datetime that is >= to the "since"
        date.
        """
        ts = extracted_datetime
        if ts is None:
            # log.info("s:%s: failed to extract datetime from "
            #          "using expressions %s - assuming line is not valid",
            #          unique_search_id, ', '.join(self.exprs))
            return False

        if ts < self._since_date:
            # log.debug("%s < %s at (%s) i.e. False", ts, self._since_date,
            #           line[-3:].strip())
            return False

        # log.debug("%s >= %s at (%s) i.e. True", ts, self._since_date,
        #           line[-3:].strip())

        return True

    def apply_to_line(self, line):
        if not self._is_valid:
            log.warning("c:%s unable to apply constraint to line", self.id)
            self._line_pass += 1
            return True

        extracted_datetime = self.extracted_datetime(line)
        if not extracted_datetime:
            self._line_pass += 1
            return True

        ret = self._line_date_is_valid(extracted_datetime)
        if ret:
            self._line_pass += 1
        else:
            self._line_fail += 1

        return ret

    def apply_to_file(self, fd, destructive=True):
        self.fd_info = SeekInfo(fd)
        if not self._is_valid:
            log.warning("c:%s unable to apply constraint to %s", self.id,
                        fd.name)
            return

        if fd.name in self._results:
            return self._results[fd.name]

        log.debug("s:%s: starting binary seek search to %s in file %s "
                  "(destructive=True)", self.id, self._since_date, fd.name)
        self._results[fd.name] = self._seek_to_first_valid(destructive)
        log.debug("s:%s: finished binary seek search in file %s", self.id,
                  fd.name)
        return self._results[fd.name]

    def stats(self):
        _stats = {'line': {'pass': self._line_pass,
                           'fail': self._line_fail}}
        if self.fd_info:
            _stats['file'] = {'name': self.fd_info.fd.name,
                              'iterations': self.fd_info.iterations}
        return _stats

    def __repr__(self):
        return ("id={}, since={}, current={}".
                format(self.id, self._since_date, self._current_date))
