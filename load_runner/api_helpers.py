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

from keystoneclient.v2_0 import client as keystone
from neutronclient.neutron import client as neutron
from novaclient.v1_1 import client as nova
from novaclient import exceptions as nova_exceptions
from keystoneclient.apiclient import exceptions as keystone_exceptions


import settings
import time
import traceback

keystone_client = None
neutron_client = None
nova_clients = {}
servers = {}

class ServersSpawner:
    usable_availability_zones = []
    heuristics = [1, 1, 1, 1, 10, 20]
    instances = []
    current_heur = 0
 
    @classmethod
    def spawn_server(cls, tenant_id, network_id, key_name, availability_zone, scheduler_hints):
        client = get_nova_client(tenant_id)
        server = client.servers.create(
            name, settings.IMAGE_ID, settings.FLAVOR_ID,
            nics=[{'net-id': settings.MANAGEMENT_NETWORK_ID},
                 {'net-id': network_id}],
            key_name=key_name,
            availability_zone=availability_zone,
            scheduler_hints=scheduler_hints)


def get_keystone_client():
    global keystone_client
    if keystone_client is None:
        keystone_client = keystone.Client(
            token=settings.OS_TOKEN, endpoint=settings.OS_SERVICE_ENDPOINT)
    return keystone_client


def get_neutron_client():
    global neutron_client
    if neutron_client is None:
        neutron_client = neutron.Client(
            '2.0', auth_url=settings.OS_AUTH_URL,
            username=settings.OS_USERNAME, password=settings.OS_PASSWORD,
            tenant_name=settings.OS_TENANT)
    return neutron_client


def get_nova_client(tenant_id=None):
    global nova_clients
    client = nova_clients.get(tenant_id)
    if client is None:
        if tenant_id is None:
            tenant_name = settings.OS_TENANT
        else:
            tenant_name = None
        client = nova.Client(settings.OS_USERNAME, settings.OS_PASSWORD,
                             tenant_name, settings.OS_AUTH_URL,
                             tenant_id=tenant_id)
        nova_clients[tenant_id] = client
    return client


def get_or_create_tenant(tenant_name):
    client = get_keystone_client()

    try:
        tenant = client.tenants.find(name=tenant_name)
    except keystone_exceptions.NotFound:
        tenant = client.tenants.create(tenant_name)
        time.sleep(4)

    def user_ensure_role(name):
        for role in client.roles.roles_for_user(user_id, tenant.id):
            if role.name == name:
                return
        try:
            role_id = client.roles.find(name=name).id
        except keystone_exceptions.NotFound:
            return
        client.roles.add_user_role(user_id, role_id, tenant=tenant.id)

    user_id = client.users.find(name=settings.OS_USERNAME).id
    user_ensure_role('Member')
    user_ensure_role('admin')
    user_ensure_role('nova_rw')

    if settings.UPDATE_NEUTRON_QUOTAS:
        get_neutron_client().update_quota(
            tenant.id, {
                'quota': {
                    'network': 100000,
                    'floatingip': 500000,
                    'security_group_rule': 500000,
                    'security_group': 500000,
                    'router': 10,
                    'port': 500000,
                    'subnet': 100000
                }
            })
    # get_nova_client().quotas.update(
    #     tenant.id, metadata_items=-1, injected_file_content_bytes=-1, ram=-1,
    #     floating_ips=-1, security_group_rules=-1, instances=-1, key_pairs=-1,
    #     injected_files=-1, cores=-1, fixed_ips=-1,
    #     injected_file_path_bytes=255, security_groups=-1)
    return tenant.id


def delete_tenant(tenant_id):
    client = get_keystone_client()
    client.tenants.delete(tenant_id)


def get_or_create_network(tenant_id, network_name):
    client = get_neutron_client()
    existing = client.list_networks(
        name=network_name, tenant_id=tenant_id).get('networks', [])
    if not existing:
        network = client.create_network({'network': {
            'name': network_name,
            'admin_state_up': True,
            'tenant_id': tenant_id}})['network']
    else:
        network = existing[0]
    return network['id']


def delete_network(network_id):
    client = get_neutron_client()
    client.delete_network(network_id)


def get_or_create_subnet(tenant_id, network_id, network_name, cidr):
    client = get_neutron_client()
    existing = client.list_subnets(network_id=network_id).get('subnets', [])
    if existing:
        if existing[0]['cidr'] != cidr:
            raise RuntimeError('Subnet in existing network is different from '
                               'requested. Tear down environment and set it up'
                               ' again to change network CIDRs.')
        else:
            return existing[0]['id']
    subnet = client.create_subnet({
        'subnet': {
            'name': network_name,
            'network_id': network_id,
            'tenant_id': tenant_id,
            'enable_dhcp': True,
            'dns_nameservers': ['8.8.8.8'],
            'cidr': cidr,
            'ip_version': 4
        }
    })
    return subnet['subnet']['id']


def create_server(tenant_id, network_id, name, key_name,
                  availability_zone=None, scheduler_hints=None,
                  floating_ip=None):
    if settings.USE_DHCP:
        return create_server_dhcp(
            tenant_id, network_id, name, key_name, availability_zone,
            scheduler_hints, floating_ip=floating_ip)
    else:
        return create_server_config_drive(
            tenant_id, network_id, name, key_name, availability_zone,
            scheduler_hints, floating_ip=floating_ip)


def create_server_config_drive(tenant_id, network_id, name, key_name,
                               availability_zone=None, scheduler_hints=None,
                               floating_ip=None):
    """
    Function that creates server with network configuration using config
    drive.
    """
    if settings.SPAWN_DELAY:
        time.sleep(settings.SPAWN_DELAY)
    neutron_client = get_neutron_client()

    MAX_TRIES = 15
    tries = 0
    while tries < MAX_TRIES:
        tries += 1
        try:
            private_port = neutron_client.create_port(
                {'port': {'tenant_id': tenant_id, 'network_id': network_id}})
            private_port = private_port['port']
            break
        except:
            traceback.print_exc()
            if tries >= MAX_TRIES:
                raise
            print 'For', tries, 'time, sleeping 20 sec...'
            time.sleep(20)

    tries = 0
    while tries < MAX_TRIES:
        tries += 1
        try:
            management_port = neutron_client.create_port(
                {'port': {'tenant_id': tenant_id,
                          'network_id': settings.MANAGEMENT_NETWORK_ID}})
            management_port = management_port['port']
            break
        except:
            traceback.print_exc()
            if tries >= MAX_TRIES:
                raise
            print 'For', tries, 'time, sleeping 20 sec...'
            time.sleep(20)

    private_ip = private_port['fixed_ips'][0]['ip_address']
    management_ip = management_port['fixed_ips'][0]['ip_address']

    client = get_nova_client(tenant_id)
    server = client.servers.create(
        name, settings.IMAGE_ID, settings.FLAVOR_ID,
        nics=[{'port-id': management_port['id']},
              {'port-id': private_port['id']}],
        meta={'management_ip': management_ip,
              'management_mac': management_port['mac_address'],
              'private_ip': private_ip,
              'private_mac': private_port['mac_address']},
        config_drive=True,
        key_name=key_name,
        availability_zone=availability_zone,
        scheduler_hints=scheduler_hints)
    return server.id, private_ip, management_ip


def create_server_dhcp(tenant_id, network_id, name, key_name,
                       availability_zone=None, scheduler_hints=None,
                       floating_ip=None):
    print "started creating server"
    if settings.SPAWN_DELAY:
        time.sleep(settings.SPAWN_DELAY)

    client = get_nova_client(tenant_id)
    server = client.servers.create(
        name, settings.IMAGE_ID, settings.FLAVOR_ID,
        nics=[{'net-id': settings.MANAGEMENT_NETWORK_ID},
              {'net-id': network_id}],
        key_name=key_name,
        availability_zone=availability_zone,
        scheduler_hints=scheduler_hints)

    while True:
        t = time.time()
        server = client.servers.get(server.id)
        if server.status == 'ERROR':
            raise Exception("Server %s failed to spawn"%server.id)
        if hasattr(server, 'networks'):
            try:
                server_nets = server.networks
                management_ip = server_nets.pop(settings.MANAGEMENT_NAME)[0]
                private_ip = server_nets.values()[0][0]
                break
            except Exception, e:
                pass
        time.sleep(0.1)
        print (time.time() - t)

    if floating_ip is not None:
        fip = get_free_floatingip(tenant_id, floating_ip)
        if fip is None:
            fip = create_free_floatingip(tenant_id, floating_ip)
        assign_floating_ip(fip, server.id, network_id)

    #server_nets = server.networks
    #management_ip = server_nets.pop(settings.MANAGEMENT_NAME)[0]
    #private_ip = server_nets.values()[0][0]
    print "finished creating server"
    print "{} {} {}" .format(server.id, private_ip, management_ip)
    print server._info
    return server.id, private_ip, management_ip


def terminate_server(server_id):
    client = get_nova_client()
    client.servers.delete(server_id)


def get_server(server_id):
    client = get_nova_client()
    try:
        server = client.servers.get(server_id)
        return server
    except nova_exceptions.NotFound:
        return None


def get_or_create_router(tenant_id, name, args):
    client = get_neutron_client()
    routers = client.list_routers(
        tenant_id=tenant_id, name=name).get('routers', [])
    if routers:
        return routers[0]['id']
    else:
        # Create router and connect it to all the networks
        data = dict(args.items())
        data['tenant_id'] = tenant_id
        data['name'] = name
        router = client.create_router(dict(router=data))
        return router['router']['id']


def delete_router(router_id):
    client = get_neutron_client()
    client.delete_router(router_id)


def add_router_interface(router_id, network_id, subnet_id):
    client = get_neutron_client()
    for port in client.list_ports(network_id=network_id).get('ports', []):
        if port['device_owner'] != 'network:router_interface':
            continue
        for fip in port['fixed_ips']:
            if fip['subnet_id'] == subnet_id:
                other_router_id = port['device_id']
                if other_router_id == router_id:
                    return
                client.remove_interface_router(
                    other_router_id, {'subnet_id': subnet_id})
                break
    client.add_interface_router(router_id, {'subnet_id': subnet_id})


def remove_router_interface(router_id, subnet_id):
    client = get_neutron_client()
    client.remove_interface_router(router_id, {'subnet_id': subnet_id})


def get_servers(tenant_id):
    client = get_nova_client(tenant_id)
    return [s for s in client.servers.list(detailed=True)
            if s.status == 'ACTIVE']


def ensure_default_sg_state(tenant_id):
    client = get_neutron_client()
    # Add 'allow all ingress ipv4 traffic' rule to default security group
    security_groups = client.list_security_groups(
        tenant_id=tenant_id, name='default').get('security_groups', [])
    security_group = security_groups[0]
    # Remove rules with remote_group_id or IPv6
    need_allow = set(('ingress', 'egress'))
    for rule in security_group['security_group_rules']:
        if rule['remote_group_id'] is not None or rule['ethertype'] != 'IPv4':
            client.delete_security_group_rule(rule['id'])
        elif (rule['direction'] == 'ingress' and
              rule['remote_ip_prefix'] == '0.0.0.0/0'):
            need_allow.discard('ingress')
        elif (rule['direction'] == 'egress' and
              rule['remote_ip_prefix'] == '0.0.0.0/0'):
            need_allow.discard('egress')
    # Add allow all security group
    for direction in need_allow:
        client.create_security_group_rule({
            'security_group_rule': {
                'security_group_id': security_group['id'],
                'direction': direction,
                'ethertype': 'IPv4',
                'tenant_id': tenant_id,
                'remote_ip_prefix': '0.0.0.0/0'
            }
        })


def get_ports(tenant_id):
    client = get_neutron_client()
    result = {}
    ports = client.list_ports(tenant_id=tenant_id)['ports']
    for port in ports:
        if port['device_owner'].startswith('network:'):
            continue
        result.setdefault(port['device_id'], []).append(port['network_id'])
    return result

def get_network_servers(network_id):
    client = get_neutron_client()
    result = set()
    ports = client.list_ports(network_id=network_id)['ports']
    for port in ports:
        if port['device_owner'].startswith('network:'):
            continue
        if port['device_owner'].startswith('neutron:'):
            continue
        result.add(port['device_id'])
    return result


fips = {}

def get_free_floatingip(tenant_id, network_id):
    global fips
    client = get_neutron_client()
    if not fips.has_key(tenant_id+network_id):
        fips[tenant_id+network_id] = client.list_floatingips(tenant_id=tenant_id)['floatingips']
    for fip in fips[tenant_id+network_id]:
        if fip['port_id'] is None:
            fips[tenant_id+network_id].remove(fip)
            return fip
    return None


def create_free_floatingip(tenant_id, network_id):
    client = get_neutron_client()
    return client.create_floatingip(
        dict(floatingip=dict(tenant_id=tenant_id,
                             floating_network_id=network_id)))['floatingip']


def assign_floating_ip(fip, server_id, network_id):
    client = get_neutron_client()
    ports = client.list_ports(device_id=server_id)['ports']
    for port in ports:
        if port['network_id'] == network_id:
            break
    else:
        raise RuntimeError('Failed to find port in net {0} for server '
                           '{1}'.format(network_id, server_id))
    client.update_floatingip(
        fip['id'],
        dict(floatingip={
            'port_id': port['id'],
            'fixed_ip_address': port['fixed_ips'][0]['ip_address']}))


all_ports = {}

def get_data_ip(server_id, network_id, floating_ip):
    x = time.time()
    client = get_neutron_client()

    ports = all_ports.get(server_id)
    if ports is None:
        ports1 = client.list_ports()['ports']
        for p in ports1:
            all_ports.setdefault(p['device_id'], []).append(p)
        ports = all_ports.get(server_id, [])

    #ports = client.list_ports(device_id=server_id)['ports']
    for port in ports:
        if port['network_id'] == network_id:
            break
    else:
        raise RuntimeError('Failed to find port in net {0} for server '
                           '{1}'.format(network_id, server_id))

    print 'took', (time.time() - x)

    if floating_ip is None or True:
        return port['fixed_ips'][0]['ip_address']

    fips = client.list_floatingips(port_id=port['id'])['floatingips']
    for fip in fips:
        if fip['port_id'] == port['id']:
            return fip['floating_ip_address']

    print 'took', (time.time() - x)

    return None
