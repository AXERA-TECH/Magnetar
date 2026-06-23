#!/bin/bash
# 测试板子SSH连接和ax_run_model

test_board() {
    local ip=$1
    local chip=$2

    echo "Testing $chip ($ip):"

    result=$(expect -c "
        set timeout 5
        spawn ssh -o StrictHostKeyChecking=no root@$ip \"which ax_run_model && ax_run_model --version 2>&1 | head -3\"
        expect \"password:\"
        send \"123456\r\"
        expect eof
    " 2>&1)

    if echo "$result" | grep -q "/opt/bin/ax_run_model"; then
        echo "✓ Connected, ax_run_model found"
        echo "$result" | grep -A 2 "ax_run_model"
    else
        echo "✗ Failed or ax_run_model not found"
    fi
    echo ""
}

test_board "10.126.33.140" "AX650N"
test_board "10.126.33.137" "AX630C"
test_board "10.126.33.244" "AX650A"
