"""Packaged copies of the bundled profile configurations.

The repository keeps the canonical files under ``config/``; the packaged copies
let an installed wheel resolve the demo/private profiles without a source
checkout. The release checks verify that both copies stay identical.
"""

from __future__ import annotations

__all__: list[str] = []
