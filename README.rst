==================
 collectd-gnocchi
==================
.. image:: https://img.shields.io/pypi/v/collectd-gnocchi.svg
    :target: https://pypi.python.org/pypi/collectd-gnocchi

.. image:: https://img.shields.io/travis/gnocchixyz/collectd-gnocchi.svg
    :target: https://travis-ci.org/gnocchixyz/collectd-gnocchi

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

.. include:: collectd-gnocchi.conf

You can also copy the provided `collectd-gnocchi.conf` from this repository in
e.g. `/etc/collectd.d` if your distribution supports it.

.. _`collectd`: http://collectd.org
.. _`Gnocchi`: http://gnocchi.xyz
.. _`PyPI`: http://pypi.python.org

