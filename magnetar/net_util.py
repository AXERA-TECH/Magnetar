"""网络访问工具：国内镜像默认（HF_ENDPOINT / GH_PROXY / PyPI 镜像）。

约定：
- HuggingFace 下载默认走 ``HF_ENDPOINT=https://hf-mirror.com``；
- GitHub 的 git clone / raw 文件下载默认经 ``GH_PROXY``（如 gh-proxy.com）代理，
  海外用户把 ``GH_PROXY`` 置空字符串即恢复直连；
- uv / pip 包安装默认使用阿里云 PyPI 镜像（``PIP_INDEX_URL``，可覆盖为清华等）。

配置来源优先级：环境变量 > .magnetarrc（``magnetar.config`` 已解析）> 代码默认值。
"""
import os
import json
import urllib.request

DEFAULT_GH_PROXY = "https://gh-proxy.com"
DEFAULT_PYPI_INDEX = "https://mirrors.aliyun.com/pypi/simple/"
MODELSCOPE_HUB = "https://modelscope.cn"
MODELSCOPE_API = "https://www.modelscope.cn"


def gh_proxy_url(url: str, cfg: dict | None = None) -> str:
    """GitHub 直链套国内代理；GH_PROXY 未配置或为空时原样返回。"""
    if cfg is not None and "GH_PROXY" in cfg:
        proxy = cfg["GH_PROXY"]
    elif "GH_PROXY" in os.environ:
        proxy = os.environ["GH_PROXY"]
    else:
        proxy = DEFAULT_GH_PROXY
    if not proxy:
        return url
    if url.startswith("https://github.com/") or url.startswith(
            "https://raw.githubusercontent.com/"):
        return f"{proxy.rstrip('/')}/{url}"
    return url


def pypi_index(cfg: dict | None = None) -> str:
    """PyPI 镜像地址：环境变量 / 配置 > 阿里云默认；显式置空回官方 PyPI。"""
    for src in (os.environ, cfg or {}):
        if "PIP_INDEX_URL" not in src:
            continue
        v = src["PIP_INDEX_URL"]
        return v or "https://pypi.org/simple/"
    return DEFAULT_PYPI_INDEX


def uv_env(cfg: dict | None = None) -> dict:
    """给 uv / pip 子进程设置的国内镜像环境变量。"""
    index = pypi_index(cfg)
    return {
        "UV_DEFAULT_INDEX": index,
        "UV_INDEX_URL": index,
        "PIP_INDEX_URL": index,
    }


def modelscope_url(model_id: str, path: str | None = None,
                   revision: str = "master") -> str:
    """ModelScope 页面 / resolve 文件 URL（HF 仓库 ID 约定一致，org/name 直接映射）。"""
    model_id = model_id.strip("/")
    if path:
        from urllib.parse import quote
        return (f"{MODELSCOPE_HUB}/models/{model_id}/resolve/{quote(revision)}/"
                f"{quote(path, safe='/')}")
    return f"{MODELSCOPE_HUB}/models/{model_id}"


def modelscope_available(model_id: str, timeout: int = 10) -> bool:
    """探测 ModelScope 上是否存在该仓库（404/网络错误返回 False）。

    用于“涉及 HF 的东西先查 ModelScope”规则：HF repo id 直接映射到 ModelScope
    （如 Qwen/Qwen2.5-0.5B、AXERA-TECH/Pulsar2 两侧都存在）。
    """
    url = f"{MODELSCOPE_API}/api/v1/models/{model_id.strip('/')}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            body = json.loads(r.read().decode("utf-8"))
            return bool(body.get("Data"))
    except Exception:
        return False
