from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from hl_observer.config.loader import load_settings
from hl_observer.config.settings import Settings
from hl_observer.storage.database import init_db
from hl_observer.ui.event_bus import UiEventBus
from hl_observer.ui.persistent_state import load_or_create_ui_state
from hl_observer.ui.routes import create_router
from hl_observer.ui.dydx_routes import create_dydx_router
from hl_observer.ui.state import UiState


def create_ui_app(settings: Settings | None = None, state: UiState | None = None) -> FastAPI:
    settings = settings or load_settings()
    # The dashboard must be able to start from a fresh runtime DB. The launcher
    # also runs init-db, but keeping this here prevents a half-started UI from
    # returning 500s when the session database is new or was rotated.
    init_db(settings.database_url)
    state = state or load_or_create_ui_state(settings)
    bus = UiEventBus()
    app = FastAPI(title="HyperSmart Observer — dYdX v4 Command Center")
    static_dir = Path(__file__).with_name("static")
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    app.include_router(create_router(settings, state, bus))
    app.include_router(create_dydx_router())

    # Démarrer le moteur dYdX v4 en arrière-plan (paper-only)
    try:
        from hyper_smart_observer.dydx_v4.engine import start_engine
        start_engine()
    except Exception as _dydx_err:
        import logging
        logging.getLogger(__name__).warning(
            'dYdX engine startup failed (non-fatal): %s', _dydx_err
        )
    app.state.ui_settings = settings
    app.state.ui_state = state
    app.state.ui_bus = bus
    return app
