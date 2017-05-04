# -*- encoding: utf-8 -*-
#
# Copyright © 2016 Red Hat, Inc
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
import operator
import time

import collectd
import gnocchiclient.auth
from gnocchiclient import client
from gnocchiclient import exceptions
from gnocchiclient import utils
from keystoneauth1 import identity
from keystoneauth1 import session


class Gnocchi(object):

    def config(self, config):
        conf = dict((c.key.lower(), c.values[0]) for c in config.children)
        auth_mode = conf.get('auth_mode', 'basic').lower()
        if auth_mode == 'keystone':
            authurl = conf.get("authurl")
            if authurl is None:
                raise RuntimeError(
                    "Please specify `authurl` for Keystone auth_mode")

            kwargs = {}

            for arg in ("auth_url",
                        "username", "user_id",
                        "project_id", "project_name",
                        "tenant_id", "tenant_name",
                        "password",
                        "user_domain_id", "user_domain_name",
                        "project_domain_id", "project_domain_name"):
                if arg in conf:
                    kwargs[arg] = conf.get(arg)

            auth = identity.Password(**kwargs)
        elif auth_mode == "basic":
            auth = gnocchiclient.auth.GnocchiBasicPlugin(
                conf.get("user", "admin"),
                conf.get("endpoint"))
        elif auth_mode == "noauth":
            auth = gnocchiclient.auth.GnocchiNoAuthPlugin(
                conf.get("userid", "admin"),
                conf.get("projectid", "admin"),
                conf.get("roles", "admin"),
                conf.get("endpoint"))
        else:
            raise RuntimeError("Unknown auth_mode `%s'" % auth_mode)
        s = session.Session(auth=auth)
        self.g = client.Client(
            1, s,
            interface=conf.get('interface'),
            region_name=conf.get('region_name'),
            endpoint_override=conf.get('endpoint'))

        self._resource_type = conf.get("resourcetype", "collectd")

        try:
            self.g.resource_type.get("collectd")
        except exceptions.ResourceTypeNotFound:
            self.g.resource_type.create({
                "name": self._resource_type,
                "attributes": {
                    "host": {
                        "required": True,
                        "type": "string",
                    },
                },
            })

        self.values = []
        self.batch_size = conf.get("batchsize", 10)

    def write(self, values):
        self.values.append(values)

        if len(self.values) >= self.batch_size:
            self.flush(0, None)

    @staticmethod
    def _serialize_identifier(index, v):
        """Based of FORMAT_VL from collectd/src/daemon/common.h.

        The biggest difference is that we don't prepend the host and append the
        index of the value, and don't use slash.

        """
        return (v.plugin + ("-" + v.plugin_instance
                            if v.plugin_instance else "")
                + "@"
                + v.type + ("-" + v.type_instance
                            if v.type_instance else "")
                + "-" + str(index))

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
            host_id = "collectd:" + host.replace("/", "_")
            measures = {host_id: collections.defaultdict(list)}
            for value_obj in values:
                for i, value in enumerate(value_obj.values):
                    measures[host_id][
                        self._serialize_identifier(i, value_obj)].append({
                            "timestamp": v.time,
                            "value": value,
                        })
            try:
                self.g.metric.batch_resources_metrics_measures(
                    measures, create_metrics=True)
            except exceptions.BadRequest:
                # Create the resource and try again
                self.g.resource.create(self._resource_type, {
                    "id": host_id,
                    "host": host,
                })
                self.g.metric.batch_resources_metrics_measures(
                    measures, create_metrics=True)

        self.values = not_to_flush


g = Gnocchi()
collectd.register_config(g.config)
collectd.register_write(g.write)
collectd.register_flush(g.flush)
