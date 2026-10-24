#!/usr/bin/env bash
# 智慧芽专利助手 (WorkBuddy 通用版) - macOS / Linux Python 环境自动检测与自举启动器

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HELPER_PY="$SCRIPT_DIR/zhihuiya_helper.py"
export PYTHONIOENCODING="utf-8"

find_python() {
    for cmd in python3 python "$HOME/.local/python3/bin/python3" "/opt/homebrew/bin/python3" "/usr/local/bin/python3"; do
        if command -v "$cmd" >/dev/null 2>&1; then
            if "$cmd" -c "import sys, urllib.request, ssl, json; sys.exit(0 if sys.version_info >= (3, 7) else 1)" >/dev/null 2>&1; then
                echo "$cmd"
                return 0
            fi
        fi
    done
    return 1
}

install_python() {
    echo "[Auto-Setup] 未检测到 Python 3 环境，正在使用 Micromamba 便携环境自动配置免管理员权限的 Python 3.11..." >&2
    TARGET_DIR="$HOME/.local/python3"
    mkdir -p "$TARGET_DIR"
    OS_NAME="$(uname -s)"
    ARCH_NAME="$(uname -m)"

    if [ "$OS_NAME" = "Darwin" ]; then
        if [ "$ARCH_NAME" = "arm64" ]; then
            PLATFORM="osx-arm64"
        else
            PLATFORM="osx-64"
        fi
    else
        if [ "$ARCH_NAME" = "aarch64" ] || [ "$ARCH_NAME" = "arm64" ]; then
            PLATFORM="linux-aarch64"
        else
            PLATFORM="linux-64"
        fi
    fi

    MAMBA_BIN="$TARGET_DIR/micromamba"
    curl -Ls "https://micro.mamba.pm/api/micromamba/$PLATFORM/latest" | tar -xvj -C "$TARGET_DIR" --strip-components=1 bin/micromamba >/dev/null 2>&1 || true
    if [ -x "$MAMBA_BIN" ]; then
        "$MAMBA_BIN" create -y -p "$TARGET_DIR" python=3.11 -c https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge/ >/dev/null 2>&1 || \
        "$MAMBA_BIN" create -y -p "$TARGET_DIR" python=3.11 -c conda-forge >/dev/null 2>&1
        if [ -x "$TARGET_DIR/bin/python3" ]; then
            echo "$TARGET_DIR/bin/python3"
            return 0
        fi
    fi

    # 备用系统级包管理器
    if command -v brew >/dev/null 2>&1; then
        brew install python3 >&2
    elif command -v apt-get >/dev/null 2>&1; then
        sudo apt-get update && sudo apt-get install -y python3 >&2
    elif command -v yum >/dev/null 2>&1; then
        sudo yum install -y python3 >&2
    fi

    find_python
}

PY_EXE="$(find_python || install_python)"
if [ "$1" = "--ensure-only" ]; then
    echo "PYTHON_OK=$PY_EXE"
    exit 0
fi

exec "$PY_EXE" "$HELPER_PY" "$@"
