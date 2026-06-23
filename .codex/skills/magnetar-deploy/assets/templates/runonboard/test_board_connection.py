#!/usr/bin/env python3
"""测试板子SSH连接和ax_run_model可用性"""
import sys
import paramiko

def test_board(ip, password='123456', user='root'):
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(ip, username=user, password=password, timeout=5)

        stdin, stdout, stderr = client.exec_command('which ax_run_model')
        ax_path = stdout.read().decode().strip()

        if ax_path:
            stdin, stdout, stderr = client.exec_command('ax_run_model --version 2>&1 | head -3')
            version = stdout.read().decode().strip()
            print(f"✓ {ip}: {ax_path}")
            print(f"  {version}")
        else:
            print(f"✗ {ip}: ax_run_model not found")

        client.close()
        return True
    except Exception as e:
        print(f"✗ {ip}: {e}")
        return False

if __name__ == '__main__':
    boards = [
        ('10.126.33.140', 'AX650N'),
        ('10.126.33.137', 'AX630C'),
        ('10.126.33.244', 'AX650A'),
    ]

    for ip, chip in boards:
        print(f"\n{chip} ({ip}):")
        test_board(ip)
