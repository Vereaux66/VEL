"""
DEPRECATED: This file has been superseded by anvel_monitoring.py

The comprehensive monitoring module (anvel_monitoring.py) now includes
ANVELHealthMonitor along with other monitoring components. Please use
anvel_monitoring.py for all health monitoring needs.

This file is kept for backward compatibility reference only.
"""
import warnings

warnings.warn(
    "anvel_health_monitor.py is deprecated. Use anvel_monitoring.ANVELHealthMonitor instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export from canonical module for backward compatibility
from anvel_monitoring import ANVELHealthMonitor, AnvelMonitoring

# Alias for backward compatibility
AnvelHealthMonitor = ANVELHealthMonitor

__all__ = ["ANVELHealthMonitor", "AnvelHealthMonitor", "AnvelMonitoring"]
