==================
 collectd-gnocchi
==================
.. image:: https://img.shields.io/pypi/v/collectd-gnocchi.svg
    :target: https://pypi.python.org/pypi/collectd-gnocchi

.. image:: https://img.shields.io/pypi/dm/collectd-gnocchi.svg
    :target: https://pypi.python.org/pypi/collectd-gnocchi

This is an output plugin for `collectd`_ that send metrics to `Gnocchi`_. It
will create a resource type named _collectd_ (by default) and a new resource
for each of the host monitored.

Each host will have a list of metrics created dynamically using the following
name convention:

  plugin-plugin_instance/type-type_instance-value_number

In order for the metric to be created correctly, be sure that you have matching
`archive policies rules`_.

.. _archive policies rules: http://gnocchi.xyz/rest.html#archive-policy-rule


Installation
============

This is a regular Python package that you can install via `PyPI`_ using::

  pip install collectd-gnocchi

Or from sources using::

  pip install .


In order to use this plugin you will need a server running the **Gnocchi 3.1**
or greater.

Configuration
=============
Once installed, you need to enable it in your `collectd.conf` file this way::

  <Plugin python>
    Import "collectd_gnocchi"
    <Module collectd_gnocchi>
       ## Without Keystone authentication
       # Endpoint "http://localhost:8041"
       # UserId admin
       # ProjectId admin
       # Roles admin

       ## With Keystone authentication
       # AuthUrl http://keystoneurl
       # UserId admin
       # ProjectId admin
       # Password passw0rd
       # UserDomainName default
       # ProjectDomainName default
       # RegionName regionOne
       # Interface public
       # Endpoint http://localhost:8041 # if you want to override Keystone value

       ## Default resource type created by the plugin in Gnocchi
       ## to store hosts
       # ResourceType collectd

       ## Minimum number of values to batch
       # BatchSize 10
    </Module>
  </Plugin>

.. _`collectd`: http://collectd.org
.. _`Gnocchi`: http://gnocchi.xyz
.. _`PyPI`: http://pypi.python.org

