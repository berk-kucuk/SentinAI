#!/usr/bin/env bash
# SentinAI — Arch Linux Installer
# Supports: Arch Linux, Manjaro, EndeavourOS, and any pacman-based distro

set -euo pipefail

# ── Colors ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

# ── Helpers ──────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
DESKTOP_DIR="$HOME/.local/share/applications"
PYTHON_MIN_MAJOR=3
PYTHON_MIN_MINOR=10

step()    { echo -e "\n${BOLD}${CYAN}▸ $*${NC}"; }
info()    { echo -e "  ${BLUE}·${NC}  $*"; }
success() { echo -e "  ${GREEN}✓${NC}  $*"; }
warn()    { echo -e "  ${YELLOW}!${NC}  $*"; }
error()   { echo -e "\n  ${RED}✗  ERROR:${NC}  $*\n" >&2; exit 1; }
ask()     { echo -e "\n  ${BOLD}${YELLOW}?${NC}  $1"; }

# ── Banner ───────────────────────────────────────────────────────────────────
print_banner() {
    echo
    echo -e "${BOLD}${CYAN}  ┌─────────────────────────────────────────────────┐${NC}"
    echo -e "${BOLD}${CYAN}  │                                                 │${NC}"
    echo -e "${BOLD}${CYAN}  │   ███████╗███████╗███╗   ██╗████████╗██╗███╗   ██╗${NC}"
    echo -e "${BOLD}${CYAN}  │   ██╔════╝██╔════╝████╗  ██║╚══██╔══╝██║████╗  ██║${NC}"
    echo -e "${BOLD}${CYAN}  │   ███████╗█████╗  ██╔██╗ ██║   ██║   ██║██╔██╗ ██║${NC}"
    echo -e "${BOLD}${CYAN}  │   ╚════██║██╔══╝  ██║╚██╗██║   ██║   ██║██║╚██╗██║${NC}"
    echo -e "${BOLD}${CYAN}  │   ███████║███████╗██║ ╚████║   ██║   ██║██║ ╚████║${NC}"
    echo -e "${BOLD}${CYAN}  │   ╚══════╝╚══════╝╚═╝  ╚═══╝   ╚═╝   ╚═╝╚═╝  ╚═══╝${NC}"
    echo -e "${BOLD}${CYAN}  │                                                 │${NC}"
    echo -e "${BOLD}${CYAN}  │      AI-Powered Cybersecurity Assistant         │${NC}"
    echo -e "${BOLD}${CYAN}  │      Arch Linux Installer v1.0                  │${NC}"
    echo -e "${BOLD}${CYAN}  │                                                 │${NC}"
    echo -e "${BOLD}${CYAN}  └─────────────────────────────────────────────────┘${NC}"
    echo
}

# ── Pre-flight checks ────────────────────────────────────────────────────────
preflight_checks() {
    step "Pre-flight Checks"

    # Arch / pacman-based distro
    if ! command -v pacman &>/dev/null; then
        error "pacman not found. This installer requires an Arch-based Linux distribution."
    fi
    success "Arch-based distribution detected"

    # Determine sudo/root
    if [[ $EUID -eq 0 ]]; then
        SUDO=""
        warn "Running as root. It is recommended to run as a normal user with sudo access."
    elif command -v sudo &>/dev/null; then
        SUDO="sudo"
        success "sudo is available"
    else
        error "Neither root nor sudo is available. Please install sudo or run as root."
    fi

    # Python version
    if ! command -v python &>/dev/null && ! command -v python3 &>/dev/null; then
        error "Python is not installed."
    fi
    PYTHON_BIN=$(command -v python3 || command -v python)
    PYTHON_VERSION=$("$PYTHON_BIN" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
    PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

    if (( PYTHON_MAJOR < PYTHON_MIN_MAJOR )) || \
       (( PYTHON_MAJOR == PYTHON_MIN_MAJOR && PYTHON_MINOR < PYTHON_MIN_MINOR )); then
        error "Python ${PYTHON_MIN_MAJOR}.${PYTHON_MIN_MINOR}+ required. Found: ${PYTHON_VERSION}"
    fi
    success "Python ${PYTHON_VERSION} detected ($PYTHON_BIN)"

    # Script dir
    info "Install directory: ${SCRIPT_DIR}"
    if [[ ! -f "$SCRIPT_DIR/app.py" ]]; then
        error "app.py not found. Please run this script from the SentinAI project directory."
    fi
    success "Project directory verified"
}

# ── Detect AUR helper ────────────────────────────────────────────────────────
detect_aur_helper() {
    for helper in paru yay pikaur aurman; do
        if command -v "$helper" &>/dev/null; then
            AUR_HELPER="$helper"
            success "AUR helper detected: $AUR_HELPER"
            return
        fi
    done
    AUR_HELPER=""
    warn "No AUR helper found (paru/yay). AUR packages will be skipped."
}

# ── System packages ───────────────────────────────────────────────────────────
install_system_packages() {
    step "System Packages (pacman)"

    local PACMAN_PACKAGES=(
        "python"
        "python-pip"
        "python-pyqt6"          # Qt bindings — better from official repo on Arch
        "python-virtualenv"
        "firefox"               # Selenium browser (official repo, reliable)
        "geckodriver"           # Firefox WebDriver (official repo)
    )

    info "Syncing package databases..."
    $SUDO pacman -Sy --noconfirm &>/dev/null

    local to_install=()
    for pkg in "${PACMAN_PACKAGES[@]}"; do
        if pacman -Q "$pkg" &>/dev/null; then
            success "Already installed: $pkg"
        else
            to_install+=("$pkg")
        fi
    done

    if [[ ${#to_install[@]} -gt 0 ]]; then
        info "Installing: ${to_install[*]}"
        $SUDO pacman -S --noconfirm --needed "${to_install[@]}"
        for pkg in "${to_install[@]}"; do
            success "Installed: $pkg"
        done
    fi

    # Optional: chromedriver from AUR (if user wants Chrome instead of Firefox)
    if [[ -n "$AUR_HELPER" ]]; then
        ask "Install chromedriver from AUR for Chromium support? (geckodriver/Firefox is already installed) [y/N]"
        read -r -t 10 INSTALL_CHROMEDRIVER || INSTALL_CHROMEDRIVER="n"
        if [[ "${INSTALL_CHROMEDRIVER,,}" == "y" ]]; then
            if pacman -Q chromedriver &>/dev/null || "$AUR_HELPER" -Q chromedriver &>/dev/null 2>&1; then
                success "chromedriver already installed"
            else
                info "Installing chromedriver from AUR via $AUR_HELPER..."
                "$AUR_HELPER" -S --noconfirm chromedriver
                success "chromedriver installed"
            fi
        else
            info "Skipping chromedriver — Firefox/geckodriver will be used for OSINT verification."
        fi
    fi
}

# ── Python virtual environment ────────────────────────────────────────────────
setup_venv() {
    step "Python Virtual Environment"

    if [[ -d "$VENV_DIR" ]]; then
        warn ".venv already exists at $VENV_DIR"
        ask "Recreate virtual environment? (keeps packages if you say N) [y/N]"
        read -r -t 10 RECREATE_VENV || RECREATE_VENV="n"
        if [[ "${RECREATE_VENV,,}" == "y" ]]; then
            rm -rf "$VENV_DIR"
            info "Removed existing .venv"
        else
            info "Keeping existing .venv"
            return
        fi
    fi

    info "Creating virtual environment with system-site-packages (uses system PyQt6)..."
    "$PYTHON_BIN" -m venv --system-site-packages "$VENV_DIR"
    success "Virtual environment created: $VENV_DIR"
}

# ── Python packages ───────────────────────────────────────────────────────────
install_python_packages() {
    step "Python Packages (pip)"

    local PIP="$VENV_DIR/bin/pip"

    info "Upgrading pip..."
    "$PIP" install --quiet --upgrade pip

    info "Installing requirements (excluding PyQt6 — using system package)..."
    # Install everything except PyQt6 which comes from the system via site-packages
    "$PIP" install --quiet \
        "google-genai" \
        "python-dotenv" \
        "beautifulsoup4" \
        "googlesearch-python" \
        "selenium" \
        "lxml"

    success "Core packages installed"

    # social-analyzer — large package, separate step with progress
    info "Installing social-analyzer (this may take a moment)..."
    "$PIP" install --quiet social-analyzer && success "social-analyzer installed" \
        || warn "social-analyzer installation failed — OSINT username scanning will be limited."
}

# ── Environment file ──────────────────────────────────────────────────────────
setup_env() {
    step "Environment Configuration"

    local ENV_EXAMPLE="$SCRIPT_DIR/.env.example"
    local ENV_FILE="$SCRIPT_DIR/.env"

    # Always (re)create .env.example
    cat > "$ENV_EXAMPLE" << 'EOF'
# ─────────────────────────────────────────────────────────────
#  SentinAI — Environment Configuration
#  Copy this file to .env and fill in your values.
# ─────────────────────────────────────────────────────────────

# Required: Gemini API key from https://aistudio.google.com/apikey
GOOGLE_API_KEY=your_gemini_api_key_here

# Optional: AI model selection (default: gemini-2.0-flash)
# Options: gemini-2.0-flash | gemini-2.0-flash-exp | gemini-1.5-pro | gemini-1.5-flash
GEMINI_MODEL=gemini-2.0-flash
EOF
    success "Created .env.example"

    if [[ -f "$ENV_FILE" ]]; then
        success ".env already exists — leaving untouched"
    else
        cp "$ENV_EXAMPLE" "$ENV_FILE"
        warn ".env created from template — add your GOOGLE_API_KEY before running SentinAI"
    fi
}

# ── Launcher script ───────────────────────────────────────────────────────────
create_launcher() {
    step "Launcher Script"

    local LAUNCHER="$SCRIPT_DIR/run.sh"
    cat > "$LAUNCHER" << LAUNCHER_EOF
#!/usr/bin/env bash
# SentinAI launcher — activates the venv and starts the app
set -euo pipefail
cd "\$(dirname "\$(readlink -f "\$0")")"
source .venv/bin/activate
exec python app.py "\$@"
LAUNCHER_EOF

    chmod +x "$LAUNCHER"
    success "Created launcher: $LAUNCHER"
}

# ── Desktop entry ─────────────────────────────────────────────────────────────
create_desktop_entry() {
    step "Desktop Entry"

    ask "Create a .desktop launcher (adds SentinAI to your app menu)? [Y/n]"
    read -r -t 10 CREATE_DESKTOP || CREATE_DESKTOP="y"
    if [[ "${CREATE_DESKTOP,,}" == "n" ]]; then
        info "Skipping desktop entry."
        return
    fi

    mkdir -p "$DESKTOP_DIR"
    local ICON_PATH="$SCRIPT_DIR/icons/icon.png"
    local EXEC_PATH="$SCRIPT_DIR/run.sh"

    cat > "$DESKTOP_DIR/sentinai.desktop" << DESKTOP_EOF
[Desktop Entry]
Name=SentinAI
GenericName=Cybersecurity Assistant
Comment=AI-powered OSINT investigation and password analysis tool
Exec=${EXEC_PATH}
Icon=${ICON_PATH}
Terminal=false
Type=Application
Categories=Network;Security;Utility;
Keywords=osint;security;password;pentest;ai;
StartupWMClass=SentinAI
DESKTOP_EOF

    chmod +x "$DESKTOP_DIR/sentinai.desktop"
    # Make the desktop file trusted if xdg-open is available
    if command -v gio &>/dev/null; then
        gio set "$DESKTOP_DIR/sentinai.desktop" metadata::trusted true 2>/dev/null || true
    fi

    success "Desktop entry created: $DESKTOP_DIR/sentinai.desktop"
}

# ── Output directories ────────────────────────────────────────────────────────
create_output_dirs() {
    step "Output Directories"
    mkdir -p "$SCRIPT_DIR/osints"
    mkdir -p "$SCRIPT_DIR/wordlists"
    success "Created: osints/, wordlists/"
}

# ── Verify installation ───────────────────────────────────────────────────────
verify_installation() {
    step "Verification"

    local PYTHON_VENV="$VENV_DIR/bin/python"
    local FAILED=0

    local checks=(
        "google.genai"
        "dotenv"
        "bs4"
        "googlesearch"
        "selenium"
        "PyQt6.QtWidgets"
    )

    for mod in "${checks[@]}"; do
        if "$PYTHON_VENV" -c "import $mod" 2>/dev/null; then
            success "import $mod"
        else
            warn "import $mod — FAILED (some features may be unavailable)"
            (( FAILED++ )) || true
        fi
    done

    if command -v geckodriver &>/dev/null; then
        DRIVER_VERSION=$(geckodriver --version 2>&1 | head -1)
        success "geckodriver: $DRIVER_VERSION"
    elif command -v chromedriver &>/dev/null; then
        DRIVER_VERSION=$(chromedriver --version 2>&1 | head -1)
        success "chromedriver: $DRIVER_VERSION"
    else
        warn "No WebDriver found — Selenium OSINT verification will be skipped."
        warn "Install geckodriver: sudo pacman -S geckodriver"
        (( FAILED++ )) || true
    fi

    if "$PYTHON_VENV" -c "import social_analyzer" 2>/dev/null; then
        success "social-analyzer"
    elif command -v social-analyzer &>/dev/null; then
        success "social-analyzer (CLI)"
    else
        warn "social-analyzer not found — username OSINT scanning will be limited."
    fi

    return $FAILED
}

# ── Summary ───────────────────────────────────────────────────────────────────
print_summary() {
    local FAILED=${1:-0}
    echo
    echo -e "${BOLD}${CYAN}  ─────────────────────────────────────────────────${NC}"
    if [[ $FAILED -eq 0 ]]; then
        echo -e "  ${BOLD}${GREEN}Installation complete!${NC}"
    else
        echo -e "  ${BOLD}${YELLOW}Installation complete with warnings.${NC}"
    fi
    echo -e "${BOLD}${CYAN}  ─────────────────────────────────────────────────${NC}"
    echo
    echo -e "  ${BOLD}Next steps:${NC}"
    echo
    echo -e "  1. Add your Gemini API key to ${BOLD}.env${NC}:"
    echo -e "     ${DIM}nano $SCRIPT_DIR/.env${NC}"
    echo
    echo -e "  2. Get a free API key at:"
    echo -e "     ${DIM}https://aistudio.google.com/apikey${NC}"
    echo
    echo -e "  3. Launch SentinAI:"
    echo -e "     ${BOLD}./run.sh${NC}   ${DIM}(or use your app menu)${NC}"
    echo
    if [[ $FAILED -gt 0 ]]; then
        echo -e "  ${YELLOW}Some optional components had issues. Check warnings above.${NC}"
        echo
    fi
}

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
    print_banner
    preflight_checks
    detect_aur_helper
    install_system_packages
    setup_venv
    install_python_packages
    setup_env
    create_launcher
    create_desktop_entry
    create_output_dirs

    local FAILED=0
    verify_installation || FAILED=$?

    print_summary $FAILED
}

main "$@"
