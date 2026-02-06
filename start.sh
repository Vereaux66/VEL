#!/bin/bash
# =============================================================================
# VEL Trading System - Hardened Unified Start Script
# =============================================================================
# Security-enhanced launcher with pre-flight validation
# Supports: Linux, macOS
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
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

log_security() {
    echo -e "${CYAN}[SECURITY]${NC} $1"
}

# =============================================================================
# SECURITY VALIDATION
# =============================================================================

validate_environment_security() {
    log_security "Running security validation..."
    local security_passed=true
    
    # Check for dangerous environment variables
    if [ -n "${LD_PRELOAD:-}" ]; then
        log_warning "LD_PRELOAD is set - potential security risk"
    fi
    
    # Validate script hasn't been tampered with
    if [ ! -f "$SCRIPT_DIR/run.py" ]; then
        log_error "Critical file run.py missing - possible tampering"
        security_passed=false
    fi
    
    # Check file permissions - should not be writable by group or others
    local dir_perms
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        dir_perms=$(stat -c %a "$SCRIPT_DIR" 2>/dev/null)
    else
        dir_perms=$(stat -f %OLp "$SCRIPT_DIR" 2>/dev/null)
    fi
    
    # Check if group or others have write permission
    local group_write=$((dir_perms / 10 % 10 & 2))
    local other_write=$((dir_perms % 10 & 2))
    
    if [ "$group_write" -ne 0 ] || [ "$other_write" -ne 0 ]; then
        log_warning "Script directory has insecure permissions ($dir_perms) - should not be writable by group/others"
    fi
    
    if [ "$security_passed" = false ]; then
        log_error "Security validation failed"
        exit 1
    fi
    
    log_success "Security validation passed"
}

# Check if setup was run
check_setup() {
    if [ ! -d "venv" ] && [ ! -d "node_modules" ]; then
        log_error "System not set up. Please run ./setup.sh first"
        exit 1
    fi
    log_success "Setup verified"
}

# MANDATORY: Check web password
check_password() {
    if [ -z "${ANVEL_WEB_PASSWORD:-}" ]; then
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
    local password_length=${#ANVEL_WEB_PASSWORD}
    if [ "$password_length" -lt 12 ]; then
        log_error "ANVEL_WEB_PASSWORD must be at least 12 characters"
        exit 1
    fi
    
    # Check password complexity - enforce strict requirements
    local has_number=false
    local has_upper=false
    local has_special=false
    local complexity_errors=0
    
    if echo "$ANVEL_WEB_PASSWORD" | grep -q '[0-9]'; then
        has_number=true
    else
        log_error "Password must contain at least one number"
        complexity_errors=$((complexity_errors + 1))
    fi
    
    if echo "$ANVEL_WEB_PASSWORD" | grep -q '[A-Z]'; then
        has_upper=true
    else
        log_error "Password must contain at least one uppercase letter"
        complexity_errors=$((complexity_errors + 1))
    fi
    
    if echo "$ANVEL_WEB_PASSWORD" | grep -qE '[!@#$%^&*()_+{}|:<>?-]'; then
        has_special=true
    else
        log_error "Password must contain at least one special character"
        complexity_errors=$((complexity_errors + 1))
    fi
    
    if [ "$complexity_errors" -gt 0 ]; then
        log_error "Password does not meet security requirements"
        exit 1
    fi
    
    log_success "Web password configured"
}

# Load environment safely
load_env() {
    if [ -f ".env" ]; then
        log_info "Loading environment from .env"
        # Safe environment loading: only export valid KEY=VALUE pairs
        while IFS='=' read -r key value || [ -n "$key" ]; do
            # Skip comments and empty lines
            case "$key" in
                '#'*) continue ;;
                '') continue ;;
            esac
            
            # Validate key format (alphanumeric + underscore, starts with letter)
            if echo "$key" | grep -qE '^[A-Za-z_][A-Za-z0-9_]*$'; then
                # Remove leading/trailing quotes from value
                value=$(echo "$value" | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")
                export "$key=$value"
            else
                log_warning "Skipping invalid env key: $key"
            fi
        done < .env
    fi
}

# Activate Python environment
activate_python() {
    if [ -d "venv" ]; then
        # shellcheck source=/dev/null
        source venv/bin/activate
        log_success "Python environment activated"
    fi
}

# Check Python security modules
check_python_security() {
    log_info "Verifying Python security modules..."
    
    if python3 -c "import anvel_military_security" 2>/dev/null; then
        log_success "Military-grade security module available"
    else
        log_warning "Military security module not loaded (will use fallback)"
    fi
}

# Start the system
start_system() {
    log_info "Starting VEL Trading System via unified launcher..."
    
    # Set secure umask
    umask 077
    
    # Use the single launch authority
    python3 run.py
}

# Graceful shutdown handler
cleanup() {
    log_info "Received shutdown signal, cleaning up..."
    # Kill any child processes
    jobs -p | xargs -r kill 2>/dev/null || true
    exit 0
}

# Register signal handlers
trap cleanup SIGINT SIGTERM

# =============================================================================
# MAIN EXECUTION
# =============================================================================

main() {
    echo ""
    echo -e "${CYAN}${BOLD}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}${BOLD}       VEL Trading System - Hardened Launch Sequence           ${NC}"
    echo -e "${CYAN}${BOLD}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
    
    validate_environment_security
    check_setup
    load_env
    check_password
    activate_python
    check_python_security
    
    echo ""
    log_success "All pre-flight checks passed"
    echo ""
    
    start_system
}

main "$@"
