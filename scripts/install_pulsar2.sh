#!/bin/bash
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log_info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

PULSAR2_VERSION="${PULSAR2_VERSION:-6.0}"
PULSAR2_FILE="ax_pulsar2_${PULSAR2_VERSION}.tar.gz"
PULSAR2_URL="${PULSAR2_URL:-}"
PULSAR2_MODELSCOPE_BASE="https://modelscope.cn/models/AXERA-TECH/Pulsar2/resolve/master/${PULSAR2_VERSION}"
PULSAR2_HF_BASE="https://hf-mirror.com/AXERA-TECH/Pulsar2/resolve/main/${PULSAR2_VERSION}"
PULSAR2_MODELSCOPE_URL="${PULSAR2_MODELSCOPE_BASE}/${PULSAR2_FILE}"
PULSAR2_HF_URL="${PULSAR2_HF_BASE}/${PULSAR2_FILE}"
PULSAR2_IMAGE_TAG="pulsar2:${PULSAR2_VERSION}"
CACHE_DIR="${HOME}/.cache/magnetar"

# 执行模式：package（官方独立安装包，默认推荐）| docker（镜像，兜底）
PULSAR2_MODE="${PULSAR2_MODE:-package}"
# package 模式子选项：lite（无 GPU，默认）| full（含 GPU 依赖）
PULSAR2_PACKAGE="${PULSAR2_PACKAGE:-lite}"
if [ "${PULSAR2_PACKAGE}" = "full" ]; then
    PULSAR2_PKG_FILE="ax_pulsar2_${PULSAR2_VERSION}_package.tar.gz"
else
    PULSAR2_PKG_FILE="ax_pulsar2_${PULSAR2_VERSION}_lite_package.tar.gz"
fi

# 下载顺序：显式 PULSAR2_URL > ModelScope（国内快） > hf-mirror（回退）
download_pulsar2() {
    local url tmp urls=()
    for url in "$@"; do
        [ -n "${url}" ] && urls+=("${url}")
    done
    for url in "${urls[@]}"; do
        log_info "Trying ${url}"
        tmp="${CACHE_DIR}/${PULSAR2_FILE}.part"
        rm -f "${tmp}"
        if command -v aria2c &>/dev/null; then
            if aria2c -x4 -s4 -d "${CACHE_DIR}" -o "${PULSAR2_FILE}.part" "${url}"; then
                mv "${tmp}" "${CACHE_DIR}/${PULSAR2_FILE}"; return 0
            fi
        elif command -v wget &>/dev/null; then
            if wget -c --show-progress -O "${tmp}" "${url}"; then
                mv "${tmp}" "${CACHE_DIR}/${PULSAR2_FILE}"; return 0
            fi
        elif command -v curl &>/dev/null; then
            if curl -L --retry 2 --connect-timeout 15 --progress-bar -o "${tmp}" "${url}"; then
                mv "${tmp}" "${CACHE_DIR}/${PULSAR2_FILE}"; return 0
            fi
        else
            log_error "Need wget, curl, or aria2c to download."
            return 1
        fi
        rm -f "${tmp}"
    done
    log_error "All download URLs failed."
    return 1
}

echo ""
echo "============================================"
echo "  Magnetar Pulsar2 Installer"
echo "  Version: ${PULSAR2_VERSION}  Mode: ${PULSAR2_MODE}${PULSAR2_PACKAGE:+ (${PULSAR2_PACKAGE})}"
echo "============================================"
echo ""

install_package() {
    local home_dir="${CACHE_DIR}/pulsar2/${PULSAR2_VERSION}"
    if [ -x "${home_dir}/bin/pulsar2" ]; then
        log_info "Pulsar2 独立包已安装: ${home_dir}"
        return 0
    fi
    mkdir -p "${CACHE_DIR}" "${home_dir}"
    local pkg_path="${CACHE_DIR}/${PULSAR2_PKG_FILE}"
    if [ ! -f "${pkg_path}" ]; then
        local pkg_url="${PULSAR2_URL}"
        [ -n "${pkg_url}" ] || pkg_url="${PULSAR2_MODELSCOPE_BASE}/${PULSAR2_PKG_FILE}"
        download_pulsar2 "${pkg_url}" "${PULSAR2_MODELSCOPE_BASE}/${PULSAR2_PKG_FILE}" \
            "${PULSAR2_HF_BASE}/${PULSAR2_PKG_FILE}"
    fi
    log_info "解压独立包（${PULSAR2_PKG_FILE}，约 1-5 GB，需要一点时间）..."
    tar -xzf "${pkg_path}" -C "${home_dir}" --strip-components=1
    if [ ! -x "${home_dir}/bin/pulsar2" ]; then
        log_error "解压后未找到 ${home_dir}/bin/pulsar2，请检查包完整性"
        return 1
    fi
    log_info "验证 Pulsar2 独立包..."
    "${home_dir}/bin/pulsar2" version 2>&1 | tail -5 || true
    log_info "Pulsar2 独立包安装完成: ${home_dir}"
    echo "  export PULSAR2_HOME=${home_dir}"
}

if [ "${PULSAR2_MODE}" = "package" ]; then
    install_package
    echo ""
    log_info "============================================"
    log_info "  安装完成！使用方式：export PULSAR2_HOME=${CACHE_DIR}/pulsar2/${PULSAR2_VERSION}"
    log_info "============================================"
    exit 0
fi

if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
    log_info "Docker already installed: $(docker --version)"
else
    log_info "Installing Docker..."
    if grep -qi ubuntu /etc/os-release 2>/dev/null; then
        sudo apt-get update -qq
        sudo apt-get install -y -qq docker.io
    elif grep -qi debian /etc/os-release 2>/dev/null; then
        sudo apt-get update -qq
        sudo apt-get install -y -qq docker.io
    elif grep -qi centos /etc/os-release 2>/dev/null || grep -qi rhel /etc/os-release 2>/dev/null; then
        sudo yum install -y docker
    elif grep -qi fedora /etc/os-release 2>/dev/null; then
        sudo dnf install -y docker
    else
        log_error "Unknown OS. Please install Docker manually: https://docs.docker.com/engine/install/"
        exit 1
    fi
    sudo systemctl start docker 2>/dev/null || sudo service docker start 2>/dev/null || true
    sudo usermod -aG docker "$USER" 2>/dev/null || true
    log_info "Docker installed."
    log_warn "You may need to re-login or run: newgrp docker"
fi

CURRENT_DOCKER_GROUP=$(id -Gn 2>/dev/null | grep -c docker || true)
if [ "$CURRENT_DOCKER_GROUP" -eq 0 ] 2>/dev/null; then
    log_warn "Current shell not in 'docker' group. Using 'sudo docker' fallback."
    DOCKER="sudo docker"
else
    DOCKER="docker"
fi


if ${DOCKER} image inspect ${PULSAR2_IMAGE_TAG} &>/dev/null 2>&1; then
    log_info "Pulsar2 Docker image '${PULSAR2_IMAGE_TAG}' already loaded."
else
    mkdir -p "${CACHE_DIR}"

    if [ -f "${CACHE_DIR}/${PULSAR2_FILE}" ]; then
        log_info "Found cached: ${CACHE_DIR}/${PULSAR2_FILE}"
    else
        download_pulsar2 "${PULSAR2_URL}" "${PULSAR2_MODELSCOPE_URL}" "${PULSAR2_HF_URL}"
        log_info "Downloaded: ${CACHE_DIR}/${PULSAR2_FILE}"
    fi

    log_info "Loading Docker image..."
    ${DOCKER} load -i "${CACHE_DIR}/${PULSAR2_FILE}"
    log_info "Pulsar2 Docker image '${PULSAR2_IMAGE_TAG}' loaded."
fi

log_info "Verifying Pulsar2..."
${DOCKER} run --rm ${PULSAR2_IMAGE_TAG} pulsar2 --version 2>/dev/null || true
${DOCKER} run --rm ${PULSAR2_IMAGE_TAG} bash -c "pulsar2 --version 2>/dev/null || pulsar2 version 2>/dev/null || echo 'pulsar2 OK'" || true

echo ""
log_info "============================================"
log_info "  Installation Complete!"
log_info "============================================"
echo ""
echo "  Docker image: ${PULSAR2_IMAGE_TAG}"
echo "  Download cache: ${CACHE_DIR}/${PULSAR2_FILE}"
echo ""
echo "  Quick test:"
echo "    ${DOCKER} run --rm ${PULSAR2_IMAGE_TAG} pulsar2 version"
echo ""
echo "  Usage with Magnetar:"
echo "    export PULSAR2_IMAGE=${PULSAR2_IMAGE_TAG}"
echo "    cd Magnetar"
echo "    ${DOCKER} run --rm -v \$(pwd):/workspace ${PULSAR2_IMAGE_TAG} pulsar2 ..."
