"""板端租约（防抢占/防误清）逻辑测试：mock SSH，不依赖真实板子。"""
import sys
import unittest
from unittest import mock
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from magnetar.board_util import (  # noqa: E402
    BOARD_LEASE_ROOT,
    BoardBusyError,
    acquire_board_lease,
    board_workdir,
    release_board_lease,
)

BOARD = {"host": "10.0.0.1", "user": "root", "port": 22, "password": "x"}
LOCK = f"{BOARD_LEASE_ROOT}/lock"


class BoardLeaseTest(unittest.TestCase):
    def test_lease_token_unique_and_safe(self):
        from magnetar.board_util import _lease_token
        t1, t2 = _lease_token("user@host:1"), _lease_token("user@host:1")
        self.assertNotEqual(t1, t2)
        self.assertTrue(t1.startswith("user_host_1-"))
        self.assertNotIn(" ", t1)

    def test_board_workdir_under_lease(self):
        lease = mock.Mock(work_root=f"{BOARD_LEASE_ROOT}/tok")
        self.assertEqual(board_workdir(lease, "work"),
                         f"{BOARD_LEASE_ROOT}/tok/work")

    def test_acquire_and_release(self):
        calls = []

        def fake_ssh(board, cmd, timeout=120, max_tail=None):
            calls.append(cmd)
            if cmd.startswith("cat > ") or cmd.startswith("mkdir /tmp/magnetar-lease/lock"):
                return ""
            return ""

        with mock.patch("magnetar.board_util.ssh", side_effect=fake_ssh):
            lease = acquire_board_lease(BOARD)
            self.assertEqual(lease.dir, LOCK)
            self.assertTrue(lease.work_root.startswith(f"{BOARD_LEASE_ROOT}/"))
            release_board_lease(lease)
        self.assertTrue(any("rm -rf" in c and lease.token in c for c in calls))

    def test_busy_raises_with_owner(self):
        calls = []

        def fake_ssh(board, cmd, timeout=120, max_tail=None):
            calls.append(cmd)
            if cmd.startswith(f"mkdir {LOCK}"):
                raise RuntimeError("dir exists")
            if cmd.startswith(f"cat {LOCK}/lease.json"):
                return '{"token": "other-token", "owner": "alice:1234", "note": "runonboard demo"}'
            return ""

        with mock.patch("magnetar.board_util.ssh", side_effect=fake_ssh), \
             mock.patch("time.sleep"):
            with self.assertRaises(BoardBusyError) as ctx:
                acquire_board_lease(BOARD)
        self.assertIn("alice:1234", str(ctx.exception))
        self.assertIn("demo", str(ctx.exception))
        # 绝不能直接删别人的锁（只允许 find 按过期时间清理租约根目录）
        self.assertFalse(any(c.startswith("rm -rf") for c in calls))

    def test_expired_lease_cleaned_then_acquired(self):
        calls = []
        state = {"mkdir_attempts": 0}

        def fake_ssh(board, cmd, timeout=120, max_tail=None):
            calls.append(cmd)
            if cmd.startswith(f"mkdir {LOCK}"):
                state["mkdir_attempts"] += 1
                if state["mkdir_attempts"] == 1:
                    raise RuntimeError("dir exists")
                return ""
            if cmd.startswith(f"cat {LOCK}/lease.json"):
                return ""  # 过期锁已被 find 清掉，无占用
            if cmd.startswith("cat > ") or "mkdir -p" in cmd:
                return ""
            return ""

        with mock.patch("magnetar.board_util.ssh", side_effect=fake_ssh), \
             mock.patch("time.sleep") as sleep:
            lease = acquire_board_lease(BOARD, ttl=600)
        # 超时租约通过 find ... -mmin +10 -exec rm -rf 清理，且只限租约根目录
        self.assertTrue(any(
            "find /tmp/magnetar-lease" in c and "-mmin +10" in c for c in calls))
        self.assertTrue(sleep.called)

    def test_read_lock_info_tolerates_ssh_warning_prefix(self):
        from magnetar.board_util import _read_lock_info
        with mock.patch("magnetar.board_util.ssh", return_value=(
            "Warning: Permanently added '10.0.0.1' (ED25519) to the list of known hosts.\n"
            '{"token": "t", "owner": "bob:1", "note": "demo"}'
        )):
            info = _read_lock_info(BOARD)
        self.assertEqual(info["owner"], "bob:1")

    def test_list_board_leases_parses_lease_json(self):
        from magnetar.board_util import list_board_leases
        out = (
            "tok-a\t{\"token\": \"tok-a\", \"owner\": \"alice:1\", \"note\": \"simulate\"}\n"
            "tok-b\t{\"token\": \"tok-b\", \"owner\": \"bob:2\", \"note\": \"runonboard\"}\n"
        )
        with mock.patch("magnetar.board_util.ssh", return_value=out):
            leases = list_board_leases(BOARD)
        self.assertEqual(set(leases), {"tok-a", "tok-b"})
        self.assertEqual(leases["tok-a"]["owner"], "alice:1")

    def test_board_lease_report_marks_expired(self):
        import time
        from magnetar.board_util import board_lease_report
        now = int(time.time())
        lease_out = (
            "tok-old\t{\"token\": \"tok-old\", \"owner\": \"dead:1\", \"note\": \"crashed\"}\n"
            "tok-new\t{\"token\": \"tok-new\", \"owner\": \"alive:2\", \"note\": \"running\"}\n"
        )
        stat_out = f"tok-old\t{now - 7200}\ntok-new\t{now - 60}\n"

        def fake_ssh(board, cmd, timeout=120, max_tail=None):
            if "lease.json" in cmd and "stat -c" in cmd:
                return stat_out
            return lease_out

        with mock.patch("magnetar.board_util.ssh", side_effect=fake_ssh):
            report = board_lease_report(BOARD, ttl_min=30)
        by_token = {i["token"]: i for i in report}
        self.assertTrue(by_token["tok-old"]["expired"])
        self.assertFalse(by_token["tok-new"]["expired"])
        self.assertEqual(by_token["tok-old"]["owner"], "dead:1")


if __name__ == "__main__":
    unittest.main()
