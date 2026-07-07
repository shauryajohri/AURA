# ui/model_lock.py
"""Back-compat shim. The canonical lock state now lives in core/model_lock.py
so the backend router and the UI share one source of truth. Kept so any
existing `from ui.model_lock import ...` keeps working."""

from core.model_lock import (  # noqa: F401
    is_locked, set_locked, toggle, locked_models, unlocked_models,
)
