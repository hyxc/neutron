# Copyright 2015 Hewlett-Packard Development Company, L.P.
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

from tempest.lib.common.utils import data_utils
from tempest import test

from neutron.tests.tempest.api import base

SUBNETPOOL_NAME = 'smoke-subnetpool'
SUBNET_NAME = 'smoke-subnet'


class SubnetPoolsTestBase(base.BaseAdminNetworkTest):

    @classmethod
    def resource_setup(cls):
        super(SubnetPoolsTestBase, cls).resource_setup()
        min_prefixlen = '29'
        prefixes = [u'10.11.12.0/24']
        cls._subnetpool_data = {'prefixes': prefixes,
                                'min_prefixlen': min_prefixlen}

    def _create_subnetpool(self, is_admin=False, **kwargs):
        if 'name' not in kwargs:
            name = data_utils.rand_name(SUBNETPOOL_NAME)
        else:
            name = kwargs.pop('name')

        if 'prefixes' not in kwargs:
            kwargs['prefixes'] = self._subnetpool_data['prefixes']

        if 'min_prefixlen' not in kwargs:
            kwargs['min_prefixlen'] = self._subnetpool_data['min_prefixlen']

        return self.create_subnetpool(name=name, is_admin=is_admin, **kwargs)


class SubnetPoolsTest(SubnetPoolsTestBase):

    min_prefixlen = '28'
    max_prefixlen = '31'
    _ip_version = 4
    subnet_cidr = u'10.11.12.0/31'
    new_prefix = u'10.11.15.0/24'
    larger_prefix = u'10.11.0.0/16'

    """
    Tests the following operations in the Neutron API using the REST client for
    Neutron:

        create a subnetpool for a tenant
        list tenant's subnetpools
        show a tenant subnetpool details
        subnetpool update
        delete a subnetpool

        All subnetpool tests are run once with ipv4 and once with ipv6.

    v2.0 of the Neutron API is assumed.

    """

    def _new_subnetpool_attributes(self):
        new_name = data_utils.rand_name(SUBNETPOOL_NAME)
        return {'name': new_name, 'min_prefixlen': self.min_prefixlen,
                'max_prefixlen': self.max_prefixlen}

    def _check_equality_updated_subnetpool(self, expected_values,
                                           updated_pool):
        self.assertEqual(expected_values['name'],
                         updated_pool['name'])
        self.assertEqual(expected_values['min_prefixlen'],
                         updated_pool['min_prefixlen'])
        self.assertEqual(expected_values['max_prefixlen'],
                         updated_pool['max_prefixlen'])
        # expected_values may not contains all subnetpool values
        if 'prefixes' in expected_values:
            self.assertEqual(expected_values['prefixes'],
                             updated_pool['prefixes'])

    @test.attr(type='smoke')
    @test.idempotent_id('6e1781ec-b45b-4042-aebe-f485c022996e')
    def test_create_list_subnetpool(self):
        created_subnetpool = self._create_subnetpool()
        body = self.client.list_subnetpools()
        subnetpools = body['subnetpools']
        self.assertIn(created_subnetpool['id'],
                      [sp['id'] for sp in subnetpools],
                      "Created subnetpool id should be in the list")
        self.assertIn(created_subnetpool['name'],
                      [sp['name'] for sp in subnetpools],
                      "Created subnetpool name should be in the list")

    @test.attr(type='smoke')
    @test.idempotent_id('c72c1c0c-2193-4aca-ddd4-b1442640bbbb')
    @test.requires_ext(extension="standard-attr-description",
                       service="network")
    def test_create_update_subnetpool_description(self):
        body = self._create_subnetpool(description='d1')
        self.assertEqual('d1', body['description'])
        sub_id = body['id']
        body = filter(lambda x: x['id'] == sub_id,
                      self.client.list_subnetpools()['subnetpools'])[0]
        self.assertEqual('d1', body['description'])
        body = self.client.update_subnetpool(sub_id, description='d2')
        self.assertEqual('d2', body['subnetpool']['description'])
        body = filter(lambda x: x['id'] == sub_id,
                      self.client.list_subnetpools()['subnetpools'])[0]
        self.assertEqual('d2', body['description'])

    @test.attr(type='smoke')
    @test.idempotent_id('741d08c2-1e3f-42be-99c7-0ea93c5b728c')
    def test_get_subnetpool(self):
        created_subnetpool = self._create_subnetpool()
        prefixlen = self._subnetpool_data['min_prefixlen']
        body = self.client.show_subnetpool(created_subnetpool['id'])
        subnetpool = body['subnetpool']
        self.assertEqual(created_subnetpool['name'], subnetpool['name'])
        self.assertEqual(created_subnetpool['id'], subnetpool['id'])
        self.assertEqual(prefixlen, subnetpool['min_prefixlen'])
        self.assertEqual(prefixlen, subnetpool['default_prefixlen'])
        self.assertFalse(subnetpool['shared'])

    @test.attr(type='smoke')
    @test.idempotent_id('764f1b93-1c4a-4513-9e7b-6c2fc5e9270c')
    def test_tenant_update_subnetpool(self):
        created_subnetpool = self._create_subnetpool()
        pool_id = created_subnetpool['id']
        subnetpool_data = self._new_subnetpool_attributes()
        self.client.update_subnetpool(created_subnetpool['id'],
                                      **subnetpool_data)

        body = self.client.show_subnetpool(pool_id)
        subnetpool = body['subnetpool']
        self._check_equality_updated_subnetpool(subnetpool_data,
                                                subnetpool)
        self.assertFalse(subnetpool['shared'])

    @test.attr(type='smoke')
    @test.idempotent_id('4b496082-c992-4319-90be-d4a7ce646290')
    def test_update_subnetpool_prefixes_append(self):
        # We can append new prefixes to subnetpool
        create_subnetpool = self._create_subnetpool()
        pool_id = create_subnetpool['id']
        old_prefixes = self._subnetpool_data['prefixes']
        new_prefixes = old_prefixes[:]
        new_prefixes.append(self.new_prefix)
        subnetpool_data = {'prefixes': new_prefixes}
        self.client.update_subnetpool(pool_id, **subnetpool_data)
        body = self.client.show_subnetpool(pool_id)
        prefixes = body['subnetpool']['prefixes']
        self.assertIn(self.new_prefix, prefixes)
        self.assertIn(old_prefixes[0], prefixes)

    @test.attr(type='smoke')
    @test.idempotent_id('2cae5d6a-9d32-42d8-8067-f13970ae13bb')
    def test_update_subnetpool_prefixes_extend(self):
        # We can extend current subnetpool prefixes
        created_subnetpool = self._create_subnetpool()
        pool_id = created_subnetpool['id']
        old_prefixes = self._subnetpool_data['prefixes']
        subnetpool_data = {'prefixes': [self.larger_prefix]}
        self.client.update_subnetpool(pool_id, **subnetpool_data)
        body = self.client.show_subnetpool(pool_id)
        prefixes = body['subnetpool']['prefixes']
        self.assertIn(self.larger_prefix, prefixes)
        self.assertNotIn(old_prefixes[0], prefixes)

    @test.attr(type='smoke')
    @test.idempotent_id('d70c6c35-913b-4f24-909f-14cd0d29b2d2')
    def test_admin_create_shared_subnetpool(self):
        created_subnetpool = self._create_subnetpool(is_admin=True,
                                                     shared=True)
        pool_id = created_subnetpool['id']
        # Shared subnetpool can be retrieved by tenant user.
        body = self.client.show_subnetpool(pool_id)
        subnetpool = body['subnetpool']
        self.assertEqual(created_subnetpool['name'], subnetpool['name'])
        self.assertTrue(subnetpool['shared'])

    def _create_subnet_from_pool(self, subnet_values=None, pool_values=None):
        if pool_values is None:
            pool_values = {}

        created_subnetpool = self._create_subnetpool(**pool_values)
        pool_id = created_subnetpool['id']
        subnet_name = data_utils.rand_name(SUBNETPOOL_NAME)
        network = self.create_network()
        subnet_kwargs = {'name': subnet_name,
                         'subnetpool_id': pool_id}
        if subnet_values:
            subnet_kwargs.update(subnet_values)
        # not creating the subnet using the base.create_subnet because
        # that function needs to be enhanced to support subnet_create when
        # prefixlen and subnetpool_id is specified.
        body = self.client.create_subnet(
            network_id=network['id'],
            ip_version=self._ip_version,
            **subnet_kwargs)
        subnet = body['subnet']
        return pool_id, subnet

    @test.attr(type='smoke')
    @test.idempotent_id('1362ed7d-3089-42eb-b3a5-d6cb8398ee77')
    def test_create_subnet_from_pool_with_prefixlen(self):
        subnet_values = {"prefixlen": self.max_prefixlen}
        pool_id, subnet = self._create_subnet_from_pool(
            subnet_values=subnet_values)
        cidr = str(subnet['cidr'])
        self.assertEqual(pool_id, subnet['subnetpool_id'])
        self.assertTrue(cidr.endswith(str(self.max_prefixlen)))

    @test.attr(type='smoke')
    @test.idempotent_id('86b86189-9789-4582-9c3b-7e2bfe5735ee')
    def test_create_subnet_from_pool_with_subnet_cidr(self):
        subnet_values = {"cidr": self.subnet_cidr}
        pool_id, subnet = self._create_subnet_from_pool(
            subnet_values=subnet_values)
        cidr = str(subnet['cidr'])
        self.assertEqual(pool_id, subnet['subnetpool_id'])
        self.assertEqual(cidr, self.subnet_cidr)

    @test.attr(type='smoke')
    @test.idempotent_id('83f76e3a-9c40-40c2-a015-b7c5242178d8')
    def test_create_subnet_from_pool_with_default_prefixlen(self):
        # If neither cidr nor prefixlen is specified,
        # subnet will use subnetpool default_prefixlen for cidr.
        pool_id, subnet = self._create_subnet_from_pool()
        cidr = str(subnet['cidr'])
        self.assertEqual(pool_id, subnet['subnetpool_id'])
        prefixlen = self._subnetpool_data['min_prefixlen']
        self.assertTrue(cidr.endswith(str(prefixlen)))

    @test.attr(type='smoke')
    @test.idempotent_id('a64af292-ec52-4bde-b654-a6984acaf477')
    def test_create_subnet_from_pool_with_quota(self):
        pool_values = {'default_quota': 4}
        subnet_values = {"prefixlen": self.max_prefixlen}
        pool_id, subnet = self._create_subnet_from_pool(
            subnet_values=subnet_values, pool_values=pool_values)
        cidr = str(subnet['cidr'])
        self.assertEqual(pool_id, subnet['subnetpool_id'])
        self.assertTrue(cidr.endswith(str(self.max_prefixlen)))

    @test.attr(type='smoke')
    @test.idempotent_id('49b44c64-1619-4b29-b527-ffc3c3115dc4')
    @test.requires_ext(extension='address-scope', service='network')
    def test_create_subnetpool_associate_address_scope(self):
        address_scope = self.create_address_scope(
            name=data_utils.rand_name('smoke-address-scope'),
            ip_version=self._ip_version)
        created_subnetpool = self._create_subnetpool(
            address_scope_id=address_scope['id'])
        body = self.client.show_subnetpool(created_subnetpool['id'])
        self.assertEqual(address_scope['id'],
                         body['subnetpool']['address_scope_id'])

    @test.attr(type='smoke')
    @test.idempotent_id('910b6393-db24-4f6f-87dc-b36892ad6c8c')
    @test.requires_ext(extension='address-scope', service='network')
    def test_update_subnetpool_associate_address_scope(self):
        address_scope = self.create_address_scope(
            name=data_utils.rand_name('smoke-address-scope'),
            ip_version=self._ip_version)
        created_subnetpool = self._create_subnetpool()
        pool_id = created_subnetpool['id']
        body = self.client.show_subnetpool(pool_id)
        self.assertIsNone(body['subnetpool']['address_scope_id'])
        self.client.update_subnetpool(pool_id,
                                      address_scope_id=address_scope['id'])
        body = self.client.show_subnetpool(pool_id)
        self.assertEqual(address_scope['id'],
                         body['subnetpool']['address_scope_id'])

    @test.attr(type='smoke')
    @test.idempotent_id('18302e80-46a3-4563-82ac-ccd1dd57f652')
    @test.requires_ext(extension='address-scope', service='network')
    def test_update_subnetpool_associate_another_address_scope(self):
        address_scope = self.create_address_scope(
            name=data_utils.rand_name('smoke-address-scope'),
            ip_version=self._ip_version)
        another_address_scope = self.create_address_scope(
            name=data_utils.rand_name('smoke-address-scope'),
            ip_version=self._ip_version)
        created_subnetpool = self._create_subnetpool(
            address_scope_id=address_scope['id'])
        pool_id = created_subnetpool['id']
        body = self.client.show_subnetpool(pool_id)
        self.assertEqual(address_scope['id'],
                         body['subnetpool']['address_scope_id'])
        self.client.update_subnetpool(
            pool_id, address_scope_id=another_address_scope['id'])
        body = self.client.show_subnetpool(pool_id)
        self.assertEqual(another_address_scope['id'],
                         body['subnetpool']['address_scope_id'])

    @test.attr(type='smoke')
    @test.idempotent_id('f8970048-e41b-42d6-934b-a1297b07706a')
    @test.requires_ext(extension='address-scope', service='network')
    def test_update_subnetpool_disassociate_address_scope(self):
        address_scope = self.create_address_scope(
            name=data_utils.rand_name('smoke-address-scope'),
            ip_version=self._ip_version)
        created_subnetpool = self._create_subnetpool(
            address_scope_id=address_scope['id'])
        pool_id = created_subnetpool['id']
        body = self.client.show_subnetpool(pool_id)
        self.assertEqual(address_scope['id'],
                         body['subnetpool']['address_scope_id'])
        self.client.update_subnetpool(pool_id,
                                      address_scope_id=None)
        body = self.client.show_subnetpool(pool_id)
        self.assertIsNone(body['subnetpool']['address_scope_id'])


class SubnetPoolsTestV6(SubnetPoolsTest):

    min_prefixlen = '48'
    max_prefixlen = '64'
    _ip_version = 6
    subnet_cidr = '2001:db8:3::/64'
    new_prefix = u'2001:db8:5::/64'
    larger_prefix = u'2001:db8::/32'

    @classmethod
    def resource_setup(cls):
        super(SubnetPoolsTestV6, cls).resource_setup()
        min_prefixlen = '64'
        prefixes = [u'2001:db8:3::/48']
        cls._subnetpool_data = {'min_prefixlen': min_prefixlen,
                                'prefixes': prefixes}

    @test.attr(type='smoke')
    @test.idempotent_id('f62d73dc-cf6f-4879-b94b-dab53982bf3b')
    def test_create_dual_stack_subnets_from_subnetpools(self):
        pool_id_v6, subnet_v6 = self._create_subnet_from_pool()
        pool_values_v4 = {'prefixes': ['192.168.0.0/16'],
                          'min_prefixlen': 21,
                          'max_prefixlen': 32}
        create_v4_subnetpool = self._create_subnetpool(**pool_values_v4)
        pool_id_v4 = create_v4_subnetpool['id']
        subnet_v4 = self.client.create_subnet(
            network_id=subnet_v6['network_id'], ip_version=4,
            subnetpool_id=pool_id_v4)['subnet']
        self.assertEqual(subnet_v4['network_id'], subnet_v6['network_id'])
