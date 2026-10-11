"""Central configuration loaded from .env (keys and model IDs are never hard-coded)."""
import os
from dotenv import load_dotenv

load_dotenv()

# Any OpenAI-compatible endpoint
API_BASE_URL = os.getenv("API_BASE_URL", "")

# Reasoning models: Model_1 = fast (default), Model_2 = deep
FAST_MODEL = os.getenv("MODEL_1", "")
FAST_MODEL_API_KEY = os.getenv("MODEL_1_API_KEY", "")
QUALITY_MODEL = os.getenv("MODEL_2", "")
REASONING_API_KEY = os.getenv("MODEL_2_API_KEY", "")
BACKUP_MODEL = os.getenv("BACKUP_MODEL", "")                         # optional last resort
DEFAULT_MODEL_MODE = os.getenv("DEFAULT_MODEL_MODE", "fast")

# Vision model for images / scanned pages (primary + fallback)
VISION_MODEL = os.getenv("VISION_MODEL", "")
VISION_FALLBACK_MODEL = os.getenv("VISION_FALLBACK_MODEL", "")
VISION_API_KEY = os.getenv("VISION_API_KEY", "")

FAST_MODEL_API_KEY = FAST_MODEL_API_KEY or REASONING_API_KEY


def api_key_for(model: str) -> str:
    """Each model can be served under a different key."""
    return FAST_MODEL_API_KEY if model == FAST_MODEL else REASONING_API_KEY


def fallback_chain(model: str) -> list[str]:
    """Models to try in order: requested -> fast -> backup (deduplicated)."""
    chain = []
    for m in (model, FAST_MODEL, BACKUP_MODEL):
        if m and m not in chain:
            chain.append(m)
    return chain


def label_for(model: str) -> str:
    """Public label shown in the UI / results - real model IDs are never exposed."""
    return {FAST_MODEL: "Model_1", QUALITY_MODEL: "Model_2", BACKUP_MODEL: "Backup"}.get(model, "code")


# Pipeline limits
MAX_INPUT_CHARS = 20_000        # longer inputs are truncated with a warning
MIN_INPUT_WORDS = 4             # below this we refuse to analyse
LLM_TIMEOUT_S = 420             # the deep reasoning model can queue for minutes on shared endpoints
FAST_TIMEOUT_S = 300            # fast model: cut stalled streams sooner and retry
LLM_TEMPERATURE = 0.1           # low temperature = consistency over creativity


def timeouts_for(model: str) -> tuple[int, int]:
    """(total deadline, max silence between chunks) in seconds."""
    if model == QUALITY_MODEL:
        return LLM_TIMEOUT_S, 300   # long queue before first token is normal
    return FAST_TIMEOUT_S, 90


def model_for(mode: str | None) -> str:
    return QUALITY_MODEL if (mode or DEFAULT_MODEL_MODE) == "quality" else FAST_MODEL
