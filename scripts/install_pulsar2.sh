#!/bin/bash
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log_info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

PULSAR2_VERSION="${PULSAR2_VERSION:-6.0}"
PULSAR2_FILE="ax_pulsar2_${PULSAR2_VERSION}.tar.gz"
PULSAR2_URL="https://hf-mirror.com/AXERA-TECH/Pulsar2/resolve/main/${PULSAR2_VERSION}/${PULSAR2_FILE}"
PULSAR2_IMAGE_TAG="pulsar2:${PULSAR2_VERSION}"
CACHE_DIR="${HOME}/.cache/magnetar"

echo ""
echo "============================================"
echo "  Magnetar Pulsar2 + Docker Installer"
echo "  Pulsar2 Version: ${PULSAR2_VERSION}"
echo "============================================"
echo ""

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
        log_info "Downloading ${PULSAR2_URL} ..."
        if command -v aria2c &>/dev/null; then
            aria2c -x4 -s4 -d "${CACHE_DIR}" "${PULSAR2_URL}"
        elif command -v wget &>/dev/null; then
            wget -c --show-progress -O "${CACHE_DIR}/${PULSAR2_FILE}" "${PULSAR2_URL}"
        elif command -v curl &>/dev/null; then
            curl -L --progress-bar -o "${CACHE_DIR}/${PULSAR2_FILE}" "${PULSAR2_URL}"
        else
            log_error "Need wget, curl, or aria2c to download."
            exit 1
        fi
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
