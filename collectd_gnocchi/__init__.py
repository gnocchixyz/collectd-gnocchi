# -*- encoding: utf-8 -*-
#
# Copyright © 2016-2018 Red Hat, Inc
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
import collections
import itertools
import math
import operator
import sys
import time
import traceback

import collectd
import gnocchiclient.auth
from gnocchiclient import client
from gnocchiclient import exceptions
from keystoneauth1 import identity
from keystoneauth1 import session

# NOTE(sileht): collectd plugin values index always have a meaning for a type
# but this meaning is not exposed into the API, just a number is throw
# This mapping aims to write the meaning in Gnocchi instead of a number

TYPE_VALUES_NAMES_MAPPING = {
    # https://github.com/collectd/collectd/blob/master/src/load.c#L91
    # https://github.com/collectd/collectd/blob/master/src/load.c#L113
    "load": ["-1min", "-5min", "-15min"],

    # https://github.com/collectd/collectd/blob/master/src/disk.c#L275
    # https://github.com/collectd/collectd/blob/master/src/disk.c#L524
    # https://github.com/collectd/collectd/blob/master/src/virt.c#L758
    # https://github.com/collectd/collectd/blob/master/src/processes.c#L871
    "disk_octets": ["-read", "-write"],
    "disk_ops": ["-read", "-write"],
    "disk_time": ["-read", "-write"],
    "disk_merged": ["-read", "-write"],
    # https://github.com/collectd/collectd/blob/master/src/disk.c#L292
    "disk_io_time": ["-io_time", "-weighted_time"],

    # https://github.com/collectd/collectd/blob/master/src/interface.c#L216
    # https://github.com/collectd/collectd/blob/master/src/interface.c#L266
    # https://github.com/collectd/collectd/blob/master/src/netlink.c#L244
    # https://github.com/collectd/collectd/blob/master/src/virt.c#L1563
    # https://github.com/collectd/collectd/blob/master/src/network.c#L3053
    "if_packets": ["-rx", "-tx"],
    "if_octets": ["-rx", "-tx"],
    "if_errors": ["-rx", "-tx"],
    "if_dropped": ["-rx", "-tx"],

    # https://github.com/collectd/collectd/blob/master/src/smart.c#L97
    "smart_attribute": ["-current", "-worst", "-threshold", "-pretty"],

    # https://github.com/collectd/collectd/blob/master/src/virt.c#L682
    # https://github.com/collectd/collectd/blob/master/src/processes.c#L836
    "ps_cputime": ["-user", "-system"],

    # https://github.com/collectd/collectd/blob/master/src/processes.c#L836
    "ps_count": ["-proc", "-lwp"],
    "ps_pagefaults": ["-min", "-max"],
    "io_octets": ["-read", "-write"],
    "io_ops": ["-read", "-write"],
}


def log_full_exception(func):
    def inner_func(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except exceptions.ConnectionFailure as e:
            collectd.warning(str(e))
        except Exception:
            etype, value, tb = sys.exc_info()
            for l in traceback.format_exception(etype, value, tb):
                collectd.error(l.strip())
    return inner_func


class Gnocchi(object):
    def config(self, config):
        # NOTE(sileht): Python threading system is not yet initialized here
        # FIXME(sileht): We handle only one configuration block for now
        self.conf = dict((c.key.lower(), c.values[0]) for c in
                         config.children)

    @log_full_exception
    def init(self):
        auth_mode = self.conf.get('auth_mode', 'basic').lower()
        if auth_mode == 'keystone':
            auth_url = self.conf.get("auth_url", self.conf.get("authurl"))
            if auth_url is None:
                raise RuntimeError(
                    "Please specify `auth_url` for Keystone auth_mode")

            kwargs = {}

            for arg in ("auth_url",
                        "username", "user_id",
                        "project_id", "project_name",
                        "tenant_id", "tenant_name",
                        "password",
                        "user_domain_id", "user_domain_name",
                        "project_domain_id", "project_domain_name"):
                if arg in self.conf:
                    kwargs[arg] = self.conf.get(arg)

            auth = identity.Password(**kwargs)
        elif auth_mode == "basic":
            auth = gnocchiclient.auth.GnocchiBasicPlugin(
                self.conf.get("user", "admin"),
                self.conf.get("endpoint"))
        elif auth_mode == "noauth":
            auth = gnocchiclient.auth.GnocchiNoAuthPlugin(
                self.conf.get("userid", "admin"),
                self.conf.get("projectid", "admin"),
                self.conf.get("roles", "admin"),
                self.conf.get("endpoint"))
        else:
            raise RuntimeError("Unknown auth_mode `%s'" % auth_mode)
        s = session.Session(auth=auth)
        self.g = client.Client(
            1, s,
            adapter_options=dict(
                interface=self.conf.get('interface'),
                region_name=self.conf.get('region_name'),
                endpoint_override=self.conf.get('endpoint')
            ))

        self._resource_type = self.conf.get("resourcetype", "collectd")
        self.values = []
        self.batch_size = self.conf.get("batchsize", 10)

        collectd.register_write(self.write)
        collectd.register_flush(self.flush)

    def _ensure_resource_exists(self, host_id, host):
        attrs = {"id": host_id, "host": host}
        try:
            try:
                self.g.resource.create(self._resource_type, attrs)
            except exceptions.ResourceTypeNotFound:
                self._ensure_resource_type_exists()
                self.g.resource.create(self._resource_type, attrs)
        except exceptions.ResourceAlreadyExists:
            pass

    def _ensure_resource_type_exists(self):
        try:
            self.g.resource_type.create({
                "name": self._resource_type,
                "attributes": {
                    "host": {
                        "required": True,
                        "type": "string",
                    },
                },
            })
        except exceptions.ResourceTypeAlreadyExists:
            pass

    @log_full_exception
    def write(self, values):
        self.values.append(values)

        if len(self.values) >= self.batch_size:
            self.flush(0, None)

    @staticmethod
    def _serialize_identifier(v):
        """Based of FORMAT_VL from collectd/src/daemon/common.h.

        The biggest difference is that we don't prepend the host and append the
        index of the value, and don't use slash.

        """
        # NOTE(sileht): the len of v.values is static in Collectd, so for
        # a particular type, this will always have the same len.
        n_values = len(v.values)
        if n_values <= 1:
            suffixes = [""]
        else:
            suffixes = TYPE_VALUES_NAMES_MAPPING.get(v.type)
            if suffixes is None:
                collectd.error("TYPE_VALUES_NAMES_MAPPING for (%s, %s) "
                               "does not have names, fallback to indexes. "
                               "Please report a bug to collectd-gnocchi" %
                               (v.plugin, v.type))
                suffixes = ["-%d" % i for i in range(n_values)]
            elif len(suffixes) != n_values:
                collectd.error("Expecting %d values instead of %s for %s in "
                               "TYPE_VALUES_NAMES_MAPPING, "
                               "fallback to indexes." %
                               (len(suffixes), n_values, v.type))
                suffixes = ["-%d" % i for i in range(n_values)]

        return (v.plugin + ("-" + v.plugin_instance
                            if v.plugin_instance else "")
                + "@"
                + v.type + ("-" + v.type_instance
                            if v.type_instance else ""),
                suffixes)

    @log_full_exception
    def flush(self, timeout, identifier):
        flush_before = time.time() - timeout
        to_flush = []
        not_to_flush = []
        for v in self.values:
            if ((identifier is not None and v.plugin != identifier)
               or v.time > flush_before):
                not_to_flush.append(v)
            else:
                to_flush.append(v)

        for host, values in itertools.groupby(
                to_flush, operator.attrgetter("host")):
            self._batch(host, values)

        self.values = not_to_flush

    def _batch(self, host, values):
        host_id = "collectd:" + host.replace("/", "_")
        measures = {host_id: collections.defaultdict(list)}
        for v in values:
            ident, suffixes = self._serialize_identifier(v)
            for i, value in enumerate(v.values):
                if not math.isnan(value):
                    measures[host_id][ident + suffixes[i]].append({
                        "timestamp": v.time,
                        "value": value,
                    })
        try:
            self.g.metric.batch_resources_metrics_measures(
                measures, create_metrics=True)
        except exceptions.BadRequest:
            # Create the resource and try again
            self._ensure_resource_exists(host_id, host)
            self.g.metric.batch_resources_metrics_measures(
                measures, create_metrics=True)


g = Gnocchi()
collectd.register_config(g.config)
collectd.register_init(g.init)
