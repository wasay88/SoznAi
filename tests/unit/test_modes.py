from __future__ import annotations

import pytest

from backend.app.services.modes import ModeManager, ModeState


@pytest.mark.anyio
async def test_mode_manager_transitions() -> None:
    manager = ModeManager()

    status = await manager.get_status()
    assert status.state == ModeState.OFFLINE

    await manager.set_online("ready")
    assert manager.snapshot().state == ModeState.ONLINE

    await manager.set_degraded("issues")
    assert manager.snapshot().state == ModeState.DEGRADED

    await manager.set_offline("manual")
    assert manager.snapshot().state == ModeState.OFFLINE
