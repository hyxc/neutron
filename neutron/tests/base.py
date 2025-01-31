# Copyright 2010-2011 OpenStack Foundation
# All Rights Reserved.
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

"""Base test cases for all neutron tests.
"""

import contextlib
import gc
import os
import os.path
import weakref

import eventlet.timeout
import fixtures
import mock
from oslo_concurrency.fixture import lockutils
from oslo_config import cfg
from oslo_messaging import conffixture as messaging_conffixture
from oslo_utils import excutils
from oslo_utils import strutils
from oslotest import base
import six
import testtools

from neutron._i18n import _
from neutron.agent.linux import external_process
from neutron.api.rpc.callbacks.consumer import registry as rpc_consumer_reg
from neutron.callbacks import manager as registry_manager
from neutron.callbacks import registry
from neutron.common import config
from neutron.common import constants
from neutron.common import rpc as n_rpc
from neutron.common import utils
from neutron.db import agentschedulers_db
from neutron import manager
from neutron import policy
from neutron.tests import fake_notifier
from neutron.tests import post_mortem_debug
from neutron.tests import tools


CONF = cfg.CONF
CONF.import_opt('state_path', 'neutron.common.config')

ROOTDIR = os.path.dirname(__file__)
ETCDIR = os.path.join(ROOTDIR, 'etc')


def etcdir(*p):
    return os.path.join(ETCDIR, *p)


def fake_use_fatal_exceptions(*args):
    return True


def get_related_rand_names(prefixes, max_length=None):
    """Returns a list of the prefixes with the same random characters appended

    :param prefixes: A list of prefix strings
    :param max_length: The maximum length of each returned string
    :returns: A list with each prefix appended with the same random characters
    """

    if max_length:
        length = max_length - max(len(p) for p in prefixes)
        if length <= 0:
            raise ValueError("'max_length' must be longer than all prefixes")
    else:
        length = 8
    rndchrs = utils.get_random_string(length)
    return [p + rndchrs for p in prefixes]


def get_rand_name(max_length=None, prefix='test'):
    """Return a random string.

    The string will start with 'prefix' and will be exactly 'max_length'.
    If 'max_length' is None, then exactly 8 random characters, each
    hexadecimal, will be added. In case len(prefix) <= len(max_length),
    ValueError will be raised to indicate the problem.
    """
    return get_related_rand_names([prefix], max_length)[0]


def get_rand_device_name(prefix='test'):
    return get_rand_name(
        max_length=constants.DEVICE_NAME_MAX_LEN, prefix=prefix)


def get_related_rand_device_names(prefixes):
    return get_related_rand_names(prefixes,
                                  max_length=constants.DEVICE_NAME_MAX_LEN)


def bool_from_env(key, strict=False, default=False):
    value = os.environ.get(key)
    return strutils.bool_from_string(value, strict=strict, default=default)


def setup_test_logging(config_opts, log_dir, log_file_path_template):
    # Have each test log into its own log file
    config_opts.set_override('debug', True)
    utils.ensure_dir(log_dir)
    log_file = sanitize_log_path(
        os.path.join(log_dir, log_file_path_template))
    config_opts.set_override('log_file', log_file)
    config_opts.set_override('use_stderr', False)
    config.setup_logging()


def sanitize_log_path(path):
    # Sanitize the string so that its log path is shell friendly
    replace_map = {' ': '-', '(': '_', ')': '_'}
    for s, r in six.iteritems(replace_map):
        path = path.replace(s, r)
    return path


class AttributeDict(dict):

    """
    Provide attribute access (dict.key) to dictionary values.
    """

    def __getattr__(self, name):
        """Allow attribute access for all keys in the dict."""
        if name in self:
            return self[name]
        raise AttributeError(_("Unknown attribute '%s'.") % name)


class DietTestCase(base.BaseTestCase):
    """Same great taste, less filling.

    BaseTestCase is responsible for doing lots of plugin-centric setup
    that not all tests require (or can tolerate).  This class provides
    only functionality that is common across all tests.
    """

    def setUp(self):
        super(DietTestCase, self).setUp()

        # FIXME(amuller): this must be called in the Neutron unit tests base
        # class to initialize the DB connection string. Moving this may cause
        # non-deterministic failures. Bug #1489098 for more info.
        config.set_db_defaults()

        # Configure this first to ensure pm debugging support for setUp()
        debugger = os.environ.get('OS_POST_MORTEM_DEBUGGER')
        if debugger:
            self.addOnException(post_mortem_debug.get_exception_handler(
                debugger))

        # Make sure we see all relevant deprecation warnings when running tests
        self.useFixture(tools.WarningsFixture())

        # NOTE(ihrachys): oslotest already sets stopall for cleanup, but it
        # does it using six.moves.mock (the library was moved into
        # unittest.mock in Python 3.4). So until we switch to six.moves.mock
        # everywhere in unit tests, we can't remove this setup. The base class
        # is used in 3party projects, so we would need to switch all of them to
        # six before removing the cleanup callback from here.
        self.addCleanup(mock.patch.stopall)

        self.addOnException(self.check_for_systemexit)
        self.orig_pid = os.getpid()

        tools.reset_random_seed()

    def addOnException(self, handler):

        def safe_handler(*args, **kwargs):
            try:
                return handler(*args, **kwargs)
            except Exception:
                with excutils.save_and_reraise_exception(reraise=False) as ctx:
                    self.addDetail('failure in exception handler %s' % handler,
                                   testtools.content.TracebackContent(
                                       (ctx.type_, ctx.value, ctx.tb), self))

        return super(DietTestCase, self).addOnException(safe_handler)

    def check_for_systemexit(self, exc_info):
        if isinstance(exc_info[1], SystemExit):
            if os.getpid() != self.orig_pid:
                # Subprocess - let it just exit
                raise
            # This makes sys.exit(0) still a failure
            self.force_failure = True

    @contextlib.contextmanager
    def assert_max_execution_time(self, max_execution_time=5):
        with eventlet.timeout.Timeout(max_execution_time, False):
            yield
            return
        self.fail('Execution of this test timed out')

    def assertOrderedEqual(self, expected, actual):
        expect_val = self.sort_dict_lists(expected)
        actual_val = self.sort_dict_lists(actual)
        self.assertEqual(expect_val, actual_val)

    def sort_dict_lists(self, dic):
        for key, value in six.iteritems(dic):
            if isinstance(value, list):
                dic[key] = sorted(value)
            elif isinstance(value, dict):
                dic[key] = self.sort_dict_lists(value)
        return dic

    def assertDictSupersetOf(self, expected_subset, actual_superset):
        """Checks that actual dict contains the expected dict.

        After checking that the arguments are of the right type, this checks
        that each item in expected_subset is in, and matches, what is in
        actual_superset. Separate tests are done, so that detailed info can
        be reported upon failure.
        """
        if not isinstance(expected_subset, dict):
            self.fail("expected_subset (%s) is not an instance of dict" %
                      type(expected_subset))
        if not isinstance(actual_superset, dict):
            self.fail("actual_superset (%s) is not an instance of dict" %
                      type(actual_superset))
        for k, v in expected_subset.items():
            self.assertIn(k, actual_superset)
            self.assertEqual(v, actual_superset[k],
                             "Key %(key)s expected: %(exp)r, actual %(act)r" %
                             {'key': k, 'exp': v, 'act': actual_superset[k]})


class ProcessMonitorFixture(fixtures.Fixture):
    """Test fixture to capture and cleanup any spawn process monitor."""

    def _setUp(self):
        self.old_callable = (
            external_process.ProcessMonitor._spawn_checking_thread)
        p = mock.patch("neutron.agent.linux.external_process.ProcessMonitor."
                       "_spawn_checking_thread",
                       new=lambda x: self.record_calls(x))
        p.start()
        self.instances = []
        self.addCleanup(self.stop)

    def stop(self):
        for instance in self.instances:
            instance.stop()

    def record_calls(self, instance):
        self.old_callable(instance)
        self.instances.append(instance)


class BaseTestCase(DietTestCase):

    @staticmethod
    def config_parse(conf=None, args=None):
        """Create the default configurations."""
        # neutron.conf includes rpc_backend which needs to be cleaned up
        if args is None:
            args = []
        args += ['--config-file', etcdir('neutron.conf')]
        if conf is None:
            config.init(args=args)
        else:
            conf(args)

    def setUp(self):
        super(BaseTestCase, self).setUp()

        self.useFixture(lockutils.ExternalLockFixture())

        cfg.CONF.set_override('state_path', self.get_default_temp_dir().path)

        self.addCleanup(CONF.reset)
        self.useFixture(ProcessMonitorFixture())

        self.useFixture(fixtures.MonkeyPatch(
            'neutron.common.exceptions.NeutronException.use_fatal_exceptions',
            fake_use_fatal_exceptions))

        self.useFixture(fixtures.MonkeyPatch(
            'oslo_config.cfg.find_config_files',
            lambda project=None, prog=None, extension=None: []))

        self.setup_rpc_mocks()
        self.setup_config()
        self.setup_test_registry_instance()

        policy.init()
        self.addCleanup(policy.reset)
        self.addCleanup(rpc_consumer_reg.clear)

    def get_new_temp_dir(self):
        """Create a new temporary directory.

        :returns fixtures.TempDir
        """
        return self.useFixture(fixtures.TempDir())

    def get_default_temp_dir(self):
        """Create a default temporary directory.

        Returns the same directory during the whole test case.

        :returns fixtures.TempDir
        """
        if not hasattr(self, '_temp_dir'):
            self._temp_dir = self.get_new_temp_dir()
        return self._temp_dir

    def get_temp_file_path(self, filename, root=None):
        """Returns an absolute path for a temporary file.

        If root is None, the file is created in default temporary directory. It
        also creates the directory if it's not initialized yet.

        If root is not None, the file is created inside the directory passed as
        root= argument.

        :param filename: filename
        :type filename: string
        :param root: temporary directory to create a new file in
        :type root: fixtures.TempDir
        :returns absolute file path string
        """
        root = root or self.get_default_temp_dir()
        return root.join(filename)

    def setup_rpc_mocks(self):
        # don't actually start RPC listeners when testing
        mock.patch(
            'neutron.common.rpc.Connection.consume_in_threads',
            return_value=[]).start()

        self.useFixture(fixtures.MonkeyPatch(
            'oslo_messaging.Notifier', fake_notifier.FakeNotifier))

        self.messaging_conf = messaging_conffixture.ConfFixture(CONF)
        self.messaging_conf.transport_driver = 'fake'
        # NOTE(russellb) We want all calls to return immediately.
        self.messaging_conf.response_timeout = 0
        self.useFixture(self.messaging_conf)

        self.addCleanup(n_rpc.clear_extra_exmods)
        n_rpc.add_extra_exmods('neutron.test')

        self.addCleanup(n_rpc.cleanup)
        n_rpc.init(CONF)

    def setup_test_registry_instance(self):
        """Give a private copy of the registry to each test."""
        self._callback_manager = registry_manager.CallbacksManager()
        mock.patch.object(registry, '_get_callback_manager',
                          return_value=self._callback_manager).start()

    def setup_config(self, args=None):
        """Tests that need a non-default config can override this method."""
        self.config_parse(args=args)

    def config(self, **kw):
        """Override some configuration values.

        The keyword arguments are the names of configuration options to
        override and their values.

        If a group argument is supplied, the overrides are applied to
        the specified configuration option group.

        All overrides are automatically cleared at the end of the current
        test by the fixtures cleanup process.
        """
        group = kw.pop('group', None)
        for k, v in six.iteritems(kw):
            CONF.set_override(k, v, group)

    def setup_coreplugin(self, core_plugin=None):
        cp = PluginFixture(core_plugin)
        self.useFixture(cp)
        self.patched_dhcp_periodic = cp.patched_dhcp_periodic
        self.patched_default_svc_plugins = cp.patched_default_svc_plugins

    def setup_notification_driver(self, notification_driver=None):
        self.addCleanup(fake_notifier.reset)
        if notification_driver is None:
            notification_driver = [fake_notifier.__name__]
        cfg.CONF.set_override("notification_driver", notification_driver)


class PluginFixture(fixtures.Fixture):

    def __init__(self, core_plugin=None):
        super(PluginFixture, self).__init__()
        self.core_plugin = core_plugin

    def _setUp(self):
        # Do not load default service plugins in the testing framework
        # as all the mocking involved can cause havoc.
        self.default_svc_plugins_p = mock.patch(
            'neutron.manager.NeutronManager._get_default_service_plugins')
        self.patched_default_svc_plugins = self.default_svc_plugins_p.start()
        self.dhcp_periodic_p = mock.patch(
            'neutron.db.agentschedulers_db.DhcpAgentSchedulerDbMixin.'
            'start_periodic_dhcp_agent_status_check')
        self.patched_dhcp_periodic = self.dhcp_periodic_p.start()
        self.agent_health_check_p = mock.patch(
            'neutron.db.agentschedulers_db.DhcpAgentSchedulerDbMixin.'
            'add_agent_status_check')
        self.agent_health_check = self.agent_health_check_p.start()
        # Plugin cleanup should be triggered last so that
        # test-specific cleanup has a chance to release references.
        self.addCleanup(self.cleanup_core_plugin)
        if self.core_plugin is not None:
            cfg.CONF.set_override('core_plugin', self.core_plugin)

    def cleanup_core_plugin(self):
        """Ensure that the core plugin is deallocated."""
        nm = manager.NeutronManager
        if not nm.has_instance():
            return

        # TODO(marun) Fix plugins that do not properly initialize notifiers
        agentschedulers_db.AgentSchedulerDbMixin.agent_notifiers = {}

        # Perform a check for deallocation only if explicitly
        # configured to do so since calling gc.collect() after every
        # test increases test suite execution time by ~50%.
        check_plugin_deallocation = (
            bool_from_env('OS_CHECK_PLUGIN_DEALLOCATION'))
        if check_plugin_deallocation:
            plugin = weakref.ref(nm._instance.plugin)

        nm.clear_instance()

        if check_plugin_deallocation:
            gc.collect()

            # TODO(marun) Ensure that mocks are deallocated?
            if plugin() and not isinstance(plugin(), mock.Base):
                raise AssertionError(
                    'The plugin for this test was not deallocated.')
