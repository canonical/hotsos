from datetime import datetime

from hotsos.core.analytics import LogEventStats
from hotsos.core.plugins.openstack.common import (
    OpenstackChecksBase,
    OpenstackEventChecksBase,
)
from hotsos.core.plugins.openstack.nova import NovaLibvirt
from hotsos.core.plugins.openstack.openstack import (
    OpenstackTimestampMatcher,
)
from hotsos.core.search import (
    FileSearcher,
    SearchConstraintSearchSince,
)
from hotsos.core import utils
from hotsos.core.ycheck.events import CallbackHelper

EVENTCALLBACKS = CallbackHelper()


class OpenstackInstanceChecks(OpenstackChecksBase):

    def __summary_vm_info(self):
        _info = {}

        instances = self.nova.instances.values()
        if instances:
            _info['running'] = [i.uuid for i in instances]

        novalibvirt = NovaLibvirt()
        cpu_models = novalibvirt.cpu_models
        if cpu_models:
            _info["cpu-models"] = cpu_models

        vm_vcpu_info = novalibvirt.vcpu_info
        if vm_vcpu_info:
            _info["vcpu-info"] = vm_vcpu_info

        if _info:
            return _info


class NovaServerMigrationAnalysis(OpenstackEventChecksBase):

    def __init__(self, *args, **kwargs):
        c = SearchConstraintSearchSince(
                                      ts_matcher_cls=OpenstackTimestampMatcher)
        super().__init__(EVENTCALLBACKS, *args,
                         yaml_defs_group='nova.migrations',
                         searchobj=FileSearcher(constraint=c),
                         **kwargs)

    def migration_seq_info(self, event, resource_idx, info_idxs,
                           incl_time_in_date=False):
        """
        Process the results of an event that was defined as a sequence.

        Returns a dict keyed by a resource id inside which is a dict of
        information keyed by date. The date can optionally be extended to
        include the time to get greater granularity - requires the associated
        search patterns to include this information.

        @param event: EventCheckResult object
        @param resource_idx: int index of the search result group that is used
                             as the resource identifier.
        @param info_idxs: dict if info types and indexes for arbitrary
                          information to be save against each resource.
        @param incl_time_in_date: include the time in the date string. Defaults
                                  to False.
        """
        info = {}
        for section in event.results:
            for result in section:
                if not result.tag.endswith('-body'):
                    continue

                ts_date = result.get(1)
                if incl_time_in_date:
                    ts_time = result.get(2)
                    ts_date = "{} {}".format(ts_date, ts_time)

                resource = result.get(resource_idx)
                if resource not in info:
                    info[resource] = {}

                if result.section_id not in info[resource]:
                    info[resource][result.section_id] = {}

                if ts_date not in info[resource]:
                    info[resource][result.section_id][ts_date] = {}

                resource_date = info[resource][result.section_id][ts_date]

                for name, idx in info_idxs.items():
                    value = result.get(idx)
                    if value is None:
                        continue

                    if name not in resource_date:
                        resource_date[name] = [value]
                    else:
                        resource_date[name].append(value)

        return info

    @EVENTCALLBACKS.callback(event_group='nova.migrations')
    def src_migration(self, event):
        """
        Source migration is defined as a sequence so that we can capture some
        of in the interim events such as memory and disk progress.
        """
        migration_info = {}

        info_idxs = {'memory': 4, 'disk': 5}
        results = self.migration_seq_info(event, 3, info_idxs,
                                          incl_time_in_date=True)
        for vm_uuid, sections in results.items():
            for section in sections.values():
                samples = {}
                start = None
                end = None
                for date, info in utils.sorted_dict(section).items():
                    if start is None:
                        start = date

                    end = date
                    for rtype, values in info.items():
                        if rtype not in samples:
                            samples[rtype] = []

                        samples[rtype] += [int(i) for i in values]

                _start = datetime.strptime(start, "%Y-%m-%d %H:%M:%S")
                _end = datetime.strptime(end, "%Y-%m-%d %H:%M:%S")
                duration = round(float((_end - _start).total_seconds()), 2)
                info = {'start': start, 'end': end, 'duration': duration}
                instance = self.nova.instances.get(vm_uuid)
                if instance and instance.memory_mbytes is not None:
                    info['resources'] = {'memory_mbytes':
                                         instance.memory_mbytes}

                if samples:
                    # regressions imply that the progress counter had one or
                    # more decreases before increasing again.
                    info['regressions'] = {}
                    for rtype, values in samples.items():
                        if 'iterations' not in info:
                            info['iterations'] = len(values)

                        loops = utils.sample_set_regressions(values)
                        info['regressions'][rtype] = loops

                if vm_uuid in migration_info:
                    migration_info[vm_uuid].append(info)
                else:
                    migration_info[vm_uuid] = [info]

        # section name expected to be live-migration
        return migration_info, event.section

    def migration_stats_info(self, event):
        """
        Process events that have passthrough-results=True such that they can be
        passed directory to analytics.LogEventStats for parsing.
        """
        stats = LogEventStats(event.results, event.name)
        stats.run()
        top5 = stats.get_top_n_events_sorted(5)
        if not top5:
            return

        results = {"top": top5}
        # There can be a very large number of incomplete migrations so need to
        # find a useful way to represent this
        # if stats.data.incomplete_events:
        #     results['incomplete-migrations'] = stats.data.incomplete_events

        return results

    @EVENTCALLBACKS.callback(event_group='nova.migrations')
    def src_post_live_migration(self, event):
        # section name expected to be live-migration
        return self.migration_stats_info(event), event.section

    @EVENTCALLBACKS.callback(event_group='nova.migrations')
    def dst_pre_live_migration(self, event):
        # section name expected to be live-migration
        return self.migration_stats_info(event), event.section

    def __summary_nova_migrations(self):
        return self.run_checks()
