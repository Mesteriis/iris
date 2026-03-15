from __future__ import annotations

from importlib import import_module

_PROMPT_REGISTRY_LOADED = False


def ensure_ai_prompt_policy_loaded() -> None:
    global _PROMPT_REGISTRY_LOADED
    if _PROMPT_REGISTRY_LOADED:
        return
    import_module("src.apps.hypothesis_engine.prompts.defaults")
    import_module("src.apps.notifications.prompts")
    import_module("src.apps.briefs.prompts")
    import_module("src.apps.explanations.prompts")
    _PROMPT_REGISTRY_LOADED = True


__all__ = ["ensure_ai_prompt_policy_loaded"]
