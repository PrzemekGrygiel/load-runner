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

import itertools
import json
import random
import os
import time
import socket

from load_runner import remote
from load_runner import settings
from load_runner.data import iperf3
from load_runner.data import ping
from load_runner.data import cpuload

def random_pairs(clients, servers, extend=False):
    clients = list(clients)
    servers = list(servers)

    if len(clients) == 0 or len(servers) == 0:
        return []

    if extend:
        if len(servers) > len(clients):
            servers = list(itertools.cycle(servers)[0:len(clients)])
        elif len(servers) < len(clients):
            clients = list(itertools.cycle(clients)[0:len(servers)])
    random.shuffle(clients)
    random.shuffle(servers)
    return zip(clients, servers)


def iperf_pairs_zmq(test, output_file):
    tenants = test.tenants
    hvs = []
    kill_commands = []
    run_kill = ['killall', 'iperf3']

    hvs_commands = []

    collectl_start = ['collectl', '--all']
    w_stat = ['/usr/bin/w']
    cpu_stat = ['/usr/bin/screen', '-d', '-m','-S', 'cpu-monit', '/root/cpu-monit.sh', test.args.get('hv_monit', [])]
    for group in test.group_servers_by_role().values():
        for server in group:
            kill_commands.append((server.management_ip, run_kill))
            if server.hypervisor not in hvs:
                hvs.append(server.hypervisor)
                hvs_commands.append((server.hypervisor, cpu_stat))
    remote.run_commands(
        kill_commands, timeout=test.args.get('server_timeout', 30))
#Moved right after run ipoerf
    #hvs_results = remote.run_commands(
     #   hvs_commands, [],
     #   test.args.get('client_timeout', 600))
    # print hvs_results

    # Prepare servers...
    clients = {}
    server_commands = []
    run_server = ['/usr/local/bin/iperf3', '-s', '-D', '-p', '8200']
    for tenant in tenants:
        grouped_servers = tenant.group_servers_by_role()
        for server, client in random_pairs(grouped_servers['server'],
                                           grouped_servers['client']):
            clients[server.management_ip] = (client, server)
            server_commands.append(
                (server.management_ip,
                 ['ping', '-c', '1', '-W', '1', client.private_ip]))
            server_commands.append((server.management_ip, run_server))
    server_results = remote.run_commands(
        server_commands, [], test.args.get('server_timeout', 30))
   
    #Run CPU stat  collection
    hvs_results = remote.run_commands(
        hvs_commands, [],
        test.args.get('client_timeout', 600))
    print hvs_results

    # Run clients...
    client_commands = []
    additional_args = test.args.get('iperf_args', [])
    for server_address in set(r['address'] for r in server_results):
        client, server = clients[server_address]
        run_client = ['/usr/local/bin/iperf3', '-c', server.private_ip, '-p',
                      '8200', '--json']
        run_client.extend(additional_args)
        client_commands.append((client.management_ip, run_client))
    print 'Running iperf...'
    client_results = remote.run_commands(
        client_commands, iperf3.Iperf3Stats(test),
        test.args.get('client_timeout', 600))

    client_results.output(output_file)
   #added by PG
    #pg_client_commands = []
    #pg_command=['cat','/tmp/results.txt']
    #pg_client_commands.append(('1.1.1.52', pg_command))

    #Get CPU stats from Hypervisors
    hv_results = []
    hvs_commands = []
    get_cpu_stat=['cat','/tmp/results.txt']
    print "collecting CPU util from HV ..."
    for srv in hvs:
        hvs_commands.append((srv, get_cpu_stat))
    hv_results = remote.run_commands(
        hvs_commands,cpuload.CPUStats(),
        test.args.get('client_timeout', 600))
   # TODO move to output function 
    for srv in hvs:
        print socket.gethostbyaddr(srv)[0]
        hv_results.output(output_file)


def ping_pairs(test, output_file):
    ping_count = test.args.get('ping_count', 10)
    tenants = test.tenants

    # Prepare servers...
    commands = []
    for tenant in tenants:
        grouped_servers = tenant.group_servers_by_role()
        for server, client in random_pairs(grouped_servers['server'],
                                           grouped_servers['client']):
            commands.append(
                (client.management_ip,
                 ['ping', '-c', ping_count, '-W', '1', server.private_ip]))
            commands.append(
                (server.management_ip,
                 ['ping', '-c', ping_count, '-W', '1', client.private_ip]))

    print 'Running pings...'
    results = remote.run_commands(
        commands, ping.PingStats(test),
        test.args.get('timeout', ping_count * 2))

    results.output(output_file)


def iperf_gateway(test, output_file):
    # Generate list of servers
    def server_list():
        ips = ['10.119.150.' + str(i) for i in range(194, 213)]
        for port in range(5200, 5300, 2):
            for ip in ips:
                yield {'ip': ip, 'port': port}
    servers = server_list()

    # Prepare servers...
    client_commands = []
    additional_args = test.args.get('iperf_args', [])
    for tenant in test.tenants:
        grouped_servers = tenant.group_servers_by_role()
        for client, server in zip(grouped_servers['client'], servers):
            run_client1 = ['/usr/local/bin/iperf3', '-c', server['ip'],
                           '-p', server['port'], '--json']
            run_client1.extend(additional_args)
            client_commands.append((client.management_ip, run_client1))

    print len(client_commands), 'pairs generated.'

    print 'Running iperf...'
    client_results = remote.run_commands(
        client_commands, iperf3.Iperf3Stats(test),
        test.args.get('client_timeout', 600))

    client_results.output(output_file)


def iperf_pairs_duplex(test, output_file):
    tenants = test.tenants

    kill_commands = []
    run_kill = ['killall', 'iperf3']
    for group in test.group_servers_by_role().values():
        for server in group:
            kill_commands.append((server.management_ip, run_kill))
    remote.run_commands(
        kill_commands, timeout=test.args.get('server_timeout', 30))

    # Prepare servers...
    server_commands = []
    run_server = ['/usr/local/bin/iperf3', '-s', '-D', '-p', '8200']
    for group in test.group_servers_by_role().values():
        for server in group:
            server_commands.append((server.management_ip, run_server))
    remote.run_commands(server_commands,
                        timeout=test.args.get('server_timeout', 30))

    # Run clients...
    client_commands = []
    additional_args = test.args.get('iperf_args', [])
    for tenant in tenants:
        grouped_servers = tenant.group_servers_by_role()
        for server, client in random_pairs(grouped_servers['server'],
                                           grouped_servers['client']):
            run_client = ['/usr/local/bin/iperf3', '-c', server.private_ip,
                          '-p', '8200', '--json']
            run_client.extend(additional_args)
            run_server = ['/usr/local/bin/iperf3', '-c', client.private_ip,
                          '-p', '8200', '--json']
            run_server.extend(additional_args)

            client_commands.append((client.management_ip, run_client))
            client_commands.append((server.management_ip, run_server))

    print 'Running iperf...'
    client_results = remote.run_commands(
        client_commands, iperf3.Iperf3Stats(test),
        test.args.get('client_timeout', 600))

    client_results.output(output_file)
