# Copyright 2014 Symantec.
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

import errno
import itertools
import netaddr
import os
import random
import select
import socket
import struct
import sys
import time
import traceback
import yaml

from load_runner import api_helpers
from load_runner import settings

management_net = netaddr.IPNetwork(settings.MANAGEMENT_CIDR)
private_net = netaddr.IPNetwork(settings.PRIVATE_CIDR)
POLL_TIMEOUT = 5000

net_num = 0


def get_net_num():
    global net_num
    net_num += 1
    return net_num


def loop_with_timeout(pred, timeout, deadline=None):
    start = time.time()
    while time.time() - start < timeout:
        result = pred()
        if result:
            return result
        if deadline is not None and time.time() > deadline:
            break
        print 'Sleeping 10 seconds'
        time.sleep(10)
    return result


class LoadRunner(object):
    def __init__(self):
        self.next_net_base = netaddr.IPAddress(private_net.ip)
        self.user = None
        self.keyfile = None
        self.key_name = None
        self.password = None
        self.run_dir = '/tmp'
        self.tests = []
        self.results = {}

    def allocate_cidr(self):
        base = self.next_net_base
        self.next_net_base += 0x1000
        return base.format() + '/20'

    def load_description(self, config_file):
        with open(config_file, 'r') as f:
            config = yaml.load(f)

        self.user = config.get('username')
        self.password = config.get('password')
        self.key_name = config.get('keyname')
        self.keyfile = config.get('keyfile')
        for test in config['tests']:
            self.tests.append(Test(self, test))

    def prepare_environment(self):
        for test in self.tests:
            test.prepare_environment()

    def list_tests(self):
        for test in self.tests:
            print test.name

    def run_tests(self, tests_to_run=None, output_file=None):
        if tests_to_run is None:
            tests_to_run = []
        test_names = [x.name for x in self.tests]
        for test in tests_to_run:
            if test not in test_names:
                print ("Warning: test %s cannot be found in tests "
                       "library." % test)
        for test in self.tests:
            if tests_to_run and test.name not in tests_to_run:
                continue

            print "Running test:", test.name
            try:
                test.prepare_environment()
                test.initialize()
                test.run_test(output_file)
            except Exception:
                print "Test failed:", test.name
                traceback.print_exc()
            finally:
                #try:
                #    test.teardown_environment()
                #except Exception:
                #    print "Teardown for test '%s' failed!" % test.name
                #    traceback.print_exc()
                pass


class BaseObject(object):
    def __init__(self, data, parent):
        if parent is not None:
            parent_ags = parent.availability_zones
        else:
            parent_ags = itertools.repeat(None)
        availability_zones = data.get('availability_zones')
        if availability_zones:
            self.availability_zones = itertools.cycle(availability_zones)
        else:
            self.availability_zones = parent_ags

    def prepare_environment(self):
        for child in self.get_children():
            child.prepare_environment()

    def initialize(self):
        for child in self.get_children():
            child.initialize()

    def deinitialize(self):
        for child in self.get_children():
            child.deinitialize()

    def group_servers_by_role(self):
        grouped_servers = {}
        for child in self.get_children():
            gs = child.group_servers_by_role()
            for role, servers in gs.items():
                role_servers = grouped_servers.setdefault(role, [])
                role_servers.extend(s for s in servers if s.management_ip)
        return grouped_servers


class Test(BaseObject):
    def __init__(self, load_runner, data):
        super(Test, self).__init__(data, None)
        self.load_runner = load_runner
        self.name = data['name']
        self.procedure = data['procedure']
        self.timeout = data.get('timeout', settings.TEST_TIMEOUT)
        self.args = data.get('args', {})

        # Create tenants
        self.tenants = []
        for tenant_desc in data['tenants']:
            tenant_prefix = tenant_desc['name']
            for i in range(tenant_desc.get('count', 1)):
                tenant_name = tenant_prefix + str(i)
                tenant = Tenant(self, tenant_desc, tenant_name)
                self.tenants.append(tenant)

    def get_children(self):
        return self.tenants

    def run_test(self, output_file):
        print("run_test()")
        module_name, func_name = self.procedure.rsplit('.', 1)
        print("module_name %s, func_name: %s" % (module_name, func_name))
        try:
            __import__(module_name)
        except Exception:
            traceback.print_exc()
            return

        module = sys.modules[module_name]
        func = getattr(module, func_name, None)
        if func is None:
            print "Function '%s' is not found" % self.procedure
            return

        func(self, output_file)

    def teardown_environment(self):
        self.remove_instances()
        self.wait_remove_instances()
        self.remove_routers()
        self.remove_networks()
        self.remove_tenants()

    def remove_instances(self):
        for tenant in self.tenants:
            tenant.remove_instances()

    def wait_remove_instances(self):
        for tenant in self.tenants:
            tenant.wait_remove_instances()

    def remove_routers(self):
        for tenant in self.tenants:
            tenant.remove_router()

    def remove_networks(self):
        for tenant in self.tenants:
            tenant.remove_networks()

    def remove_tenants(self):
        for tenant in self.tenants:
            tenant.remove()

    def store_result(self, result):
        self.load_runner.results[self.name] = result


class Tenant(BaseObject):
    def __init__(self, test, data, name):
        super(Tenant, self).__init__(data, test)
        self.test = test
        self.name = name
        self.tenant_id = None
        self.router_id = None
        self.router_args = data.get('router_args', {})

        # Create networks
        network_index = 0
        self.networks = []
        for n in data['networks']:
            network_count = int(n.get('count', 1))
            for i in range(network_count):
                if network_count > 1:
                    network_name = '{0}{1}'.format(n['name'], network_index)
                else:
                    network_name = n['name']
                self.networks.append(Network(self, n, network_name))
                network_index += 1
        self.available_servers = []
        self.connected_servers = {}

    def get_children(self):
        return self.networks

    def prepare_environment(self):
        self.tenant_id = api_helpers.get_or_create_tenant(self.name)
        print("TenantId: %s" % self.tenant_id)
        self.available_servers = api_helpers.get_servers(self.tenant_id)
        print("Available_servers: %s" % self.available_servers)
        random.shuffle(self.available_servers)

        super(Tenant, self).prepare_environment()
        api_helpers.ensure_default_sg_state(self.tenant_id)

        self.router_id = api_helpers.get_or_create_router(
            self.tenant_id, 'router', self.router_args)
        for network in self.networks:
            if network.subnet_id is not None:
                api_helpers.add_router_interface(
                    self.router_id, network.network_id, network.subnet_id)

    def remove(self):
        if self.tenant_id:
            api_helpers.delete_tenant(self.tenant_id)
            self.tenant_id = None

    def remove_instances(self):
        for network in self.networks:
            network.remove_instances()

    def wait_remove_instances(self):
        for network in self.networks:
            network.wait_remove_instances()

    def remove_router(self):
        if self.router_id is not None:
            for network in self.networks:
                if network.subnet_id is not None:
                    api_helpers.remove_router_interface(self.router_id,
                                                        network.subnet_id)
            api_helpers.delete_router(self.router_id)
            self.router_id = None

    def remove_networks(self):
        for network in self.networks:
            network.remove()

    def initialize(self):
        deadline = time.time() + settings.ACTIVATION_TIMEOUT
        while time.time() < deadline:
            active_servers = api_helpers.get_servers(self.tenant_id)
            if all(s.status in ('ACTIVE', 'ERROR')
                   for s in active_servers):
                break
            print 'Waiting', sum(1 for s in active_servers
                                 if s.status not in ('ACTIVE', 'ERROR')), 'VMs'
            time.sleep(5)
        for network in self.networks:
            network.initialize(dict((server.id, server)
                                    for server in active_servers
                                    if server.status == 'ACTIVE'))

    def allocate_server(self, network_id, name, key_name, availability_zone,
                        floating_ip=None):
        # Split availability zone and host
        print "started allocation"
        if availability_zone:
            az_host = availability_zone.rsplit(':', 1)
            az = az_host[0]
            if len(az_host) > 1:
                host = az_host[1]
            else:
                host = None
        else:
            az = None
            host = None

        # Find already running server that fits requested arguments
        for i, server in enumerate(self.available_servers):
            server_host = server._info['OS-EXT-SRV-ATTR:host']
            server_az = server._info['OS-EXT-AZ:availability_zone']
            if host is not None:
                if host != server_host:
                    continue
            elif az is not None:
                if az != server_az:
                    continue
            if not self.is_server_connected(server.id, network_id):
                continue
            data_ip = api_helpers.get_data_ip(
                server.id, network_id, floating_ip)
            if data_ip is None:
                continue
            self.available_servers.pop(i)
            mgmt = server.addresses[settings.MANAGEMENT_NAME]
            print "finished allocation"
            hv_name = server._info['OS-EXT-SRV-ATTR:hypervisor_hostname']
            hv = socket.gethostbyname(hv_name)
            print server._info['OS-EXT-SRV-ATTR:hypervisor_hostname'], hv
            return server.id, data_ip, mgmt[0]['addr'], hv
        print "spawning new server"
        # If no luck, then allocate new server
        return api_helpers.create_server(self.tenant_id, network_id, name,
                                         key_name, availability_zone,
                                         floating_ip=floating_ip)

    def is_server_connected(self, server_id, network_id):
        network_servers = self.connected_servers.get(network_id)
        if network_servers is None:
            network_servers = api_helpers.get_network_servers(network_id)
            self.connected_servers[network_id] = network_servers
        return server_id in network_servers


class Network(BaseObject):
    def __init__(self, tenant, data, name=None):
        super(Network, self).__init__(data, tenant)
        self.tenant = tenant
        self.name = data['name'] if not name else name
        self.network_id = data.get('network_id')
        self.subnet_id = data.get('subnet_id')
        self.created_network = False
        self.started_servers = []

        # Create servers
        self.servers = []
        test_name = self.tenant.test.name
        #print data['servers']
        for server_desc in data['servers']:
            floating_ip = server_desc.get('floating_ip')
            availability_zones = server_desc.get('availability_zones')
            if availability_zones:
                if isinstance(availability_zones, list):
                    availability_zones = itertools.cycle(availability_zones)
                    server_desc['availability_zones'] = availability_zones
            elif self.availability_zones:
                availability_zones = self.availability_zones
            if availability_zones:
                av_zones = availability_zones
            else:
                av_zones = itertools.repeat(None)

            role = server_desc['role']
            server_prefix = test_name + '-'
            for i, avail_zone in zip(range(server_desc.get('count', 1)),
                                     av_zones):
                server_name = server_prefix + os.urandom(3).encode('hex')
                server = Server(self, server_name, role, avail_zone,
                                floating_ip)
                #print server
                self.servers.append(server)

    def get_children(self):
        return self.servers

    def prepare_environment(self):
        tenant_id = self.tenant.tenant_id
        if self.network_id is None:
            self.network_id = api_helpers.get_or_create_network(
                tenant_id, self.name)
            self.created_network = True
        if self.subnet_id is None:
            cidr = self.tenant.test.load_runner.allocate_cidr()
            self.subnet_id = api_helpers.get_or_create_subnet(
                tenant_id, self.network_id, self.name, cidr)
        super(Network, self).prepare_environment()

    def remove(self):
        if self.network_id is not None and self.created_network:
            api_helpers.delete_network(self.network_id)
            self.network_id = None
            self.subnet_id = None

    def group_servers_by_role(self):
        grouped_servers = {}
        for server in self.servers:
            grouped_servers.setdefault(server.role, []).append(server)
        return grouped_servers

    def remove_instances(self):
        for server in self.started_servers:
            server.remove()

    def wait_remove_instances(self):
        for server in self.servers:
            server.deinitialize()

    def initialize(self, active_servers):
        self.started_servers = self.servers
        self.servers = []
        for server in self.started_servers:
            if server.server_id not in active_servers:
                continue
            self.servers.append(server)
        self.servers = self._check_boot(self.servers, settings.BOOT_TIMEOUT)
        print len(self.servers), 'out of', len(self.started_servers), \
            'servers booted successfully'

    def _check_boot(self, servers, timeout):
        poller = select.poll()
        fd_to_socket = {}

        def make_connection(server):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setblocking(0)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER,
                         struct.pack('ii', 1, 0))
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            poller.register(s, select.POLLIN | select.POLLPRI |
                            select.POLLHUP | select.POLLERR)
            err = s.connect_ex((server.management_ip, 5500))
            if err in (0, errno.EINPROGRESS):
                fd_to_socket[s.fileno()] = (s, server)
                return s
            else:
                poller.unregister(s)
                s.close()
                return None

        for server in (s for s in servers if s.management_ip):
            print 'Checking connection to', server.management_ip
            make_connection(server)

        servers_ready = []

        deadline = time.time() + timeout
        while fd_to_socket and (timeout == 0 or time.time() < deadline):
            events = poller.poll(POLL_TIMEOUT)
            for fd, flag in events:
                if flag == select.POLLNVAL:
                    continue
                s, server = fd_to_socket.pop(fd)
                if flag & (select.POLLERR | select.POLLHUP):
                    poller.unregister(fd)
                    make_connection(server)
                else:
                    servers_ready.append(server)
                s.close()
            if fd_to_socket:
                print len(servers_ready), 'of', len(self.servers), \
                    'servers ready'
                time.sleep(1)

        not_ready = set(self.servers) - set(servers_ready)
        for s in not_ready:
            print 'Not responding:', s.management_ip
        print servers_ready
        return servers_ready


class Server(object):
    def __init__(self, network, name, role, availability_zone, floating_ip):
        self.floating_ip = floating_ip
        self.network = network
        self.name = name
        self.role = role
        self.availability_zone = availability_zone
        self.server_id = None
        self.stashed_server_id = None
        self.private_ip = None
        self.management_ip = None
        self.start_time = None
        self.hypervisor = None

    def prepare_environment(self):
        tenant = self.network.tenant
        key_name = tenant.test.load_runner.key_name
        network_id = self.network.network_id
        server_info = tenant.allocate_server(network_id, self.name, key_name,
                                             self.availability_zone,
                                             self.floating_ip)
        print server_info
        self.server_id, self.private_ip, self.management_ip, self.hypervisor = server_info
        self.start_time = time.time()

    def remove(self):
        if self.server_id is not None:
            api_helpers.terminate_server(self.server_id)
            self.stashed_server_id = self.server_id
            self.server_id = None

    def deinitialize(self):
        self._wait_terminate()
        self.management_ip = None
        self.private_ip = None
        self.stashed_server_id = None

    def _wait_terminate(self):
        if self.stashed_server_id is None:
            return

        print "Waiting terminate: %s" % self.stashed_server_id

        def action():
            server = api_helpers.get_server(self.stashed_server_id)
            if server is None:
                return True
            if server.status == 'ERROR':
                print "VM %s ended up in error state" % self.name
                return True
            return False

        loop_with_timeout(action, settings.ACTIVATION_TIMEOUT)
