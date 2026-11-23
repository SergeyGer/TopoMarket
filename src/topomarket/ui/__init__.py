"""Dashboard UI layer for TopoMarket.

The pure selection/payload/performance modules can be imported without
Streamlit; the Streamlit shell lives in ``app.py`` at the repository root.
"""

from __future__ import annotations

from .dashboard import DashboardSelection, DashboardSelectionError
from .panels import (
    DashboardData,
    DashboardDataError,
    PanelCache,
    build_screen_payloads,
    load_dashboard_data,
)
from .performance import measure_cached_date_changes, measure_dashboard_startup

__all__ = [
    "DashboardData",
    "DashboardDataError",
    "DashboardSelection",
    "DashboardSelectionError",
    "PanelCache",
    "build_screen_payloads",
    "load_dashboard_data",
    "measure_cached_date_changes",
    "measure_dashboard_startup",
]
