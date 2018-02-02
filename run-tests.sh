#!/bin/bash
set -e
set -x

PATH=/opt/collectd/sbin:/opt/collectd/bin:/usr/local/sbin:/usr/sbin:$PATH

cleanup () {
    set +x
    test -n "$COLLECTD_PID" && kill $COLLECTD_PID || true
    type -t pifpaf_stop >/dev/null && pifpaf_stop || true
}
trap cleanup EXIT

eval `pifpaf run gnocchi`
cd $PIFPAF_DATA
cat > collectd.conf <<EOF
Hostname "host-test"
Interval     1

LoadPlugin logfile
<Plugin logfile>
  File "stdout"
  PrintSeverity true
</Plugin>

LoadPlugin cpu
LoadPlugin interface
LoadPlugin load
LoadPlugin memory
LoadPlugin network
LoadPlugin python
<Plugin python>
  LogTraces true
  Import "collectd_gnocchi"
  ModulePath "$TRAVIS_BUILD_DIR"
  <Module collectd_gnocchi>
     Endpoint "http://localhost:8041"
  </Module>
</Plugin>
EOF

cat collectd.conf

PYTHONPATH=$TRAVIS_BUILD_DIR collectd -f -C $PWD/collectd.conf &
COLLECTD_PID=$!
sleep 10

# First check resource type collectd has been created
gnocchi resource-type list # Dump
gnocchi resource-type list -f value | grep collectd # Check

# Check localhost exists
gnocchi resource list
gnocchi resource list -f value | grep collectd:

gnocchi resource show collectd:host-test
for metric in memory@memory-used load@load-1min; do
    gnocchi resource show collectd:host-test -f value | grep "$metric"
    gnocchi measures show $metric -r collectd:host-test
    MEASURES_NB=$(gnocchi measures show $metric -r collectd:host-test -f value| wc -l)
    test $MEASURES_NB -ge 1
done

echo I: Tests passed
