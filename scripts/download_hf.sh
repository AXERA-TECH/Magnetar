#!/usr/bin/env bash
# 用 hf-mirror 的 hfd.sh 下载 HuggingFace 大文件（模型/数据集，多线程加速）。
#
# 用法:
#   scripts/download_hf.sh <REPO_ID> [hfd 参数...]
# 示例:
#   scripts/download_hf.sh Qwen/Qwen2.5-7B-Instruct --local-dir origin/Qwen2.5-7B-Instruct -x 8
#   scripts/download_hf.sh AXERA-TECH/Some-Model --exclude '*.onnx' --tool wget
#
# hfd.sh 会缓存到 ~/.cache/magnetar/hfd.sh（可用 MAGNETAR_HFD_CACHE 覆盖），
# 端点默认 hf-mirror（HF_ENDPOINT 可覆盖，置空/改官方即直连）。
set -euo pipefail

HFD_URL="${HFD_URL:-https://hf-mirror.com/hfd/hfd.sh}"
HFD_CACHE="${MAGNETAR_HFD_CACHE:-${HOME}/.cache/magnetar/hfd.sh}"
HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"

if [ "$#" -lt 1 ]; then
    echo "用法: $0 <REPO_ID> [hfd 参数...]" >&2
    echo "示例: $0 Qwen/Qwen2.5-7B-Instruct --local-dir origin/qwen -x 8" >&2
    exit 2
fi

mkdir -p "$(dirname "$HFD_CACHE")"
if [ ! -f "$HFD_CACHE" ]; then
    echo "[download_hf] 获取 hfd.sh: ${HFD_URL}"
    if command -v curl &>/dev/null; then
        curl -fsSL --retry 2 --connect-timeout 15 -o "$HFD_CACHE" "$HFD_URL"
    else
        wget -q -O "$HFD_CACHE" "$HFD_URL"
    fi
fi
chmod a+x "$HFD_CACHE"

# hfd.sh 默认用 aria2c 多线程；缺 aria2c 且用户未显式指定 --tool 时回退 wget
if ! command -v aria2c &>/dev/null && [[ " $* " != *" --tool "* ]]; then
    echo "[download_hf] 未找到 aria2c，回退 wget（建议: apt install aria2）" >&2
    set -- "$@" --tool wget
fi

export HF_ENDPOINT
echo "[download_hf] HF_ENDPOINT=${HF_ENDPOINT}"
exec "$HFD_CACHE" "$@"
