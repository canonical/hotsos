from functools import cached_property

from hotsos.core.host_helpers import CLIHelper

CEPH_POOL_TYPE = {1: 'replicated', 3: 'erasure-coded'}

# Ratio threshold for OSD count imbalance across failure-domain buckets.
# A value of 1.33 means a warning is raised when the largest bucket has
# >= 1.33x the OSDs of the smallest bucket.
#
# This is a arbitrarily chosen value to catch meaningful imbalances
# without alerting on minor differences (e.g. 10 vs 9 OSDs).
CEPH_OSD_COUNT_IMBALANCE_THRESHOLD = 1.33


class CephCrushMap():
    """
    Representation of a Ceph cluster CRUSH map.
    """
    @staticmethod
    def _filter_pools_by_rule(pools, crush_rule):
        res_pool = []
        for pool in pools:
            if pool['crush_rule'] == crush_rule:
                pool_str = pool['pool_name'] + ' (' + str(pool['pool']) + ')'
                res_pool.append(pool_str)

        return res_pool

    @cached_property
    def osd_crush_dump(self):
        return CLIHelper().ceph_osd_crush_dump_json_decoded() or {}

    @cached_property
    def ceph_report(self):
        return CLIHelper().ceph_report_json_decoded() or {}

    @cached_property
    def rules(self):
        """
        Returns a list of crush rules, mapped to the respective pools.
        """
        if not self.ceph_report:
            return {}

        rule_to_pool = {}
        for rule in self.ceph_report['crushmap']['rules']:
            rule_id = rule['rule_id']
            rtype = rule['type']
            pools = self.ceph_report['osdmap']['pools']
            pools = self._filter_pools_by_rule(pools, rule_id)
            rule_to_pool[rule['rule_name']] = {'id': rule_id,
                                               'type': CEPH_POOL_TYPE[rtype],
                                               'pools': pools}

        return rule_to_pool

    @staticmethod
    def _build_buckets_from_crushdump(crushdump):
        buckets = {}
        # iterate jp for each bucket
        for bucket in crushdump["buckets"]:
            bid = bucket["id"]
            items = []
            for item in bucket["items"]:
                items.append(item["id"])

            buckets[bid] = {"name": bucket["name"],
                            "type_id": bucket["type_id"],
                            "type_name": bucket["type_name"],
                            "items": items}

        return buckets

    def _rule_used_by_any_pool(self, rule_id):
        for pool_dict in self.rules.values():
            if (pool_dict['id'] == rule_id) and pool_dict['pools']:
                return True
        return False

    @cached_property
    def crushmap_mixed_buckets(self):
        """
        Report buckets that have mixed type of items,
        as they will cause crush map unable to compute
        the expected up set
        """
        if not self.osd_crush_dump:
            return []

        bad_buckets = []
        buckets = self._build_buckets_from_crushdump(self.osd_crush_dump)
        # check all buckets
        for bdict in buckets.values():
            items = bdict["items"]
            type_ids = []
            for item in items:
                if item >= 0:
                    type_ids.append(0)
                else:
                    type_ids.append(buckets[item]["type_id"])

            if not type_ids:
                continue

            # verify if the type_id list contain mixed type id
            if type_ids.count(type_ids[0]) != len(type_ids):
                bad_buckets.append(bdict["name"])

        return bad_buckets

    @cached_property
    def crushmap_mixed_buckets_str(self):
        return ','.join(self.crushmap_mixed_buckets)

    def _is_bucket_imbalanced(self, buckets, start_bucket_id, failure_domain,
                              weight=-1):
        """Return whether a tree is unbalanced

        Recursively determine if a given tree (start_bucket_id) is
        balanced at the given failure domain (failure_domain) in the
        CRUSH tree(s) provided by the buckets parameter.
        """

        for item in buckets[start_bucket_id]["items"]:
            # Skip items that are not buckets (e.g., OSDs with positive IDs)
            # since they are leaf nodes and don't exist in buckets.
            if item["id"] not in buckets:
                continue
            if buckets[item["id"]]["type_name"] != failure_domain:
                if self._is_bucket_imbalanced(buckets, item["id"],
                                              failure_domain, weight):
                    return True
            # Handle items/buckets with 0 weight correctly, by
            # ignoring them.
            # These are excluded from placement consideration,
            # and therefore do not unbalance a tree.
            elif item["weight"] > 0:
                if weight == -1:
                    weight = item["weight"]
                else:
                    if weight != item["weight"]:
                        return True

        return False

    def _get_in_use_trees_and_fdomains(self):
        """Get list of (rule_id, tree_bucket_id, failure_domain) tuples
        for rules that are used by at least one pool."""
        to_check = []
        for rule in self.osd_crush_dump.get('rules', []):
            taken = 0
            fdomain = 0
            rid = rule["rule_id"]
            for step in rule['steps']:
                if step["op"] == "take":
                    taken = step["item"]
                if "type" in step and taken != 0:
                    fdomain = step["type"]
                if taken != 0 and fdomain != 0 and \
                        self._rule_used_by_any_pool(rid):
                    to_check.append((rid, taken, fdomain))
                    taken = fdomain = 0
        return to_check

    @cached_property
    def crushmap_equal_buckets(self):
        """
        Report when in-use failure domain buckets are unbalanced.

        Uses the trees and failure domains referenced in the
        CRUSH rules, and checks that all buckets of the failure
        domain type in the referenced tree are equal or of zero size.
        """
        if not self.osd_crush_dump:
            return []

        buckets = {b['id']: b for b in self.osd_crush_dump["buckets"]}
        to_check = self._get_in_use_trees_and_fdomains()

        unequal_buckets = []
        for _, tree, failure_domain in to_check:
            if self._is_bucket_imbalanced(buckets, tree, failure_domain):
                unequal_buckets.append(f"tree '{buckets[tree]['name']}' at "
                                       f"the '{failure_domain}' level")

        return unequal_buckets

    @cached_property
    def crushmap_equal_buckets_pretty(self):
        unequal = self.crushmap_equal_buckets
        if unequal:
            return ", ".join(unequal)

        return None

    def _count_osds_by_class_in_bucket(self, buckets, bucket_id,
                                       device_classes):
        """Count the number of OSDs per device class under a bucket.

        @param device_classes: dict mapping OSD id -> class name
        @return: dict mapping class name -> count
        """
        bucket = buckets.get(bucket_id)
        if bucket is None:
            return {}

        counts = {}
        for item in bucket["items"]:
            if item["id"] >= 0:
                cls = device_classes.get(item["id"], "unknown")
                counts[cls] = counts.get(cls, 0) + 1
            elif item["id"] in buckets:
                sub = self._count_osds_by_class_in_bucket(
                    buckets, item["id"], device_classes)
                for cls, cnt in sub.items():
                    counts[cls] = counts.get(cls, 0) + cnt

        return counts

    def _check_class_imbalance(self, buckets, fd_bucket_ids,
                               device_classes):
        """Check for per-class OSD count imbalance across fd buckets.

        @return: list of (device_class, bucket_count_parts) tuples
        """
        per_bucket = {}
        all_classes = set()
        for bid in fd_bucket_ids:
            class_counts = self._count_osds_by_class_in_bucket(
                buckets, bid, device_classes)
            per_bucket[bid] = class_counts
            all_classes.update(class_counts.keys())

        results = []
        for cls in sorted(all_classes):
            counts = [per_bucket[bid].get(cls, 0)
                      for bid in fd_bucket_ids]
            nonzero = [c for c in counts if c > 0]
            if not nonzero:
                continue
            # A class present in only one bucket is a severe imbalance
            if len(nonzero) == 1 and len(counts) > 1:
                pass  # fall through to report
            elif len(nonzero) < 2:
                continue
            elif max(nonzero) < (
                    CEPH_OSD_COUNT_IMBALANCE_THRESHOLD * min(nonzero)):
                continue

            parts = [f"{buckets[bid]['name']}="
                     f"{per_bucket[bid].get(cls, 0)}"
                     for bid in fd_bucket_ids]
            results.append((cls, parts))

        return results

    @cached_property
    def crushmap_osd_count_imbalanced_buckets(self):
        """
        Report failure-domain buckets with significantly imbalanced OSD
        counts per device class. Flags when the maximum OSD count across
        sibling buckets is >= CEPH_OSD_COUNT_IMBALANCE_THRESHOLD times
        the minimum (non-zero) count for any device class.
        """
        if not self.osd_crush_dump:
            return []

        buckets = {b['id']: b for b in self.osd_crush_dump["buckets"]}
        device_classes = {
            d['id']: d.get('class', 'unknown')
            for d in self.osd_crush_dump.get("devices", [])}

        imbalanced = []
        for _, tree, failure_domain in self._get_in_use_trees_and_fdomains():
            fd_bucket_ids = self._collect_fd_buckets(
                buckets, tree, failure_domain)
            if len(fd_bucket_ids) < 2:
                continue

            for cls, parts in self._check_class_imbalance(
                    buckets, fd_bucket_ids, device_classes):
                imbalanced.append(
                    f"tree '{buckets[tree]['name']}' at the "
                    f"'{failure_domain}' level for device class "
                    f"'{cls}' (OSD counts: {', '.join(parts)})")

        return imbalanced

    def _collect_fd_buckets(self, buckets, start_bucket_id, failure_domain):
        """Collect bucket IDs at the given failure domain level."""
        result = []
        bucket = buckets.get(start_bucket_id)
        if bucket is None:
            return result

        for item in bucket["items"]:
            if item["id"] not in buckets:
                continue
            child = buckets[item["id"]]
            if child["type_name"] == failure_domain:
                result.append(item["id"])
            else:
                result.extend(self._collect_fd_buckets(
                    buckets, item["id"], failure_domain))

        return result

    @cached_property
    def crushmap_osd_count_imbalanced_pretty(self):
        imbalanced = self.crushmap_osd_count_imbalanced_buckets
        if imbalanced:
            return "; ".join(imbalanced)

        return None

    @property
    def osd_count_imbalance_threshold(self):
        """Return the configured OSD count imbalance threshold."""
        return CEPH_OSD_COUNT_IMBALANCE_THRESHOLD

    @staticmethod
    def collect_osd_classes(node_id, nodes):
        """Recursively collect device classes of all OSDs under a node."""
        node = nodes.get(node_id)
        if node is None:
            return set()
        if node.get('type') == 'osd':
            dc = node.get('device_class')
            return {dc} if dc else set()
        classes = set()
        for child_id in node.get('children', []):
            classes.update(
                CephCrushMap.collect_osd_classes(child_id, nodes))
        return classes

    @cached_property
    def crush_tree_has_overlapping_roots(self):
        """
        Detect overlapping roots from ceph osd crush tree --show-shadow.

        A non-shadow root has overlapping roots when it contains OSDs from
        multiple device classes.
        """
        crush_tree = CLIHelper().ceph_osd_crush_tree_json_decoded()
        if not crush_tree:
            return False

        nodes = {n['id']: n for n in crush_tree.get('nodes', [])}

        for node in crush_tree.get('nodes', []):
            if node.get('type') != 'root':
                continue
            # Skip shadow roots (their names contain '~')
            if '~' in node.get('name', ''):
                continue
            classes = self.collect_osd_classes(node['id'], nodes)
            if len(classes) > 1:
                return True

        return False

    @cached_property
    def autoscaler_enabled_pools(self):
        if not self.ceph_report:
            return []

        pools = self.ceph_report['osdmap']['pools']
        return [p for p in pools if p.get('pg_autoscale_mode') == 'on']

    @cached_property
    def autoscaler_disabled_pools(self):
        if not self.ceph_report:
            return []

        pools = self.ceph_report['osdmap']['pools']
        return [p for p in pools if p.get('pg_autoscale_mode') != 'on']

    @cached_property
    def is_rgw_using_civetweb(self):
        if not self.ceph_report:
            return []

        try:
            rgws = self.ceph_report['servicemap']['services']['rgw']['daemons']
            for _, outer_d in rgws.items():
                if isinstance(outer_d, dict):
                    if outer_d['metadata']['frontend_type#0'] == 'civetweb':
                        return True
        except (ValueError, KeyError):
            pass

        return False
