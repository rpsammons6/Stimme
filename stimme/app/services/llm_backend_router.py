"""
LLM Backend Router — routes translation requests between cloud (TranslationBrain)
and local (LocalLLMProvider) backends based on SettingsManager configuration.

Pure service layer: no Flet imports, no UI widgets.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.contexts.settings import SettingsManager
    from app.services.local_llm_provider import LocalLLMProvider


class LLMBackendRouter:
    """Selects between cloud and local LLM backends for translation.

    Both providers are lazily initialized — only created when first needed.
    The backend selection is read from ``SettingsManager.get_llm_backend()``
    on every ``translate()`` call, defaulting to ``"cloud"`` when the key
    is missing or empty.
    """

    def __init__(self, settings: SettingsManager):
        self.settings = settings
        self._brain = None   # lazy TranslationBrain
        self._local = None   # lazy LocalLLMProvider

    def _get_brain(self):
        """Lazily initialize and return the cloud TranslationBrain."""
        if self._brain is None:
            # Add programs dir to path so brain module can be imported
            programs_dir = str(Path(__file__).parent.parent.parent / "programs")
            if programs_dir not in sys.path:
                sys.path.insert(0, programs_dir)
            from brain import TranslationBrain
            self._brain = TranslationBrain()
        return self._brain

    def _get_local(self):
        """Lazily initialize and return the LocalLLMProvider."""
        if self._local is None:
            from app.services.local_llm_provider import LocalLLMProvider
            self._local = LocalLLMProvider(self.settings)
        return self._local

    def translate(self, text: str, **kwargs) -> tuple:
        """Route translation to the configured backend.

        Reads ``llm_backend`` from SettingsManager on every call.
        Defaults to ``"cloud"`` when the value is missing or empty.
        All *kwargs* are forwarded unchanged to the selected provider.

        Returns
        -------
        tuple
            Whatever the underlying provider returns — typically
            ``(translation, commentary_or_None, metrics_or_None)``.
        """
        backend = self.settings.get_llm_backend() or "cloud"
        if backend == "local":
            return self._get_local().translate(text, **kwargs)
        return self._get_brain().translate(text, **kwargs)
