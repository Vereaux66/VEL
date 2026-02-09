# VEL-ARC - VEL Archive

This directory contains modules that are **not actively wired** into the main VEL trading system.
These files are preserved for reference, future integration, or legacy purposes.

## Directory Structure

```
VEL-ARC/
├── ready_to_integrate/    # Modules that IMPORT from main system
│                          # Could be wired up with minimal effort
├── legacy/                # Standalone legacy modules
│   ├── anvel/            # ANVEL legacy modules
│   └── vel/              # VEL legacy modules
└── docs/                  # Documentation about archived modules
```

## Categories Explained

### ready_to_integrate/ (13 files)
These modules already import from the main system. They are **functionally compatible** 
and could be integrated with proper wiring. Each file has been analyzed for:
- What main system modules it depends on
- What functionality it provides
- Integration effort estimate

### legacy/anvel/ and legacy/vel/ (92 files)
Standalone modules that have **no imports from the active main system**.
They are either:
- Experimental features never fully integrated
- Alternative implementations
- Development utilities
- Future feature placeholders

## Important Notes

1. **DO NOT DELETE** - These files may contain useful code or algorithms
2. **IMPORT PATHS** - If re-integrating, update import paths from `from anvel_xxx` to `from VEL_ARC.xxx`
3. **TESTING** - Archived modules may have outdated dependencies

## Main System Location

The active trading system files remain in the repository root.
See `/MODULE_ARCHITECTURE.md` for the main system documentation.

---
*Generated: 2026-02-09*
