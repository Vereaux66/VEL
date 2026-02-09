# ═══════════════════════════════════════════════════════════════════════════════
#                    VEL-ARC BOUNDARY DEFINITION
# ═══════════════════════════════════════════════════════════════════════════════
#
#  ██╗   ██╗███████╗██╗          █████╗ ██████╗  ██████╗
#  ██║   ██║██╔════╝██║         ██╔══██╗██╔══██╗██╔════╝
#  ██║   ██║█████╗  ██║         ███████║██████╔╝██║     
#  ╚██╗ ██╔╝██╔══╝  ██║         ██╔══██║██╔══██╗██║     
#   ╚████╔╝ ███████╗███████╗    ██║  ██║██║  ██║╚██████╗
#    ╚═══╝  ╚══════╝╚══════╝    ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝
#
#  ARCHIVE - NOT FOR PRODUCTION USE
#
# ═══════════════════════════════════════════════════════════════════════════════

## 🚨 CRITICAL: BOUNDARY RULES

### Rule 1: NO IMPORTS FROM VEL-ARC IN MAIN SYSTEM
The main system (root directory) MUST NEVER import from VEL-ARC.

```python
# ❌ FORBIDDEN - Never do this in main system:
from VEL_ARC.legacy.anvel import anvel_brain
from VEL_ARC.DO_NOT_USE_outcast import anvel_api_gateway
import VEL_ARC.legacy.vel.vel_cli

# ✅ CORRECT - Main system only imports from root:
from anvel_event_bus import ANVELEventBus
from vel_execution_core import VELExecutionCore
```

### Rule 2: VEL-ARC MAY IMPORT FROM MAIN (Read-Only Reference)
Archived modules may have imports from the main system for reference purposes.
This does NOT mean they are integrated - they are archived and inactive.

### Rule 3: VEL-ARC IS ISOLATED
- No CI/CD pipelines run on VEL-ARC code
- No tests depend on VEL-ARC modules
- No Docker builds include VEL-ARC

---

## 📂 DIRECTORY STRUCTURE

```
/home/runner/work/VEL/VEL/
│
├── [MAIN SYSTEM - PRODUCTION CODE]
│   ├── vel_main.py              ← Single entry point (39 modules)
│   ├── anvel_*.py (25 files)    ← Active ANVEL modules
│   ├── vel_*.py (14 files)      ← Active VEL modules
│   └── (other core files)
│
└── VEL-ARC/                      ← [ARCHIVE - NOT PRODUCTION]
    │
    ├── BOUNDARY.md              ← This file (boundary rules)
    ├── README.md                ← Archive overview
    ├── __init__.py              ← Empty (prevents accidental imports)
    │
    ├── DO_NOT_USE_outcast/      ← 12 files - Orphaned, no references
    │   └── (modules removed from main)
    │
    ├── legacy/                  ← 92 files - Historical code
    │   ├── anvel/              ← 65 legacy ANVEL modules
    │   └── vel/                ← 27 legacy VEL modules
    │
    └── ready_to_integrate/      ← Empty (modules moved to main or outcast)
```

---

## 📊 MODULE COUNTS

| Location | Count | Status |
|----------|-------|--------|
| **Main System (root)** | 39 | ✅ ACTIVE |
| VEL-ARC/DO_NOT_USE_outcast | 12 | ❌ ORPHANED |
| VEL-ARC/legacy/anvel | 65 | 📦 ARCHIVED |
| VEL-ARC/legacy/vel | 27 | 📦 ARCHIVED |
| **Total Archived** | 104 | ⏸️ INACTIVE |

---

## 🔒 ENFORCEMENT

### 1. CI/CD Check (Recommended)
Add this check to your CI pipeline:

```yaml
- name: Verify no VEL-ARC imports in main
  run: |
    if grep -r "from VEL_ARC\|import VEL_ARC" --include="*.py" . \
       --exclude-dir=VEL-ARC 2>/dev/null; then
      echo "ERROR: Main system imports from VEL-ARC!"
      exit 1
    fi
```

### 2. Pre-commit Hook (Recommended)
```bash
#!/bin/bash
# .git/hooks/pre-commit
if git diff --cached --name-only | xargs grep -l "from VEL_ARC\|import VEL_ARC" 2>/dev/null | \
   grep -v "^VEL-ARC/"; then
  echo "ERROR: Attempting to import from VEL-ARC in main system"
  exit 1
fi
```

### 3. __init__.py Guard
The VEL-ARC/__init__.py raises an error if imported:

```python
raise ImportError(
    "VEL-ARC is an archive. Do not import from it. "
    "Use modules from the main system (root directory)."
)
```

---

## 🔄 MIGRATION PROCESS

To move a module FROM VEL-ARC TO main system:

1. **Analyze dependencies**: Check what it imports
2. **Copy to root**: `cp VEL-ARC/legacy/anvel/module.py ./`
3. **Update vel_main.py**: Add to CORE_MODULES list
4. **Test imports**: Verify it loads
5. **Remove from VEL-ARC**: `rm VEL-ARC/legacy/anvel/module.py`
6. **Update this document**: Adjust counts

To move a module FROM main TO VEL-ARC:

1. **Verify no imports**: Ensure nothing imports it
2. **Move to outcast**: `mv module.py VEL-ARC/DO_NOT_USE_outcast/`
3. **Remove from vel_main.py**: Delete from CORE_MODULES
4. **Update this document**: Adjust counts

---

## 📋 INVENTORY

### Main System (39 modules) - ACTIVE
See `vel_main.py` CORE_MODULES for the complete list.

### VEL-ARC/DO_NOT_USE_outcast (12 modules) - ORPHANED
- anvel_advanced_trading_strategies.py
- anvel_api_gateway.py
- anvel_contract_integration.py
- anvel_health_monitor.py
- anvel_learning_bridge.py
- anvel_pooled_trading_api.py
- anvel_saas_trading_coordinator.py
- anvel_strategy_runner.py
- anvel_trade_engine.py
- vel_connection_hardening.py
- vel_execution_example.py
- vel_security_core.py

### VEL-ARC/legacy/ (92 modules) - ARCHIVED
See VEL-ARC/legacy/anvel/ and VEL-ARC/legacy/vel/ directories.

---

*Last Updated: 2026-02-09*
*Boundary Version: 1.0*
