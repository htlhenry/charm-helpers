# Copyright 2014-2015 Canonical Limited.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

''' Helpers for interacting with OpenvSwitch '''
import subprocess
import os
import netifaces
from charmhelpers.core.hookenv import (
    log, WARNING, INFO
)
from charmhelpers.core.host import (
    service
)


def add_bridge(name, datapath_type=None):
    ''' Add the named bridge to openvswitch '''
    log('Creating bridge {}'.format(name))
    cmd = ["ovs-vsctl", "--", "--may-exist", "add-br", name]
    if datapath_type is not None:
        cmd += ['--', 'set', 'bridge', name,
                'datapath_type={}'.format(datapath_type)]
    subprocess.check_call(cmd)


def del_bridge(name):
    ''' Delete the named bridge from openvswitch '''
    log('Deleting bridge {}'.format(name))
    subprocess.check_call(["ovs-vsctl", "--", "--if-exists", "del-br", name])


def add_bridge_port(name, port, promisc=False):
    ''' Add a port to the named openvswitch bridge '''
    log('Adding port {} to bridge {}'.format(port, name))
    subprocess.check_call(["ovs-vsctl", "--", "--may-exist", "add-port",
                           name, port])
    subprocess.check_call(["ip", "link", "set", port, "up"])
    if promisc:
        subprocess.check_call(["ip", "link", "set", port, "promisc", "on"])
    else:
        subprocess.check_call(["ip", "link", "set", port, "promisc", "off"])


def del_bridge_port(name, port):
    ''' Delete a port from the named openvswitch bridge '''
    log('Deleting port {} from bridge {}'.format(port, name))
    subprocess.check_call(["ovs-vsctl", "--", "--if-exists", "del-port",
                           name, port])
    subprocess.check_call(["ip", "link", "set", port, "down"])
    subprocess.check_call(["ip", "link", "set", port, "promisc", "off"])


def add_ovsbridge_linuxbridge(name, bridge):
    ''' Add linux bridge to the named openvswitch bridge '''
    ovsbridge_port = "veth-" + name
    linuxbridge_port = "veth-" + bridge
    log('Adding linuxbridge {} to ovsbridge {}'.format(bridge, name), level=INFO)
    interfaces = netifaces.interfaces()
    for interface in interfaces:
        if interface == ovsbridge_port or interface == linuxbridge_port:
            log('Interface {} already exists'.format(interface), level=INFO)
            return

    with open('/etc/network/interfaces.d/{}.cfg'.format(linuxbridge_port), 'w') as config:
        config.write("""\
# This veth pair is required when neutron data-port is mapped to an existing linux bridge. lp:1635067

auto {linuxbridge_port}
iface {linuxbridge_port} inet manual
    pre-up ip link add name {linuxbridge_port} type veth peer name {ovsbridge_port}
    pre-up ip link set {linuxbridge_port} master {bridge}
    pre-up ip link set {ovsbridge_port} up
    up ip link set {linuxbridge_port} up
    down ip link del {linuxbridge_port}
""".format(linuxbridge_port=linuxbridge_port, ovsbridge_port=ovsbridge_port, bridge=bridge))
        config.close()

    subprocess.check_call(["ifup", linuxbridge_port])
    add_bridge_port(name, ovsbridge_port)


def is_linuxbridge_interface(port):
    ''' Check if the interface is a linuxbridge bridge '''
    if os.path.exists('/sys/class/net/' + port + '/bridge'):
        log('Interface {} is a Linux bridge'.format(port), level=INFO)
        return True
    else:
        log('Interface {} is not a Linux bridge'.format(port), level=INFO)
        return False


def set_manager(manager):
    ''' Set the controller for the local openvswitch '''
    log('Setting manager for local ovs to {}'.format(manager))
    subprocess.check_call(['ovs-vsctl', 'set-manager',
                           'ssl:{}'.format(manager)])


CERT_PATH = '/etc/openvswitch/ovsclient-cert.pem'


def get_certificate():
    ''' Read openvswitch certificate from disk '''
    if os.path.exists(CERT_PATH):
        log('Reading ovs certificate from {}'.format(CERT_PATH))
        with open(CERT_PATH, 'r') as cert:
            full_cert = cert.read()
            begin_marker = "-----BEGIN CERTIFICATE-----"
            end_marker = "-----END CERTIFICATE-----"
            begin_index = full_cert.find(begin_marker)
            end_index = full_cert.rfind(end_marker)
            if end_index == -1 or begin_index == -1:
                raise RuntimeError("Certificate does not contain valid begin"
                                   " and end markers.")
            full_cert = full_cert[begin_index:(end_index + len(end_marker))]
            return full_cert
    else:
        log('Certificate not found', level=WARNING)
        return None


def full_restart():
    ''' Full restart and reload of openvswitch '''
    if os.path.exists('/etc/init/openvswitch-force-reload-kmod.conf'):
        service('start', 'openvswitch-force-reload-kmod')
    else:
        service('force-reload-kmod', 'openvswitch-switch')
