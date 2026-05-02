"""MergeEngine — merges Global Foundation + Scholarly Persona into the Active Registry.

The merge is a shallow dictionary merge where Scholarly Persona values
override Global Foundation values for shared keys.  After merging, business
rules are applied (e.g. auto-disabling cross-chunk memory when the LLM
backend is set to ``local``).

Both public methods are stateless and return new dictionaries — they never
mutate their inputs.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class MergeEngine:
    """Merges Global Foundation + Scholarly Persona into Active Registry."""

    @staticmethod
    def merge(global_dict: dict, persona_dict: dict) -> dict:
        """Shallow merge: persona values override global values for shared keys.

        Returns a **new** dict — neither *global_dict* nor *persona_dict* is
        mutated.
        """
        return {**global_dict, **persona_dict}

    @staticmethod
    def apply_rules(registry: dict) -> dict:
        """Apply business rules post-merge.

        Current rules:
        - If ``llm_backend == 'local'``, force ``cross_chunk_memory = False``
          and log when auto-disabling.

        Returns the (potentially modified) *registry* dict.  The dict is
        modified **in place** for efficiency, but also returned for
        convenience.
        """
        if registry.get("llm_backend") == "local":
            if registry.get("cross_chunk_memory") is not False:
                logger.info(
                    "MergeEngine: auto-disabling cross_chunk_memory "
                    "(llm_backend='local', original value=%r)",
                    registry.get("cross_chunk_memory"),
                )
            registry["cross_chunk_memory"] = False

        return registry
