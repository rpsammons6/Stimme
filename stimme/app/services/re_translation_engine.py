"""Re-translation engine for paragraph-level HITL re-translation."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Callable, Optional

from app.models.hitl_models import TranslationVersion

if TYPE_CHECKING:
    from app.contexts.settings import SettingsManager
    from app.event_bus import EventBus
    from app.services.translation_service import TranslationService
    from app.state import AppState


class ReTranslationEngine:
    """Re-translates individual paragraphs using TranslationBrain."""

    def __init__(
        self,
        translation_service: "TranslationService",
        settings: "SettingsManager",
        bus: "EventBus",
        app_state: "AppState",
    ) -> None:
        self.translation_service = translation_service
        self.settings = settings
        self.bus = bus
        self.app_state = app_state

    def re_translate(
        self,
        source_text: str,
        instructions: str,
        tab_id: int,
        segment_index: int,
        log_callback: Optional[Callable] = None,
        glossary_block: str = "",
    ) -> Optional[TranslationVersion]:
        """Re-translate a single paragraph.

        Runs TranslationBrain.translate in a background thread.
        On success, stores the version in VersionStore and emits ``version_added``.
        On failure, emits an error banner via EventBus.

        Returns the new TranslationVersion, or None on error.
        """
        result: list[Optional[TranslationVersion]] = [None]

        def _run() -> None:
            try:
                self.translation_service._initialize_brain()

                model_id = self.settings.get_model()
                api_key = self.settings.get_api_key()

                translation, _commentary, _metrics = (
                    self.translation_service.brain.translate(
                        text=source_text,
                        model_id=model_id,
                        user_instructions=instructions,
                        provide_commentary=False,
                        log_callback=log_callback,
                        cache_control=False,
                        api_key=api_key,
                        glossary_block=glossary_block,
                    )
                )

                version = self.app_state.version_store.add_version(
                    tab_id=tab_id,
                    segment_index=segment_index,
                    text=translation,
                    instructions=instructions,
                )

                self.bus.emit(
                    "version_added",
                    tab_id=tab_id,
                    segment_index=segment_index,
                )

                result[0] = version

            except Exception as exc:
                self.bus.show_banner(
                    f"Re-translation failed: {exc}", is_error=True
                )

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        thread.join()

        return result[0]
