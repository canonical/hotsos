from datetime import datetime

from hotsos.core.analytics import LogEventStats
from hotsos.core.plugins.openstack.common import (
    OpenStackChecks,
    OpenstackEventHandlerBase,
    OpenstackEventCallbackBase,
)
from hotsos.core.plugins.openstack.nova import NovaLibvirt
from hotsos.core import utils
from hotsos.core.plugintools import (
    summary_entry,
    get_min_available_entry_index,
)


class OpenstackInstanceChecks(OpenStackChecks):
    """ Implements Openstack Nova instance checks. """
    summary_part_index = 2

    @summary_entry('vm-info', get_min_available_entry_index() + 1)
    def summary_vm_info(self):
        _info = {}

        instances = self.nova.instances.values()
        if instances:
            _info['running'] = {'count': len(instances),
                                'uuids': [i.uuid for i in instances]}

        novalibvirt = NovaLibvirt()
        cpu_models = novalibvirt.cpu_models
        if cpu_models:
            _info["cpu-models"] = cpu_models

        vm_vcpu_info = novalibvirt.vcpu_info
        if vm_vcpu_info:
            _info["vcpu-info"] = vm_vcpu_info

        if _info:
            return _info

        return None


class SrcMigrationCallback(OpenstackEventCallbackBase):
    """
    Implements Openstack Nova live-migration source migration events
    callback.
    """
    event_group = 'nova.migrations'
    event_names = ['src-migration']

    @staticmethod
    def _migration_seq_info(event, resource_idx, info_idxs,
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
                    ts_date = f"{ts_date} {ts_time}"

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

    def __call__(self, event):
        """
        Source migration is defined as a sequence so that we can capture some
        of in the interim events such as memory and disk progress.
        """
        migration_info = {}

        info_idxs = {'memory': 4, 'disk': 5}
        results = self._migration_seq_info(event, 3, info_idxs,
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
        return migration_info, event.section_name


class PrePostLiveMigrationCallback(OpenstackEventCallbackBase):
    """
    Implements Openstack Nova live-migration pre-post migration events
    callback.
    """
    event_group = 'nova.migrations'
    event_names = ['src-post-live-migration', 'dst-pre-live-migration']

    @staticmethod
    def _migration_stats_info(event):
        """
        Process events that have passthrough-results=True such that they can be
        passed directory to analytics.LogEventStats for parsing.
        """
        stats = LogEventStats(event.results, event.name)
        stats.run()
        top5 = stats.get_top_n_events_sorted(5)
        if not top5:
            return None

        results = {"top": top5}
        # There can be a very large number of incomplete migrations so need to
        # find a useful way to represent this
        # if stats.data.incomplete_events:
        #     results['incomplete-migrations'] = stats.data.incomplete_events

        return results

    def __call__(self, event):
        # section name expected to be live-migration
        return self._migration_stats_info(event), event.section_name


class NovaServerMigrationAnalysis(OpenstackEventHandlerBase):
    """ Implements Openstack Nova live-migration events handler. """
    event_group = 'nova.migrations'
    summary_part_index = 3

    @summary_entry('nova-migrations', get_min_available_entry_index() + 2)
    def summary_nova_migrations(self):
        return self.run()
