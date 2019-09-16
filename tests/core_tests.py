# Vane 2.0: A web application vulnerability assessment tool.
# Copyright (C) 2017-  Delve Labs inc.
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

from unittest import TestCase
from unittest.mock import MagicMock, patch, call, ANY
from aiohttp.test_utils import make_mocked_coro, loop_context
from hammertime.http import Entry
from hammertime.ruleset import HammerTimeException
from hammertime.rules.deadhostdetection import OfflineHostException
from aiohttp import ClientError
import asyncio
from collections import OrderedDict
from os.path import join, dirname

from vane.core import Vane
from openwebvulndb.common.models import VulnerabilityList, Vulnerability
from vane.outputmanager import OutputManager
from fixtures import async_test, html_file_to_hammertime_response


@patch("vane.core.load_model_from_file", MagicMock(return_value=(MagicMock(), "errors")))
class TestVane(TestCase):

    def setUp(self):
        self._vane = None

    @property
    def vane(self):
        if self._vane is None:
            self._vane = Vane()
            self._vane.config_hammertime = MagicMock()
            self._vane.initialize_hammertime(concurrency=1)
            self._vane.hammertime.close = make_mocked_coro()
            self._vane.output_manager = MagicMock()
            self._vane.database = MagicMock()
            self._vane.database.database_directory = "/path/to/database/vane2_data_1.0"
            self._vane._load_database = make_mocked_coro()

        return self._vane

    @async_test()
    async def test_perform_action_raise_exception_if_no_url_and_action_is_scan(self):
        with patch("vane.core.custom_event_loop", MagicMock()):
            with self.assertRaises(ValueError):
                self.vane.perform_action(action="scan")

    @async_test()
    async def test_perform_action_flush_output(self):
        with patch("vane.core.custom_event_loop", MagicMock()):
            self.vane.perform_action(action="no_action", url="test", verify_ssl=False)

            self.vane.output_manager.flush.assert_called_once_with()

    @async_test()
    async def test_scan_target_abort_if_target_is_not_wordpress(self):
        self.vane.is_wordpress = make_mocked_coro(return_value=False)
        self.vane.identify_target_version = make_mocked_coro()

        await self.vane.scan_target("http://www.test.com/", True, True)

        self.vane.identify_target_version.assert_not_called()

    @async_test()
    async def test_scan_target_log_message_if_scan_aborted(self):
        exception = ValueError("target is not a valid Wordpress site.")
        self.vane.is_wordpress = make_mocked_coro(raise_exception=exception)

        await self.vane.scan_target("http://www.test.com/", True, True)

        self.vane.output_manager.log_message.assert_any_call(str(exception))

    @async_test()
    async def test_scan_target_abort_if_target_is_not_valid_url(self):
        self.vane.active_plugin_enumeration = make_mocked_coro()
        self.vane.active_theme_enumeration = make_mocked_coro()
        self.vane.identify_target_version = make_mocked_coro()

        await self.vane.scan_target("www.test.com", True, True)

        self.vane.active_plugin_enumeration.assert_not_called()
        self.vane.active_theme_enumeration.assert_not_called()
        self.vane.identify_target_version.assert_not_called()
        self.vane.hammertime.close.assert_called_once_with()

    @async_test()
    async def test_scan_target_log_message_and_abort_scan_if_host_is_dead(self):
        self.vane.is_wordpress = make_mocked_coro(return_value=True)
        self.vane.identify_target_version = make_mocked_coro(raise_exception=OfflineHostException())
        self.vane.plugin_enumeration = make_mocked_coro()
        host = "http://www.test.com/"

        await self.vane.scan_target(host, True, True)

        self.vane.output_manager.log_message.assert_any_call("%s seems to be offline, aborting scan" % host)
        self.vane.plugin_enumeration.assert_not_called()  # Should not proceed to next step.

    @async_test()
    async def test_is_wordpress_return_true_if_link_to_wp_json_in_http_headers(self):
        entry = MagicMock()
        entry.response.headers = {"link": "<http://example.com/index.php/wp-json/>"}
        self.vane.hammertime.request = make_mocked_coro(return_value=entry)

        self.assertTrue(await self.vane.is_wordpress("http://example.com/"))

    @async_test()
    async def test_is_wordpress_return_true_if_url_with_wp_content_in_homepage(self):
        entry = MagicMock()
        entry.response = html_file_to_hammertime_response(join(dirname(__file__), "samples/delvelabs_homepage.html"))
        entry.response.headers = {"link": "http://example.com/url/unrelated/to_wordpress"}
        self.vane.hammertime.request = make_mocked_coro(return_value=entry)

        self.assertTrue(await self.vane.is_wordpress("http://example.com/"))

    @async_test()
    async def test_is_wordpress_return_false_if_not_wordpress(self):
        entry = MagicMock()
        entry.response.content = "not a wordpress homepage"
        entry.response.headers = {"link": "http://example.com/url/unrelated/to_wordpress"}
        self.vane.hammertime.request = make_mocked_coro(return_value=entry)

        self.assertFalse(await self.vane.is_wordpress("http://example.com/"))

    @async_test()
    async def test_identify_target_version_request_files_that_expose_version(self):
        fake_fetcher = MagicMock()
        fake_fetcher.request_files = make_mocked_coro(return_value=("key", ["files"]))
        self.vane._get_files_for_version_identification = make_mocked_coro()

        await self.vane.identify_target_version("url", "input path",
                                                file_fetcher=fake_fetcher, version_identifier=MagicMock())

        self.vane._get_files_for_version_identification.assert_called_once_with("url")

    @async_test()
    async def test_identify_target_version_calls_identify_version_with_files_that_expose_version(self):
        fake_fetcher = MagicMock()
        fake_fetcher.request_files = make_mocked_coro(return_value=("key", ["files"]))
        version_identifier = MagicMock()
        self.vane._get_files_for_version_identification = make_mocked_coro(return_value=["file0", "file1"])

        await self.vane.identify_target_version("url", "input path",
                                                file_fetcher=fake_fetcher, version_identifier=version_identifier)

        version_identifier.identify_version.assert_called_once_with(["files"], ANY, ["file0", "file1"])

    @async_test()
    async def test_identify_target_version_set_confidence_level_of_version_found_in_fetched_files(self):
        fake_fetcher = MagicMock()
        fake_fetcher.request_files = make_mocked_coro(return_value=("key", ["files"]))
        fake_fetcher.timeouts = 15
        version_identifier = MagicMock()
        loaded_files = MagicMock(), []
        loaded_files[0].files = [i for i in range(20)]  # emulate a file list with 20 files
        self.vane._get_files_for_version_identification = make_mocked_coro(return_value=["file0", "file1"])

        with patch("vane.core.load_model_from_file", MagicMock(return_value=loaded_files)):
            await self.vane.identify_target_version("url", "input path",
                                                    file_fetcher=fake_fetcher, version_identifier=version_identifier)

            # confidence level is (total files - files that timed out) / total files.
            version_identifier.set_confidence_level_of_fetched_files.assert_called_once_with(5 / 20)

    @async_test()
    async def test_list_component_vulnerabilitites_call_list_vulnerabilities_for_each_component(self):
        components_version = {'plugin0': "1.2.3", 'theme0': "3.2.1", 'plugin1': "1.4.0", 'theme1': "6.9"}
        plugin0_vuln_list = VulnerabilityList(key="plugin0", producer="")
        plugin1_vuln_list = VulnerabilityList(key="plugin1", producer="")
        theme0_vuln_list = VulnerabilityList(key="theme0", producer="")
        theme1_vuln_list = VulnerabilityList(key="theme1", producer="")
        vuln_list_group = MagicMock()
        vuln_list_group.vulnerability_lists = [plugin0_vuln_list, plugin1_vuln_list, theme1_vuln_list, theme0_vuln_list]

        fake_list_vuln = MagicMock()

        with patch("vane.vulnerabilitylister.VulnerabilityLister.list_vulnerabilities", fake_list_vuln):
            self.vane.list_component_vulnerabilities(components_version, vuln_list_group, no_version_match_all=True)

            calls = [call("1.2.3", plugin0_vuln_list, no_version_match_all=True),
                     call("1.4.0", plugin1_vuln_list, no_version_match_all=True),
                     call("3.2.1", theme0_vuln_list, no_version_match_all=True),
                     call("6.9", theme1_vuln_list, no_version_match_all=True)]
            fake_list_vuln.assert_has_calls(calls, any_order=True)

    @async_test()
    async def test_list_component_vulnerabilitites_skip_component_with_no_vulnerability(self):
        components_version = {'plugin0': "1.2.3"}
        plugin1_vuln_list = VulnerabilityList(key="plugin1", producer="")
        vuln_list_group = MagicMock()
        vuln_list_group.vulnerability_lists = [plugin1_vuln_list]

        fake_list_vuln = MagicMock()

        with patch("vane.vulnerabilitylister.VulnerabilityLister.list_vulnerabilities", fake_list_vuln):
            self.vane.list_component_vulnerabilities(components_version, vuln_list_group, no_version_match_all=True)

            fake_list_vuln.assert_not_called()

    @async_test()
    async def test_list_component_vulnerabilitites_return_vulnerabilities_for_each_component(self):
        components_version = {'plugin0': "1.2.3", 'plugin1': "1.4.0"}
        plugin0_vuln_list = VulnerabilityList(key="plugin0", producer="", vulnerabilities=[Vulnerability(id="1234")])
        plugin1_vuln_list = VulnerabilityList(key="plugin1", producer="", vulnerabilities=[Vulnerability(id="2345")])
        vuln_list_group = MagicMock()
        vuln_list_group.vulnerability_lists = [plugin0_vuln_list, plugin1_vuln_list]

        def fake_list_vuln(self, version, vuln_list, no_version_match_all):
            return vuln_list.vulnerabilities

        with patch("vane.vulnerabilitylister.VulnerabilityLister.list_vulnerabilities", fake_list_vuln):
            vulns = self.vane.list_component_vulnerabilities(components_version, vuln_list_group,
                                                             no_version_match_all=True)

            self.assertEqual(plugin0_vuln_list.vulnerabilities, vulns['plugin0'])
            self.assertEqual(plugin1_vuln_list.vulnerabilities, vulns['plugin1'])

    @async_test()
    async def test_passive_plugin_enumeration_return_dict_with_plugins_key_and_version(self):
        fake_plugin_finder = MagicMock()
        fake_plugin_finder.list_plugins.return_value = {"plugins/wp-postratings": None, "plugins/disqus-comment-system":
                                                        "1.0.2", "plugins/cyclone-slider-2": "2.9.1"}
        fake_plugin_finder_factory = MagicMock()
        fake_plugin_finder_factory.return_value = fake_plugin_finder

        with patch("vane.core.PassivePluginsFinder", fake_plugin_finder_factory):
            plugins = self.vane.passive_plugin_enumeration("html_page", None)

            self.assertEqual(plugins["plugins/disqus-comment-system"], "1.0.2")
            self.assertIsNone(plugins["plugins/wp-postratings"])
            self.assertEqual(plugins["plugins/cyclone-slider-2"], "2.9.1")

    @async_test()
    async def test_plugin_enumeration_merge_active_and_passive_detection_results(self):
        self.vane.active_plugin_enumeration = make_mocked_coro(return_value={"plugins/plugin0": "1.2",
                                                                             "plugins/plugin1": "3.2.1"})
        self.vane.passive_plugin_enumeration = MagicMock(return_value={"plugins/plugin2": "4.3.1",
                                                                       "plugins/plugin1": None})
        self.vane.hammertime.request = make_mocked_coro(return_value=MagicMock())

        plugins_version = await self.vane.plugin_enumeration("target", True, True, "path")

        self.assertEqual(plugins_version, {"plugins/plugin0": "1.2", "plugins/plugin1": "3.2.1",
                                           "plugins/plugin2": "4.3.1"})

    @async_test()
    async def test_plugin_enumeration_version_found_by_passive_scan_overwrite_version_found_by_active_scan(self):
        self.vane.active_plugin_enumeration = make_mocked_coro(return_value={"plugins/plugin0": None,
                                                                             "plugins/plugin1": "3.2.1",
                                                                             "plugins/plugin2": "1.2.3"})
        self.vane.passive_plugin_enumeration = MagicMock(return_value={"plugins/plugin0": "4.3.1",
                                                                       "plugins/plugin1": None,
                                                                       "plugins/plugin2": "1.2.4"})
        self.vane.hammertime.request = make_mocked_coro(return_value=MagicMock())
        self.vane.output_manager = OutputManager()
        self.vane.output_manager.add_plugin("plugins/plugin0", None, None)
        self.vane.output_manager.add_plugin("plugins/plugin1", "3.2.1", None)
        self.vane.output_manager.add_plugin("plugins/plugin2", "1.2.3", None)

        plugins_version = await self.vane.plugin_enumeration("target", True, True, "path")

        self.assertEqual(plugins_version, {"plugins/plugin0": "4.3.1", "plugins/plugin1": "3.2.1",
                                           "plugins/plugin2": "1.2.4"})

        plugins_data = self.vane.output_manager.data["plugins"]
        plugin0_data = [plugin_dict for plugin_dict in plugins_data if plugin_dict["key"] == "plugins/plugin0"][0]
        plugin2_data = [plugin_dict for plugin_dict in plugins_data if plugin_dict["key"] == "plugins/plugin2"][0]
        self.assertEqual(len(plugins_data), 3)  # make sure plugins are not added twice when found two or more times.
        self.assertEqual(plugin0_data["version"], "4.3.1")
        self.assertEqual(plugin2_data["version"], "1.2.4")

    @async_test()
    async def test_plugin_enumeration_log_plugins_found_in_passive_scan(self):
        self.vane.active_plugin_enumeration = make_mocked_coro(return_value={"plugins/plugin0": "1.2",
                                                                             "plugins/plugin1": "3.2.1"})
        self.vane.passive_plugin_enumeration = MagicMock(return_value={"plugins/plugin2": None,
                                                                       "plugins/plugin1": "3.2.1"})
        self.vane.hammertime.request = make_mocked_coro(return_value=MagicMock())
        self.vane.output_manager = OutputManager()
        self.vane.output_manager.add_plugin("plugins/plugin0", "1.2", None)
        self.vane.output_manager.add_plugin("plugins/plugin1", "3.2.1", None)
        fake_meta_list = MagicMock()
        fake_meta_list.get_meta.return_value = None
        self.vane._load_meta_list = MagicMock(return_value=(fake_meta_list, None))

        await self.vane.plugin_enumeration("target", True, True, "path")

        plugins_log = self.vane.output_manager.data["plugins"]
        self.assertEqual(len(plugins_log), 3)
        self.assertEqual(plugins_log[0], OrderedDict([('name', "plugin0"), ('key', "plugins/plugin0"),
                                                     ('version', "1.2"), ('url', None)]))
        self.assertEqual(plugins_log[1], OrderedDict([('name', "plugin1"), ('key', "plugins/plugin1"),
                                                     ('version', "3.2.1"), ('url', None)]))
        self.assertEqual(plugins_log[2], OrderedDict([('name', "plugin2"), ('key', "plugins/plugin2"),
                                                     ('version', "No version found"), ('url', None)]))

    @async_test()
    async def test_passive_theme_enumeration_return_set_of_theme_keys(self):
        fake_theme_finder = MagicMock()
        fake_theme_finder.list_themes.return_value = {"themes/twentyseventeen", "themes/twentysixteen"}

        fake_theme_finder_factory = MagicMock()
        fake_theme_finder_factory.return_value = fake_theme_finder

        with patch("vane.core.PassiveThemesFinder", fake_theme_finder_factory):
            themes = self.vane.passive_theme_enumeration("html_page", None)

            self.assertIn("themes/twentyseventeen", themes)
            self.assertIn("themes/twentysixteen", themes)

    @async_test()
    async def test_theme_enumeration_merge_active_and_passive_detection_results(self):
        self.vane.active_theme_enumeration = make_mocked_coro(return_value={"themes/theme0": "1.2",
                                                                             "themes/theme1": "3.2.1"})
        self.vane.passive_theme_enumeration = MagicMock(return_value={"themes/theme2", "themes/theme1"})
        self.vane.hammertime.request = make_mocked_coro(return_value=MagicMock())

        themes_version = await self.vane.theme_enumeration("target", True, True, "path")

        self.assertEqual(themes_version, {"themes/theme0": "1.2", "themes/theme1": "3.2.1",
                                          "themes/theme2": None})

    @async_test()
    async def test_theme_enumeration_log_theme_found_in_passive_scan_but_not_in_active_scan(self):
        self.vane.active_theme_enumeration = make_mocked_coro(return_value={"themes/theme0": "1.2",
                                                                            "themes/theme1": "3.2.1"})
        self.vane.passive_theme_enumeration = MagicMock(return_value=["themes/theme2", "themes/theme1"])
        self.vane.hammertime.request = make_mocked_coro(return_value=MagicMock())

        await self.vane.theme_enumeration("target", True, True, "path")

        call_args = self.vane.output_manager.add_theme.call_args
        self.assertEqual(len(self.vane.output_manager.add_theme.mock_calls), 1)
        self.assertEqual(call_args[0][0], "themes/theme2")
        self.assertIsNone(call_args[0][1])

    @async_test()
    async def test_set_proxy_set_hammertime_proxy(self):
        self.vane.set_proxy("http://127.0.0.1:8080")

        self.assertEqual(self.vane.hammertime.request_engine.request_engine.proxy, "http://127.0.0.1:8080")

    @async_test()
    async def test_scan_target_only_use_passive_detection_if_passive_parameter_is_true(self):
        self.vane.is_wordpress = make_mocked_coro(return_value=True)
        self.vane.identify_target_version = make_mocked_coro()
        self.vane.active_plugin_enumeration = make_mocked_coro()
        self.vane.passive_plugin_enumeration = MagicMock(return_value={})
        self.vane.passive_theme_enumeration = MagicMock(return_value=[])
        self.vane.active_theme_enumeration = make_mocked_coro()
        self.vane.list_component_vulnerabilities = MagicMock()
        self.vane.hammertime.request = make_mocked_coro(return_value=MagicMock())
        self.vane._load_meta_list = MagicMock(return_value=("meta_list", "errors"))

        await self.vane.scan_target("http://www.unit.test/", True, True, passive_only=True)

        self.vane.active_theme_enumeration.assert_not_called()
        self.vane.active_plugin_enumeration.assert_not_called()
        self.assertEqual(len(self.vane.passive_theme_enumeration.mock_calls), 1)
        self.assertEqual(len(self.vane.passive_plugin_enumeration.mock_calls), 1)

    @async_test()
    async def test_request_target_home_page_make_hammertime_request_for_target_url(self):
        target_url = "http://www.example.com/"
        self.vane.hammertime.request = make_mocked_coro(return_value=Entry.create(target_url))

        await self.vane._request_target_home_page(target_url)

        self.vane.hammertime.request.assert_called_once_with(target_url)

    @async_test()
    async def test_request_target_home_page_return_hammertime_response_for_request(self):
        target_url = "http://www.example.com/"
        entry = Entry.create(target_url, response="response")
        self.vane.hammertime.request = make_mocked_coro(return_value=entry)

        response = await self.vane._request_target_home_page(target_url)

        self.assertEqual(response, "response")

    @async_test()
    async def test_request_target_home_page_raises_hammertime_exception(self):
        target_url = "http://www.example.com/"
        self.vane.hammertime.request = make_mocked_coro(raise_exception=HammerTimeException())

        with self.assertRaises(HammerTimeException):
            await self.vane._request_target_home_page(target_url)

    @async_test()
    async def test_get_files_for_version_identification_fetch_target_homepage(self):
        target_url = "http://www.example.com/"
        self.vane.hammertime.request = make_mocked_coro(return_value=MagicMock())
        homepage_response = MagicMock()
        self.vane._request_target_home_page = make_mocked_coro(return_value=homepage_response)

        response_list = await self.vane._get_files_for_version_identification(target_url)

        self.vane._request_target_home_page.assert_called_once_with(target_url)
        self.assertIn(homepage_response, response_list)

    @async_test()
    async def test_get_files_for_version_identification_fetch_files_exposing_version(self):
        target_url = "http://www.example.com/"
        file_entry = MagicMock()
        self.vane.hammertime.request = make_mocked_coro(return_value=file_entry)
        self.vane._request_target_home_page = make_mocked_coro()

        response_list = await self.vane._get_files_for_version_identification(target_url)

        expected_calls = [call(target_url + "wp-login.php"), call(target_url + "wp-links-opml.php")]
        self.vane.hammertime.request.assert_has_calls(expected_calls)
        self.assertIn(file_entry.response, response_list)

    @async_test()
    async def test_get_files_for_version_identification_dont_fail_if_request_homepage_raise_exception(self):
        target_url = "http://www.example.com/"
        file_entry = MagicMock()
        self.vane.hammertime.request = make_mocked_coro(return_value=file_entry)
        self.vane._request_target_home_page = make_mocked_coro(raise_exception=HammerTimeException())

        response_list = await self.vane._get_files_for_version_identification(target_url)

        self.assertIn(file_entry.response, response_list)

    @async_test()
    async def test_get_files_for_version_identification_dont_fail_if_hammertime_request_raise_exception(self):
        target_url = "http://www.example.com/"
        file_response = MagicMock()
        self.vane.hammertime.request = make_mocked_coro(raise_exception=HammerTimeException())
        self.vane._request_target_home_page = make_mocked_coro(return_value=file_response)

        response_list = await self.vane._get_files_for_version_identification(target_url)

        self.assertIn(file_response, response_list)
