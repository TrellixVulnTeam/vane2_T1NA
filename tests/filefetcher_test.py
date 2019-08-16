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
from unittest.mock import ANY, MagicMock
from vane.filefetcher import FileFetcher
from hammertime.core import HammerTime
from aiohttp.test_utils import make_mocked_coro
import asyncio
from openwebvulndb.common.models import File, FileSignature, FileList
from hammertime.ruleset import StopRequest, RejectRequest
from fixtures import async_test, fake_future


class TestFileFetcher(TestCase):

    def setUp(self):
        signatures = [FileSignature(hash="hash"), FileSignature(hash="another-hash")]
        self.plugin_key = "my-plugin"
        self.files_to_fetch = FileList(key=self.plugin_key, producer="", files=[
                                        File(path="wp-content/plugins/my-plugin/script.js", signatures=signatures),
                                        File(path="wp-content/plugins/my-plugin/style.css", signatures=signatures),
                                        File(path="wp-content/plugins/my-plugin/readme.txt", signatures=signatures)])

    def _setup_async_test(self, loop):
        self.hammertime = HammerTime(loop=loop)
        self.fetcher = FileFetcher(self.hammertime, "www.example.com")

    @async_test()
    async def test_request_files_return_task_wrapping_hammertime_requests(self, loop):
        self._setup_async_test(loop)
        self.hammertime.request_engine.perform = self.fake_perform

        files_request = self.fetcher.request_files(self.plugin_key, self.files_to_fetch)

        key, fetched_files = await asyncio.wait_for(files_request, None, loop=loop)
        self.assertEqual(key, self.plugin_key)
        for file in fetched_files:
            self.assertIn(file.path, [file.path for file in self.files_to_fetch.files])
            self.assertEqual(file.hash, "fake-hash")

    @async_test()
    async def test_request_files_set_expected_hash_and_return_code_for_requests(self, loop):
        self._setup_async_test(loop)
        self.hammertime.request = MagicMock(return_value=fake_future(MagicMock(), loop=loop))

        await self.fetcher.request_files(self.plugin_key, self.files_to_fetch)

        expected_arguments = {"expected_hash": {"hash", "another-hash"}, "hash_algo": "SHA256",  "file_path": ANY,
                              "expected_status_code": 200}
        for args, kwargs in self.hammertime.request.call_args_list:
            self.assertEqual(kwargs["arguments"], expected_arguments)

    @async_test()
    async def test_awaiting_requests_ignores_timeout_errors(self, loop):
        self._setup_async_test(loop)
        self.hammertime.request_engine.perform = make_mocked_coro(raise_exception=StopRequest())

        requests = self.fetcher.request_files(self.plugin_key, self.files_to_fetch)

        try:
            await asyncio.wait_for(requests, None, loop=loop)
        except StopRequest:
            self.fail("Timeout error raised.")

    @async_test()
    async def test_fetcher_increase_timeout_count_on_stop_request(self, loop):
        self._setup_async_test(loop)
        self.hammertime.request_engine.perform = make_mocked_coro(raise_exception=StopRequest())

        requests = self.fetcher.request_files(self.plugin_key, self.files_to_fetch)

        await asyncio.wait_for(requests, None, loop=loop)

        self.assertEqual(self.fetcher.timeouts, len(self.files_to_fetch.files))

    @async_test()
    async def test_fetcher_awaiting_requests_dont_increase_timeout_count_on_reject_request(self, loop):
        self._setup_async_test(loop)
        self.hammertime.request_engine.perform = make_mocked_coro(raise_exception=RejectRequest())

        requests = self.fetcher.request_files(self.plugin_key, self.files_to_fetch)

        await asyncio.wait_for(requests, None, loop=loop)

        self.assertEqual(self.fetcher.timeouts, 0)

    @async_test()
    async def test_request_files_reset_timeout_count(self, loop):
        self._setup_async_test(loop)
        self.hammertime.request_engine.perform = self.fake_perform
        self.fetcher.timeouts = 10

        self.fetcher.request_files(self.plugin_key, self.files_to_fetch)

        self.assertEqual(self.fetcher.timeouts, 0)

    @async_test()
    async def test_awaiting_requests_ignore_file_if_no_hash(self, loop):
        self._setup_async_test(loop)
        self.hammertime.request_engine.perform = self.fake_perform_no_hash

        requests = self.fetcher.request_files(self.plugin_key, self.files_to_fetch)

        key, fetched_files = await asyncio.wait_for(requests, None, loop=loop)
        self.assertEqual(len(fetched_files), 0)

    @staticmethod
    async def fake_perform(entry, *args, **kwargs):
        entry.result.hash = "fake-hash"
        return entry

    @staticmethod
    async def fake_perform_no_hash(entry, *args, **kwargs):
        return entry
