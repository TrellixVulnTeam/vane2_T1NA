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

from vane.theme import Theme


class TestTheme(TestCase):

    def test_constructor_raise_value_error_if_url_is_not_a_valid_theme_url(self):
        junk_url = "https://www.mywebsite.com/something.html"
        valid_url_with_file_at_end = "https://www.delve-labs.com/wp-content/themes/delvelabs/style.css"
        url_with_junk_at_beginning = "link to theme: https://www.delve-labs.com/wp-content/themes/delvelabs"

        with self.assertRaises(ValueError):
            Theme(junk_url)
        with self.assertRaises(ValueError):
            Theme(valid_url_with_file_at_end)
        with self.assertRaises(ValueError):
            Theme(url_with_junk_at_beginning)

    def test_constructor_accept_relative_url(self):
        relative_url = "/wp-content/themes/my-theme"
        try:
            Theme(relative_url)
        except ValueError:
            self.fail("Theme constructor raised an error for a relative url.")

    def test_name_return_name_from_theme_url(self):
        theme = Theme("https://www.delve-labs.com/wp-content/themes/delvelabs")

        self.assertEqual(theme.name, "delvelabs")

    def test_name_return_name_from_vip_theme_url(self):
        theme = Theme("https://s0.wp.com/wp-content/themes/vip/techcrunch-2013")

        self.assertEqual(theme.name, "techcrunch-2013")

    def test_name_return_name_from_relative_theme_url(self):
        theme = Theme("/wp-content/themes/my-theme")

        self.assertEqual(theme.name, "my-theme")

    def test_themes_equal_if_themes_have_same_name(self):
        theme0 = Theme("https://www.mysite.com/wp-content/themes/my-theme")
        theme1 = Theme("https://www.mysite.com/wp-content/themes/my-theme")

        self.assertEqual(theme0, theme1)

    def test_themes_equal_is_false_if_themes_have_different_name(self):
        theme0 = Theme("https://www.mysite.com/wp-content/themes/my-theme")
        theme1 = Theme("https://www.mysite.com/wp-content/themes/another-theme")

        self.assertNotEqual(theme0, theme1)