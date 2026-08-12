"""LLM 上板路径租约安全测试（mock SSH，不碰真实板子）。"""
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from magnetar.stages import llm  # noqa: E402

BOARD = {"host": "10.0.0.1", "user": "root", "port": 22, "password": "x"}


class LlmBoardLeaseTest(unittest.TestCase):
    def _lease(self):
        return mock.Mock(token="tok123",
                         work_root="/tmp/magnetar-lease/tok123")

    def test_serve_uses_lease_namespace(self):
        cmds = []

        def fake_ssh(board, cmd, timeout=120, max_tail=None):
            cmds.append(cmd)
            if "curl" in cmd:
                return "200"
            if "nohup axllm serve" in cmd:
                return "4321\n"
            return ""

        with mock.patch("magnetar.board_util.acquire_board_lease",
                        return_value=self._lease()) as acq, \
             mock.patch("magnetar.board_util.ssh", side_effect=fake_ssh), \
             mock.patch("magnetar.board_util.scp_to"):
            rd = llm.serve_axllm(BOARD, Path("/model"), port=8000)
        acq.assert_called_once()
        self.assertTrue(rd.startswith("/tmp/magnetar-lease/tok123/serve/"))
        self.assertFalse(any("/tmp/magnetar_llm_" in c for c in cmds))
        self.assertFalse(any("rm -rf /tmp/magnetar" in c and "magnetar-lease" not in c
                             for c in cmds))
        self.assertTrue(any("serve.json" in c and "tok123" in c for c in cmds))

    def test_serve_with_remote_root_skips_lease(self):
        with mock.patch("magnetar.board_util.acquire_board_lease",
                        side_effect=AssertionError("不应申请租约")) as acq, \
             mock.patch("magnetar.board_util.ssh", return_value="200"), \
             mock.patch("magnetar.board_util.scp_to"):
            rd = llm.serve_axllm(BOARD, Path("/model"), remote_root="/custom/rd")
        self.assertTrue(rd.startswith("/custom/rd/"))

    def test_stop_serve_requires_rd(self):
        with mock.patch("magnetar.board_util.ssh") as ssh:
            with self.assertRaises(RuntimeError):
                llm.stop_serve(BOARD)
        ssh.assert_not_called()

    def test_stop_serve_kills_own_pid_not_pkill(self):
        cmds = []

        def fake_ssh(board, cmd, timeout=120, max_tail=None):
            cmds.append(cmd)
            if "cat /tmp/magnetar-lease/tok123/serve/serve.json" in cmd:
                return '{"pid": "4321", "token": "tok123", "rd": "/tmp/magnetar-lease/tok123/serve"}'
            return ""

        with mock.patch("magnetar.board_util.ssh", side_effect=fake_ssh):
            llm.stop_serve(BOARD, "/tmp/magnetar-lease/tok123/serve")
        self.assertFalse(any("pkill" in c for c in cmds))
        self.assertTrue(any("kill 4321" in c for c in cmds))
        self.assertTrue(any("rm -rf /tmp/magnetar-lease/tok123" in c for c in cmds))
        self.assertTrue(any("grep -qF 'tok123' /tmp/magnetar-lease/lock/lease.json" in c
                            for c in cmds))

    def test_install_axllm_holds_lease(self):
        cmds = []
        state = {"attempts": 0}

        def fake_ssh(board, cmd, timeout=120, max_tail=None):
            cmds.append(cmd)
            state["attempts"] += 1
            if state["attempts"] <= 2:
                raise RuntimeError("not installed")
            return "axllm ok"

        with mock.patch("magnetar.board_util.ssh", side_effect=fake_ssh), \
             mock.patch("magnetar.board_util.board_lease") as bl:
            llm.install_axllm(BOARD)
        bl.assert_called_once()
        self.assertTrue(any("curl -fsSL" in c for c in cmds))


if __name__ == "__main__":
    unittest.main()
