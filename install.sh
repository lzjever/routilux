#!/bin/bash
#
# Routilux Installer - Universal installation script for Mac and Linux
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/lzjever/routilux/main/install.sh | bash
#   wget -qO- https://raw.githubusercontent.com/lzjever/routilux/main/install.sh | bash
#
# Options:
#   METHOD=uv    - Use uv tool install (default, recommended)
#   METHOD=pipx  - Use pipx install
#   METHOD=pip   - Use pip --user install (not recommended)
#   VERSION=x.x.x - Install specific version
#
# Examples:
#   METHOD=pipx curl -fsSL https://raw.githubusercontent.com/lzjever/routilux/main/install.sh | bash
#   VERSION=0.14.0 curl -fsSL https://raw.githubusercontent.com/lzjever/routilux/main/install.sh | bash
#
set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
ROUTILUX_REPO="lzjever/routilux"
ROUTILUX_PYPI="routilux"
METHOD="${METHOD:-uv}"
VERSION="${VERSION:-}"
PREFIX="${PREFIX:-$HOME/.local}"

info() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

detect_os() {
    case "$(uname -s)" in
        Darwin*) echo "macos" ;;
        Linux*) echo "linux" ;;
        *) echo "unknown" ;;
    esac
}

detect_arch() {
    case "$(uname -m)" in
        x86_64|amd64) echo "x86_64" ;;
        arm64|aarch64) echo "arm64" ;;
        *) echo "unknown" ;;
    esac
}

check_python() {
    if command -v python3 &> /dev/null; then
        PYTHON=python3
    elif command -v python &> /dev/null; then
        PYTHON=python
    else
        error "Python 3 is required but not found. Please install Python 3.8+ first."
    fi

    PY_VERSION=$($PYTHON --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
    info "Found Python $PY_VERSION"

    # Check version >= 3.8
    MAJOR=$(echo $PY_VERSION | cut -d'.' -f1)
    MINOR=$(echo $PY_VERSION | cut -d'.' -f2)
    if [ "$MAJOR" -lt 3 ] || ([ "$MAJOR" -eq 3 ] && [ "$MINOR" -lt 8 ]); then
        error "Python 3.8+ is required. Found Python $PY_VERSION"
    fi
}

install_uv() {
    if command -v uv &> /dev/null; then
        success "uv is already installed"
        return 0
    fi

    info "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # Add to PATH for current session
    export PATH="$HOME/.local/bin:$PATH"

    if command -v uv &> /dev/null; then
        success "uv installed successfully"
    else
        error "Failed to install uv"
    fi
}

install_pipx() {
    if command -v pipx &> /dev/null; then
        success "pipx is already installed"
        return 0
    fi

    info "Installing pipx..."
    $PYTHON -m pip install --user pipx
    $PYTHON -m pipx ensurepath

    # Add to PATH for current session
    export PATH="$HOME/.local/bin:$PATH"

    if command -v pipx &> /dev/null; then
        success "pipx installed successfully"
    else
        error "Failed to install pipx"
    fi
}

install_routilux_uv() {
    info "Installing routilux with uv..."

    local pkg="routilux[cli]"
    if [ -n "$VERSION" ]; then
        pkg="routilux[cli]==$VERSION"
    fi

    uv tool install "$pkg"
    success "routilux installed with uv"
}

install_routilux_pipx() {
    info "Installing routilux with pipx..."

    local pkg="routilux[cli]"
    if [ -n "$VERSION" ]; then
        pkg="routilux[cli]==$VERSION"
    fi

    pipx install "$pkg"
    success "routilux installed with pipx"
}

install_routilux_pip() {
    warn "pip install is not recommended. Consider using uv or pipx instead."
    info "Installing routilux with pip..."

    local pkg="routilux[cli]"
    if [ -n "$VERSION" ]; then
        pkg="routilux[cli]==$VERSION"
    fi

    $PYTHON -m pip install --user "$pkg"
    success "routilux installed with pip"
}

verify_installation() {
    info "Verifying installation..."

    # Ensure PATH includes common locations
    export PATH="$HOME/.local/bin:$PATH"

    if command -v routilux &> /dev/null; then
        ROUTILUX_VERSION=$(routilux --version 2>&1 || echo "unknown")
        success "routilux is installed: $ROUTILUX_VERSION"

        echo ""
        echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo -e "${GREEN}  Installation complete!${NC}"
        echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo ""
        echo -e "${CYAN}Quick start:${NC}"
        echo ""
        echo "  routilux --help              # Show all commands"
        echo "  routilux init my-project     # Create a new project"
        echo "  routilux run workflow.yaml   # Run a workflow"
        echo "  routilux server start        # Start HTTP server"
        echo ""
        echo -e "${CYAN}Documentation:${NC} https://github.com/$ROUTILUX_REPO"
        echo ""
    else
        error "Installation verification failed. 'routilux' command not found.

Try one of these fixes:
  1. Restart your terminal
  2. Run: source ~/.bashrc  (or ~/.zshrc)
  3. Ensure ~/.local/bin is in your PATH"
    fi
}

print_banner() {
    echo ""
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${NC}                                                                  ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}   ${GREEN}██████╗ ██╗   ██╗████████╗███████╗██████╗ ███╗   ███╗${NC}         ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}   ${GREEN}██╔══██╗██║   ██║╚══██╔══╝██╔════╝██╔══██╗████╗ ████║${NC}         ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}   ${GREEN}██████╔╝██║   ██║   ██║   █████╗  ██████╔╝██╔████╔██║${NC}         ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}   ${GREEN}██╔═══╝ ██║   ██║   ██║   ██╔══╝  ██╔══██╗██║╚██╔╝██║${NC}         ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}   ${GREEN}██║     ╚██████╔╝   ██║   ███████╗██║  ██║██║ ╚═╝ ██║${NC}         ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}   ${GREEN}╚═╝      ╚═════╝    ╚═╝   ╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝${NC}         ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}                                                                  ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}   ${YELLOW}Event-driven Workflow Orchestration Framework${NC}                ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}   ${BLUE}Installer v1.0  •  Mac & Linux${NC}                                ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}                                                                  ${CYAN}║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

main() {
    print_banner

    OS=$(detect_os)
    ARCH=$(detect_arch)
    info "Detected: $OS on $ARCH"

    check_python

    case "$METHOD" in
        uv)
            install_uv
            install_routilux_uv
            ;;
        pipx)
            install_pipx
            install_routilux_pipx
            ;;
        pip)
            install_routilux_pip
            ;;
        *)
            error "Unknown installation method: $METHOD. Use uv, pipx, or pip."
            ;;
    esac

    verify_installation
}

main "$@"
