#!/bin/bash
# VEL Trading System - Unified Start Script
# Starts the system with proper environment and validation

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

# Check if setup was run
check_setup() {
    if [ ! -d "venv" ] && [ ! -d "node_modules" ]; then
        log_error "System not set up. Please run ./setup.sh first"
        exit 1
    fi
}

# MANDATORY: Check web password
check_password() {
    if [ -z "$ANVEL_WEB_PASSWORD" ]; then
        log_error "ANVEL_WEB_PASSWORD environment variable is not set"
        log_error "This is MANDATORY for system security"
        log_error ""
        log_error "Option 1: Set in .env file (recommended for persistent config):"
        log_error "  echo 'ANVEL_WEB_PASSWORD=your_secure_password' >> .env"
        log_error ""
        log_error "Option 2: Export for current session:"
        log_error "  export ANVEL_WEB_PASSWORD='your_secure_password'"
        log_error "  ./start.sh"
        exit 1
    fi
    
    # Validate password strength
    if [ ${#ANVEL_WEB_PASSWORD} -lt 12 ]; then
        log_error "ANVEL_WEB_PASSWORD must be at least 12 characters"
        exit 1
    fi
    
    log_success "Web password configured"
}

# Load environment
load_env() {
    if [ -f ".env" ]; then
        log_info "Loading environment from .env"
        # Safe environment loading: only export valid KEY=VALUE pairs
        set -a
        while IFS='=' read -r key value; do
            # Skip comments and empty lines
            [[ "$key" =~ ^#.*$ ]] && continue
            [[ -z "$key" ]] && continue
            # Validate key format (alphanumeric + underscore)
            if [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
                export "$key=$value"
            fi
        done < .env
        set +a
    fi
}

# Activate Python environment
activate_python() {
    if [ -d "venv" ]; then
        source venv/bin/activate
        log_success "Python environment activated"
    fi
}

# Start the system
start_system() {
    log_info "Starting VEL Trading System..."
    
    # Check which components to start
    MODE="${ANVEL_MODE:-demo}"
    
    log_info "Mode: $MODE"
    
    # Start the main Python system
    python3 anvel_bootstrap.py
}

# Main
main() {
    echo "========================================"
    echo "VEL Trading System - Starting"
    echo "========================================"
    echo ""
    
    check_setup
    load_env
    check_password
    activate_python
    
    echo ""
    start_system
}

main "$@"
