"""Phase 1 ingest + analytics modules for `COT_LENS_v1`.

Reusable across the Phase 1 notebook, the Phase 2 web app's data export, and
the Phase 1 production cron (PLAN §1.3).
"""

from .universe import UNIVERSE, Contract, by_symbol, sectors

__all__ = ["UNIVERSE", "Contract", "by_symbol", "sectors"]
