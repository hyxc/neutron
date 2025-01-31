# Copyright 2013 OpenStack Foundation
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import netaddr
import six
from tempest.lib.common.utils import data_utils
from tempest import test

from neutron.tests.tempest.api import base_routers as base
from neutron.tests.tempest import config

CONF = config.CONF


class RoutersTest(base.BaseRouterTest):

    @classmethod
    @test.requires_ext(extension="router", service="network")
    def skip_checks(cls):
        super(RoutersTest, cls).skip_checks()

    @classmethod
    def resource_setup(cls):
        super(RoutersTest, cls).resource_setup()
        cls.tenant_cidr = (
            config.safe_get_config_value('network', 'project_network_cidr')
            if cls._ip_version == 4 else
            config.safe_get_config_value('network', 'project_network_v6_cidr'))

    @test.attr(type='smoke')
    @test.idempotent_id('c72c1c0c-2193-4aca-eeee-b1442640eeee')
    @test.requires_ext(extension="standard-attr-description",
                       service="network")
    def test_create_update_router_description(self):
        body = self.create_router(description='d1', router_name='test')
        self.assertEqual('d1', body['description'])
        body = self.client.show_router(body['id'])['router']
        self.assertEqual('d1', body['description'])
        body = self.client.update_router(body['id'], description='d2')
        self.assertEqual('d2', body['router']['description'])
        body = self.client.show_router(body['router']['id'])['router']
        self.assertEqual('d2', body['description'])

    @test.idempotent_id('847257cc-6afd-4154-b8fb-af49f5670ce8')
    @test.requires_ext(extension='ext-gw-mode', service='network')
    @test.attr(type='smoke')
    def test_create_router_with_default_snat_value(self):
        # Create a router with default snat rule
        name = data_utils.rand_name('router')
        router = self._create_router(
            name, external_network_id=CONF.network.public_network_id)
        self._verify_router_gateway(
            router['id'], {'network_id': CONF.network.public_network_id,
                           'enable_snat': True})

    @test.idempotent_id('ea74068d-09e9-4fd7-8995-9b6a1ace920f')
    @test.requires_ext(extension='ext-gw-mode', service='network')
    @test.attr(type='smoke')
    def test_create_router_with_snat_explicit(self):
        name = data_utils.rand_name('snat-router')
        # Create a router enabling snat attributes
        enable_snat_states = [False, True]
        for enable_snat in enable_snat_states:
            external_gateway_info = {
                'network_id': CONF.network.public_network_id,
                'enable_snat': enable_snat}
            create_body = self.admin_client.create_router(
                name, external_gateway_info=external_gateway_info)
            self.addCleanup(self.admin_client.delete_router,
                            create_body['router']['id'])
            # Verify snat attributes after router creation
            self._verify_router_gateway(create_body['router']['id'],
                                        exp_ext_gw_info=external_gateway_info)

    def _verify_router_gateway(self, router_id, exp_ext_gw_info=None):
        show_body = self.admin_client.show_router(router_id)
        actual_ext_gw_info = show_body['router']['external_gateway_info']
        if exp_ext_gw_info is None:
            self.assertIsNone(actual_ext_gw_info)
            return
        # Verify only keys passed in exp_ext_gw_info
        for k, v in six.iteritems(exp_ext_gw_info):
            self.assertEqual(v, actual_ext_gw_info[k])

    def _verify_gateway_port(self, router_id):
        list_body = self.admin_client.list_ports(
            network_id=CONF.network.public_network_id,
            device_id=router_id)
        self.assertEqual(len(list_body['ports']), 1)
        gw_port = list_body['ports'][0]
        fixed_ips = gw_port['fixed_ips']
        self.assertGreaterEqual(len(fixed_ips), 1)
        public_net_body = self.admin_client.show_network(
            CONF.network.public_network_id)
        public_subnet_id = public_net_body['network']['subnets'][0]
        self.assertIn(public_subnet_id,
                      [x['subnet_id'] for x in fixed_ips])

    @test.idempotent_id('b386c111-3b21-466d-880c-5e72b01e1a33')
    @test.requires_ext(extension='ext-gw-mode', service='network')
    @test.attr(type='smoke')
    def test_update_router_set_gateway_with_snat_explicit(self):
        router = self._create_router(data_utils.rand_name('router-'))
        self.admin_client.update_router_with_snat_gw_info(
            router['id'],
            external_gateway_info={
                'network_id': CONF.network.public_network_id,
                'enable_snat': True})
        self._verify_router_gateway(
            router['id'],
            {'network_id': CONF.network.public_network_id,
             'enable_snat': True})
        self._verify_gateway_port(router['id'])

    @test.idempotent_id('96536bc7-8262-4fb2-9967-5c46940fa279')
    @test.requires_ext(extension='ext-gw-mode', service='network')
    @test.attr(type='smoke')
    def test_update_router_set_gateway_without_snat(self):
        router = self._create_router(data_utils.rand_name('router-'))
        self.admin_client.update_router_with_snat_gw_info(
            router['id'],
            external_gateway_info={
                'network_id': CONF.network.public_network_id,
                'enable_snat': False})
        self._verify_router_gateway(
            router['id'],
            {'network_id': CONF.network.public_network_id,
             'enable_snat': False})
        self._verify_gateway_port(router['id'])

    @test.idempotent_id('f2faf994-97f4-410b-a831-9bc977b64374')
    @test.requires_ext(extension='ext-gw-mode', service='network')
    @test.attr(type='smoke')
    def test_update_router_reset_gateway_without_snat(self):
        router = self._create_router(
            data_utils.rand_name('router-'),
            external_network_id=CONF.network.public_network_id)
        self.admin_client.update_router_with_snat_gw_info(
            router['id'],
            external_gateway_info={
                'network_id': CONF.network.public_network_id,
                'enable_snat': False})
        self._verify_router_gateway(
            router['id'],
            {'network_id': CONF.network.public_network_id,
             'enable_snat': False})
        self._verify_gateway_port(router['id'])

    @test.idempotent_id('c86ac3a8-50bd-4b00-a6b8-62af84a0765c')
    @test.requires_ext(extension='extraroute', service='network')
    @test.attr(type='smoke')
    def test_update_extra_route(self):
        self.network = self.create_network()
        self.name = self.network['name']
        self.subnet = self.create_subnet(self.network)
        # Add router interface with subnet id
        self.router = self._create_router(
            data_utils.rand_name('router-'), True)
        self.create_router_interface(self.router['id'], self.subnet['id'])
        self.addCleanup(
            self._delete_extra_routes,
            self.router['id'])
        # Update router extra route, second ip of the range is
        # used as next hop
        cidr = netaddr.IPNetwork(self.subnet['cidr'])
        next_hop = str(cidr[2])
        destination = str(self.subnet['cidr'])
        extra_route = self.client.update_extra_routes(self.router['id'],
                                                      next_hop, destination)
        self.assertEqual(1, len(extra_route['router']['routes']))
        self.assertEqual(destination,
                         extra_route['router']['routes'][0]['destination'])
        self.assertEqual(next_hop,
                         extra_route['router']['routes'][0]['nexthop'])
        show_body = self.client.show_router(self.router['id'])
        self.assertEqual(destination,
                         show_body['router']['routes'][0]['destination'])
        self.assertEqual(next_hop,
                         show_body['router']['routes'][0]['nexthop'])

    def _delete_extra_routes(self, router_id):
        self.client.delete_extra_routes(router_id)

    @test.attr(type='smoke')
    @test.idempotent_id('01f185d1-d1a6-4cf9-abf7-e0e1384c169c')
    def test_network_attached_with_two_routers(self):
        network = self.create_network(data_utils.rand_name('network1'))
        self.create_subnet(network)
        port1 = self.create_port(network)
        port2 = self.create_port(network)
        router1 = self._create_router(data_utils.rand_name('router1'))
        router2 = self._create_router(data_utils.rand_name('router2'))
        self.client.add_router_interface_with_port_id(
            router1['id'], port1['id'])
        self.client.add_router_interface_with_port_id(
            router2['id'], port2['id'])
        self.addCleanup(self.client.remove_router_interface_with_port_id,
                        router1['id'], port1['id'])
        self.addCleanup(self.client.remove_router_interface_with_port_id,
                        router2['id'], port2['id'])
        body = self.client.show_port(port1['id'])
        port_show1 = body['port']
        body = self.client.show_port(port2['id'])
        port_show2 = body['port']
        self.assertEqual(port_show1['network_id'], network['id'])
        self.assertEqual(port_show2['network_id'], network['id'])
        self.assertEqual(port_show1['device_id'], router1['id'])
        self.assertEqual(port_show2['device_id'], router2['id'])


class RoutersIpV6Test(RoutersTest):
    _ip_version = 6


class DvrRoutersTest(base.BaseRouterTest):

    @classmethod
    @test.requires_ext(extension="dvr", service="network")
    def skip_checks(cls):
        super(DvrRoutersTest, cls).skip_checks()

    @test.attr(type='smoke')
    @test.idempotent_id('141297aa-3424-455d-aa8d-f2d95731e00a')
    def test_create_distributed_router(self):
        name = data_utils.rand_name('router')
        create_body = self.admin_client.create_router(
            name, distributed=True)
        self.addCleanup(self._delete_router,
                        create_body['router']['id'],
                        self.admin_client)
        self.assertTrue(create_body['router']['distributed'])

    @test.attr(type='smoke')
    @test.idempotent_id('644d7a4a-01a1-4b68-bb8d-0c0042cb1729')
    def test_convert_centralized_router(self):
        router = self._create_router(data_utils.rand_name('router'))
        self.assertNotIn('distributed', router)
        update_body = self.admin_client.update_router(router['id'],
                                                      distributed=True)
        self.assertTrue(update_body['router']['distributed'])
        show_body = self.admin_client.show_router(router['id'])
        self.assertTrue(show_body['router']['distributed'])
        show_body = self.client.show_router(router['id'])
        self.assertNotIn('distributed', show_body['router'])
