import os

from datetime import datetime

from core import constants
from core.ycheck import CallbackHelper
from core.analytics import LogEventStats
from core.searchtools import (
    FileSearcher,
    SearchDef,
)
from core.plugins.openstack import (
    OpenstackChecksBase,
    OpenstackEventChecksBase,
    OpenstackConfig,
)
from core.plugins.system import SystemBase
from core.plugins.kernel import CPU
from core import utils

YAML_PRIORITY = 3
EVENTCALLBACKS = CallbackHelper()


class OpenstackInstanceChecks(OpenstackChecksBase):

    def __init__(self):
        super().__init__()
        self._nova_config = OpenstackConfig(os.path.join(constants.DATA_ROOT,
                                                         "etc/nova/nova.conf"))

    def _get_vm_info(self):
        instances = self.nova.instances.values()
        if instances:
            self._output["running"] = [i.uuid for i in instances]

    def _get_vcpu_info(self):
        vcpu_info = {}
        guests = []
        s = FileSearcher()
        if self.nova.instances:
            for i in self.nova.instances.values():
                guests.append(i.name)
                path = os.path.join(constants.DATA_ROOT, 'etc/libvirt/qemu',
                                    "{}.xml".format(i.name))
                s.add_search_term(SearchDef(".+vcpus>([0-9]+)<.+",
                                            tag=i.name), path)

            total_vcpus = 0
            results = s.search()
            for guest in guests:
                for r in results.find_by_tag(guest):
                    vcpus = r.get(1)
                    total_vcpus += int(vcpus)

            vcpu_info["used"] = total_vcpus
            sysinfo = SystemBase()
            if sysinfo.num_cpus is not None:
                total_cores = sysinfo.num_cpus
                vcpu_info["system-cores"] = total_cores

                pinset = self._nova_config.get("vcpu_pin_set",
                                               expand_ranges=True) or []
                pinset += self._nova_config.get("cpu_dedicated_set",
                                                expand_ranges=True) or []
                pinset += self._nova_config.get("cpu_shared_set",
                                                expand_ranges=True) or []
                if pinset:
                    # if pinning is used, reduce total num of cores available
                    # to those included in nova cpu sets.
                    available_cores = len(set(pinset))
                else:
                    available_cores = total_cores

                vcpu_info["available-cores"] = available_cores

                cpu = CPU()
                # put this here so that available cores value has
                # context
                if cpu.smt is not None:
                    vcpu_info["smt"] = cpu.smt

                factor = float(total_vcpus) / available_cores
                vcpu_info["overcommit-factor"] = round(factor, 2)

            self._output["vcpu-info"] = vcpu_info

    @property
    def output(self):
        if self._output:
            return {"vm-info": self._output}

    def __call__(self):
        # Only run if we think Openstack is installed.
        if not self.openstack_installed:
            return

        self._get_vm_info()
        self._get_vcpu_info()


class NovaServerMigrationAnalysis(OpenstackEventChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, callback_helper=EVENTCALLBACKS,
                         yaml_defs_group='nova-migrations',
                         event_results_output_key='nova-migrations',
                         searchobj=FileSearcher(),
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

    @EVENTCALLBACKS.callback
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
        """
        if stats.data.incomplete_events:
            results['incomplete-migrations'] = stats.data.incomplete_events
        """

        return results

    @EVENTCALLBACKS.callback
    def src_post_live_migration(self, event):
        # section name expected to be live-migration
        return self.migration_stats_info(event), event.section

    @EVENTCALLBACKS.callback
    def dst_pre_live_migration(self, event):
        # section name expected to be live-migration
        return self.migration_stats_info(event), event.section
