import os

from searchkit import (   # noqa: F403,F401, pylint: disable=W0611
    FileSearcher as _FileSearcher,
    ResultFieldInfo,
    SearchDef,
    SequenceSearchDef,
)
from searchkit.constraints import (
    SearchConstraintSearchSince as _SearchConstraintSearchSince
)

from hotsos.core.log import log
from hotsos.core.host_helpers.cli import CLIHelper
from hotsos.core.config import HotSOSConfig


class FileSearcher(_FileSearcher):
    def __init__(self, *args, **kwargs):
        super().__init__(*args,
                         max_parallel_tasks=HotSOSConfig.max_parallel_tasks,
                         max_logrotate_depth=HotSOSConfig.max_logrotate_depth,
                         **kwargs)


class SearchConstraintSearchSince(_SearchConstraintSearchSince):
    def __init__(self, *args, **kwargs):
        if 'days' not in kwargs and 'hours' not in kwargs:
            days = 1
            if HotSOSConfig.use_all_logs:
                days = HotSOSConfig.max_logrotate_depth

            kwargs['days'] = days

        current_date = CLIHelper().date(format='+%Y-%m-%d %H:%M:%S')
        if not current_date or type(current_date) != str:
            log.error("current date '%s' being provided to search "
                      "constraints is not valid.", current_date)
            return

        super().__init__(*args,
                         current_date=current_date,
                         cache_path=HotSOSConfig.plugin_tmp_dir,
                         allow_constraints_for_unverifiable_logs=HotSOSConfig.
                         allow_constraints_for_unverifiable_logs,
                         **kwargs)

    def apply_to_line(self, *args, **kwargs):
        if not os.path.isdir(os.path.join(HotSOSConfig.data_root,
                                          'sos_commands')):
            log.info("skipping line constraint since data_root is not a "
                     "sosreport therefore files may be changing")
            return True

        return super().apply_to_line(*args, **kwargs)

    def apply_to_file(self, *args, **kwargs):
        if not os.path.isdir(os.path.join(HotSOSConfig.data_root,
                                          'sos_commands')):
            log.info("skipping file constraint since data_root is not a "
                     "sosreport therefore files may be changing")
            return 0

        return super().apply_to_file(*args, **kwargs)
