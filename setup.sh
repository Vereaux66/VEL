#!/bin/bash
# VEL Trading System - Unified Setup Script
# Supports: Linux, macOS
# This script automates complete system setup including native builds

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Detect OS
detect_os() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        OS="linux"
        log_info "Detected Linux"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        OS="macos"
        log_info "Detected macOS"
    else
        log_error "Unsupported OS: $OSTYPE"
        exit 1
    fi
}

# Check system dependencies
check_dependencies() {
    log_info "Checking system dependencies..."
    
    local missing_deps=()
    
    # Check Python
    if ! command -v python3 &> /dev/null; then
        missing_deps+=("python3")
    else
        log_success "Python 3: $(python3 --version)"
    fi
    
    # Check Node.js
    if ! command -v node &> /dev/null; then
        missing_deps+=("nodejs")
    else
        log_success "Node.js: $(node --version)"
    fi
    
    # Check Rust
    if ! command -v cargo &> /dev/null; then
        log_warning "Rust not found - will attempt to install"
        install_rust
    else
        log_success "Rust: $(rustc --version)"
    fi
    
    # Check CMake (for C++ builds)
    if ! command -v cmake &> /dev/null; then
        log_warning "CMake not found - C++ components will be skipped"
    else
        log_success "CMake: $(cmake --version | head -1)"
    fi
    
    # Check Go (for Go components)
    if ! command -v go &> /dev/null; then
        log_warning "Go not found - Go components will be skipped"
    else
        log_success "Go: $(go version)"
    fi
    
    if [ ${#missing_deps[@]} -ne 0 ]; then
        log_error "Missing required dependencies: ${missing_deps[*]}"
        log_info "Please install them and re-run this script"
        exit 1
    fi
}

# Install Rust if missing
install_rust() {
    log_info "Installing Rust..."
    log_warning "This will download and run the official Rust installer"
    log_warning "See https://rustup.rs/ for more information"
    read -p "Continue? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
        source "$HOME/.cargo/env"
        log_success "Rust installed successfully"
    else
        log_error "Rust installation cancelled. Please install manually and re-run."
        exit 1
    fi
}

# Setup Python environment
setup_python() {
    log_info "Setting up Python environment..."
    
    # Create virtual environment if it doesn't exist
    if [ ! -d "venv" ]; then
        python3 -m venv venv
        log_success "Created Python virtual environment"
    fi
    
    # Activate virtual environment
    source venv/bin/activate
    
    # Upgrade pip
    pip install --upgrade pip setuptools wheel
    
    # Install Python dependencies
    log_info "Installing Python dependencies..."
    pip install -r requirements.txt
    log_success "Python dependencies installed"
}

# Setup Node.js environment
setup_nodejs() {
    log_info "Setting up Node.js environment..."
    
    # Install Node.js dependencies
    if [ -f "package.json" ]; then
        npm install
        log_success "Node.js dependencies installed"
    fi
    
    # Install native module dependencies
    if [ -d "native/js_app" ]; then
        pushd native/js_app > /dev/null
        npm install
        popd > /dev/null
        log_success "Native JS app dependencies installed"
    fi
    
    if [ -d "native/gateway_js" ]; then
        pushd native/gateway_js > /dev/null
        npm install
        popd > /dev/null
        log_success "Gateway JS dependencies installed"
    fi
    
    if [ -d "native/strategy_js" ]; then
        pushd native/strategy_js > /dev/null
        npm install
        popd > /dev/null
        log_success "Strategy JS dependencies installed"
    fi
}

# Build Rust components
build_rust() {
    log_info "Building Rust components..."
    
    # Build main VEL trading engine
    if [ -d "vel-trading" ]; then
        log_info "Building VEL trading engine..."
        pushd vel-trading > /dev/null
        cargo build --release
        popd > /dev/null
        
        # Copy artifacts to root for easy access
        mkdir -p build/release
        if [ -f "vel-trading/target/release/vel-trading" ]; then
            cp vel-trading/target/release/vel-trading build/release/
            log_success "VEL trading engine built successfully"
        fi
    fi
    
    # Build native Rust analytics
    if [ -d "native/rust_analytics" ]; then
        log_info "Building Rust analytics..."
        pushd native/rust_analytics > /dev/null
        cargo build --release
        popd > /dev/null
        log_success "Rust analytics built"
    fi
    
    # Build native Rust execution core
    if [ -d "native/rust_exec_core" ]; then
        log_info "Building Rust execution core..."
        pushd native/rust_exec_core > /dev/null
        cargo build --release
        popd > /dev/null
        log_success "Rust execution core built"
    fi
    
    # Build native ANVEL core
    if [ -d "native/anvel_core" ]; then
        log_info "Building ANVEL core..."
        pushd native/anvel_core > /dev/null
        cargo build --release
        popd > /dev/null
        log_success "ANVEL core built"
    fi
}

# Build C++ components
build_cpp() {
    if ! command -v cmake &> /dev/null; then
        log_warning "Skipping C++ builds (CMake not found)"
        return
    fi
    
    log_info "Building C++ components..."
    
    if [ -d "native/cpp_gateway" ]; then
        log_info "Building C++ gateway..."
        pushd native/cpp_gateway > /dev/null
        mkdir -p build
        pushd build > /dev/null
        cmake ..
        make -j$(nproc 2>/dev/null || echo 4)
        popd > /dev/null
        popd > /dev/null
        log_success "C++ gateway built"
    fi
}

# Build Go components
build_go() {
    if ! command -v go &> /dev/null; then
        log_warning "Skipping Go builds (Go not found)"
        return
    fi
    
    log_info "Building Go components..."
    
    if [ -d "native/go_risk_core" ]; then
        log_info "Building Go risk core..."
        pushd native/go_risk_core > /dev/null
        make build
        popd > /dev/null
        log_success "Go risk core built"
    fi
}

# Build standalone signal generator
build_signal_generator() {
    if [ -f "anvel_signal_generator.cpp" ]; then
        log_info "Building signal generator..."
        if command -v g++ &> /dev/null; then
            g++ -O3 -std=c++17 -o build/release/anvel_signal_generator anvel_signal_generator.cpp -lpthread
            log_success "Signal generator built"
        else
            log_warning "g++ not found - skipping signal generator"
        fi
    fi
}

# Setup configuration
setup_config() {
    log_info "Setting up configuration..."
    
    # Create necessary directories
    mkdir -p logs data backups models configs build/release
    
    # Copy example config if config doesn't exist
    if [ ! -f ".env" ] && [ -f ".env.example" ]; then
        cp .env.example .env
        log_success "Created .env from template"
        log_warning "Please edit .env with your configuration"
    fi
    
    # Create default config if it doesn't exist
    if [ ! -f "configs/anvel_config.json" ] && [ -f "anvel_config.json" ]; then
        cp anvel_config.json configs/
        log_success "Created default configuration"
    fi
}

# Create build manifest
create_build_manifest() {
    log_info "Creating build manifest..."
    
    cat > build/BUILD_MANIFEST.txt << EOF
VEL Trading System - Build Manifest
====================================
Build Date: $(date)
OS: $OS
Host: $(hostname)

Build Artifacts:
EOF
    
    find build/release -type f -executable 2>/dev/null | while read -r file; do
        echo "  - $(basename "$file")" >> build/BUILD_MANIFEST.txt
    done
    
    log_success "Build manifest created at build/BUILD_MANIFEST.txt"
}

# Main setup flow
main() {
    echo "========================================"
    echo "VEL Trading System - Unified Setup"
    echo "========================================"
    echo ""
    
    detect_os
    check_dependencies
    
    log_info "Starting full system setup..."
    echo ""
    
    setup_python
    setup_nodejs
    build_rust
    build_cpp
    build_go
    build_signal_generator
    setup_config
    create_build_manifest
    
    echo ""
    echo "========================================"
    echo "Setup Complete!"
    echo "========================================"
    echo ""
    log_success "VEL Trading System is ready to use"
    echo ""
    echo "Next steps:"
    echo "  1. Review and edit .env with your configuration"
    echo "  2. Set ANVEL_WEB_PASSWORD environment variable"
    echo "  3. Run './start.sh' to launch the system"
    echo ""
    echo "Documentation: See README.md for full details"
    echo ""
}

main "$@"
