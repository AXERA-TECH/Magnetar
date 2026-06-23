#!/usr/bin/env python3
"""从设备监控页面获取板子信息"""
import re
import sys
import requests
from html.parser import HTMLParser

class BoardParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.boards = []
        self.current_row = []
        self.in_td = False

    def handle_starttag(self, tag, attrs):
        if tag == 'td':
            self.in_td = True
            self.current_row.append('')

    def handle_endtag(self, tag):
        if tag == 'td':
            self.in_td = False
        elif tag == 'tr' and len(self.current_row) >= 4:
            if 'Online' in self.current_row[0]:
                ip = self.current_row[2].strip()
                board_id = self.current_row[3].strip()
                if ip and board_id:
                    chip = self._extract_chip(board_id)
                    self.boards.append({'ip': ip, 'board_id': board_id, 'chip': chip})
            self.current_row = []

    def handle_data(self, data):
        if self.in_td and self.current_row:
            self.current_row[-1] += data.strip()

    def _extract_chip(self, board_id):
        match = re.search(r'(AX\d+[A-Z]*)', board_id, re.IGNORECASE)
        return match.group(1).upper() if match else 'Unknown'

def get_boards(url='http://10.126.33.124:25000/'):
    try:
        resp = requests.get(url, timeout=5)
        parser = BoardParser()
        parser.feed(resp.text)
        return parser.boards
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return []

if __name__ == '__main__':
    boards = get_boards()
    if not boards:
        print("No boards found")
        sys.exit(1)

    for i, b in enumerate(boards, 1):
        print(f"{i}. {b['chip']:10s} {b['ip']:15s} ({b['board_id']})")
