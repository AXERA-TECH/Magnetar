"""国内镜像 helper 单元测试。"""
import json
import os
import unittest
from unittest import mock

from magnetar.net_util import (
    DEFAULT_GH_PROXY,
    gh_proxy_url,
    modelscope_available,
    modelscope_url,
    pypi_index,
)


class NetUtilTest(unittest.TestCase):
    def test_github_url_prefixed_by_default(self):
        url = "https://github.com/a/b.git"
        self.assertEqual(gh_proxy_url(url), f"{DEFAULT_GH_PROXY}/{url}")

    def test_raw_github_url_prefixed(self):
        url = "https://raw.githubusercontent.com/a/b/install.sh"
        self.assertEqual(gh_proxy_url(url), f"{DEFAULT_GH_PROXY}/{url}")

    def test_non_github_url_untouched(self):
        url = "https://example.com/a.zip"
        self.assertEqual(gh_proxy_url(url), url)

    def test_explicit_empty_cfg_disables_proxy(self):
        url = "https://github.com/a/b.git"
        self.assertEqual(gh_proxy_url(url, cfg={"GH_PROXY": ""}), url)

    def test_cfg_proxy_wins_over_default(self):
        url = "https://github.com/a/b.git"
        self.assertEqual(
            gh_proxy_url(url, cfg={"GH_PROXY": "https://gh.example.com"}),
            "https://gh.example.com/" + url,
        )

    def test_env_empty_disables_proxy(self):
        old = os.environ.get("GH_PROXY")
        os.environ["GH_PROXY"] = ""
        try:
            self.assertEqual(gh_proxy_url("https://github.com/a/b.git"),
                             "https://github.com/a/b.git")
        finally:
            if old is None:
                os.environ.pop("GH_PROXY", None)
            else:
                os.environ["GH_PROXY"] = old

    def test_pypi_default_is_aliyun(self):
        self.assertEqual(pypi_index(), "https://mirrors.aliyun.com/pypi/simple/")

    def test_pypi_explicit_empty_returns_official(self):
        self.assertEqual(pypi_index({"PIP_INDEX_URL": ""}),
                         "https://pypi.org/simple/")

    def test_modelscope_url_page_and_file(self):
        self.assertEqual(
            modelscope_url("AXERA-TECH/Pulsar2"),
            "https://modelscope.cn/models/AXERA-TECH/Pulsar2",
        )
        self.assertEqual(
            modelscope_url("AXERA-TECH/Pulsar2", path="6.0/ax_pulsar2_6.0.tar.gz"),
            "https://modelscope.cn/models/AXERA-TECH/Pulsar2/resolve/"
            "master/6.0/ax_pulsar2_6.0.tar.gz",
        )

    def test_modelscope_available_true(self):
        resp = mock.MagicMock()
        resp.read.return_value = json.dumps({"Code": 200, "Data": {"Name": "x"}}).encode()
        resp.__enter__.return_value = resp
        with mock.patch("urllib.request.urlopen", return_value=resp):
            self.assertTrue(modelscope_available("AXERA-TECH/Pulsar2"))

    def test_modelscope_available_false_on_404(self):
        import urllib.error
        with mock.patch("urllib.request.urlopen",
                        side_effect=urllib.error.HTTPError(
                            "url", 404, "Not Found", None, None)):
            self.assertFalse(modelscope_available("AXERA-TECH/Nope"))


if __name__ == "__main__":
    unittest.main()
