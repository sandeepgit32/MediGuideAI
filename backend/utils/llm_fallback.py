"""Fallback parser for Groq/llama tool-call failures.

Some smaller models (e.g. ``llama-3.1-8b-instant``) emit function calls in a
non-standard XML-like format::

    <function=final_result>{"key": value}</function>

instead of the proper JSON tool-call format that pydantic-ai expects.  Groq's
API rejects these with a 400 ``tool_use_failed`` error but still surfaces the
raw model output in the ``failed_generation`` field of the error body.

:func:`extract_failed_generation_json` parses that field so callers can
recover a valid ``dict`` without re-calling the LLM.
"""

import json
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Matches: <function=some_name>{...}</function>  OR  <function=some_name>{...}  (no closing tag)
_FUNC_TAG_RE = re.compile(
    r"<function=\w+>\s*(\{.*?)\s*(?:</function>|$)",
    re.DOTALL,
)


def extract_failed_generation_json(error: Exception) -> Optional[dict]:
    """Try to extract a JSON dict from a pydantic-ai ``ModelHTTPError``.

    When ``llama-3.1-8b-instant`` (and similar models) on Groq returns output
    in the ``<function=final_result>{...}</function>`` format, the OpenAI
    client raises a ``ModelHTTPError`` with ``code='tool_use_failed'`` and the
    raw model output in ``body['failed_generation']``.  This function parses
    that output and returns the embedded JSON as a plain ``dict``.

    Args:
        error: The exception raised by ``Agent.run()``.

    Returns:
        A ``dict`` parsed from the model's intended output, or ``None`` when
        the error is not a recoverable ``tool_use_failed`` case.
    """
    try:
        # Import here to avoid a hard dependency at module load time.
        from pydantic_ai.exceptions import ModelHTTPError  # noqa: PLC0415

        if not isinstance(error, ModelHTTPError):
            return None

        body = getattr(error, "body", None)
        if not isinstance(body, dict):
            return None

        if body.get("code") != "tool_use_failed":
            return None

        failed_gen: str = body.get("failed_generation", "")
        if not failed_gen:
            return None

        match = _FUNC_TAG_RE.search(failed_gen)
        if not match:
            logger.debug(
                "tool_use_failed: no <function=…> tag found in failed_generation"
            )
            return None

        raw = match.group(1)

        # The model sometimes emits Python-style literals inside what looks
        # like JSON (True/False/None).  Normalise them before parsing.
        raw = re.sub(r"\bTrue\b", "true", raw)
        raw = re.sub(r"\bFalse\b", "false", raw)
        raw = re.sub(r"\bNone\b", "null", raw)

        data = json.loads(raw)
        logger.info(
            "tool_use_failed fallback: recovered JSON from failed_generation (keys=%s)",
            list(data.keys()),
        )
        return data

    except Exception as exc:  # pragma: no cover
        logger.debug("tool_use_failed fallback parse error: %s", exc)
        return None
