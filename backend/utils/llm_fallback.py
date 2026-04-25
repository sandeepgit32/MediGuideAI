"""Fallback utilities for Groq/llama tool-call failures.

Some smaller models (e.g. ``llama-3.1-8b-instant``) emit function calls in a
non-standard XML-like format::

    <function=final_result>{"key": value}</function>

instead of the proper JSON tool-call format that pydantic-ai expects.  Groq's
API rejects these with a 400 ``tool_use_failed`` error but still surfaces the
raw model output in the ``failed_generation`` field of the error body.

:func:`extract_failed_generation_json` parses that field (with truncation
repair) so callers can recover a valid ``dict`` without re-calling the LLM.

:func:`run_agent_with_retry` wraps ``Agent.run()`` with automatic retries on
transient ``tool_use_failed`` errors before falling back to the parser above.
"""

import asyncio
import json
import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Matches: <function=some_name>{...}</function>  OR  <function=some_name>{...}  (no closing tag)
_FUNC_TAG_RE = re.compile(
    r"<function=\w+>\s*(\{.*?)\s*(?:</function>|$)",
    re.DOTALL,
)


def _repair_truncated_json(raw: str) -> str:
    """Best-effort repair of a truncated JSON object string.

    Handles the common failure mode where the model stops mid-generation,
    leaving trailing commas and unclosed ``{`` / ``[`` delimiters.

    Args:
        raw: The partial JSON string to repair.

    Returns:
        A string with trailing commas removed and missing closing delimiters
        appended.  The result may still be invalid if the truncation occurred
        inside a string value, but covers the most frequent cases.
    """
    # Strip trailing whitespace and a dangling comma before any closer
    raw = re.sub(r",\s*$", "", raw.rstrip())

    # Count unmatched open delimiters (ignoring those inside strings is complex;
    # a simple count works for the typical "stops after a value" failure mode)
    open_braces = raw.count("{") - raw.count("}")
    open_brackets = raw.count("[") - raw.count("]")

    if open_braces > 0 or open_brackets > 0:
        raw = raw + "]" * max(open_brackets, 0) + "}" * max(open_braces, 0)

    return raw


def extract_failed_generation_json(error: Exception) -> Optional[dict]:
    """Try to extract a JSON dict from a pydantic-ai ``ModelHTTPError``.

    When ``llama-3.1-8b-instant`` (and similar models) on Groq returns output
    in the ``<function=final_result>{...}</function>`` format, the OpenAI
    client raises a ``ModelHTTPError`` with ``code='tool_use_failed'`` and the
    raw model output in ``body['failed_generation']``.  This function parses
    that output — including truncated JSON — and returns the embedded data as
    a plain ``dict``.

    Args:
        error: The exception raised by ``Agent.run()``.

    Returns:
        A ``dict`` parsed from the model's intended output, or ``None`` when
        the error is not a recoverable ``tool_use_failed`` case.
    """
    try:
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

        # Normalise Python-style literals to JSON booleans/null
        raw = re.sub(r"\bTrue\b", "true", raw)
        raw = re.sub(r"\bFalse\b", "false", raw)
        raw = re.sub(r"\bNone\b", "null", raw)

        # First attempt: strict parse
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Second attempt: repair truncated output then re-parse
            logger.debug(
                "tool_use_failed: strict JSON parse failed; attempting truncation repair"
            )
            repaired = _repair_truncated_json(raw)
            data = json.loads(repaired)

        logger.info(
            "tool_use_failed fallback: recovered JSON from failed_generation (keys=%s)",
            list(data.keys()),
        )
        return data

    except Exception as exc:
        logger.debug("tool_use_failed fallback parse error: %s", exc)
        return None


async def run_agent_with_retry(
    agent: Any,
    prompt: str,
    *,
    max_retries: int = 2,
    retry_delay: float = 0.5,
) -> Any:
    """Run *agent* with automatic retries on transient ``tool_use_failed`` errors.

    ``llama-3.1-8b-instant`` and similar small models occasionally fail with a
    ``tool_use_failed`` 400 error even when the prompt and schema are valid.
    Retrying usually succeeds because the generation is non-deterministic.

    Args:
        agent:       The ``pydantic_ai.Agent`` instance to run.
        prompt:      The user prompt string to pass to ``agent.run()``.
        max_retries: Maximum number of *additional* attempts after the first
                     failure (default ``2``, so up to 3 total attempts).
        retry_delay: Seconds to wait between attempts (default ``0.5``).

    Returns:
        The ``AgentRunResult`` returned by ``agent.run()``.

    Raises:
        The last ``ModelHTTPError`` when all attempts are exhausted and it is
        not a ``tool_use_failed`` error, or when retries run out.
    """
    from pydantic_ai.exceptions import ModelHTTPError  # noqa: PLC0415

    last_exc: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            return await agent.run(prompt)
        except ModelHTTPError as exc:
            body = getattr(exc, "body", {}) or {}
            if body.get("code") == "tool_use_failed" and attempt < max_retries:
                logger.warning(
                    "tool_use_failed on attempt %d/%d — retrying in %.1fs",
                    attempt + 1,
                    max_retries + 1,
                    retry_delay,
                )
                last_exc = exc
                await asyncio.sleep(retry_delay)
                continue
            raise
    # Should not be reached, but satisfy type checker
    raise last_exc  # type: ignore[misc]
