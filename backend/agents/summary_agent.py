"""Consultation Summary Agent.

Generates a concise one-paragraph English summary of a completed consultation,
covering the reported symptoms, symptom duration, any pre-existing conditions,
and the patient's answers to each clarification question asked by the triage agent.

The summary is stored in the ``consultation_history`` table and displayed in
the History page so users can quickly recall what was discussed in past sessions.
"""

import logging
from typing import Optional

from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelHTTPError

from ..config import settings
from ..services.session_store import SessionData
from ..utils.prompts import build_summary_prompt

logger = logging.getLogger(__name__)

_SUMMARY_AGENT = Agent(
    settings.get_llm_model(),
    output_type=str,
    instructions=(
        "You write brief, factual summaries of medical consultations for personal health records. "
        "Your summaries are plain English, one paragraph, 3-5 sentences. "
        "Include: symptoms reported, duration, any pre-existing conditions, and a short account of "
        "what the patient answered to each clarification question. "
        "Do NOT include any diagnosis, medical advice, or triage outcome. "
        "Return only the paragraph text with no headings, labels, or bullet points."
    ),
    name="summary_agent",
)


async def generate_summary(session: SessionData) -> Optional[str]:
    """Generate a one-paragraph summary for the completed consultation.

    Extracts Q&A pairs from *session.conversation* (skipping the opening
    patient-info message and the closing triage-log message) and asks the
    LLM to produce a plain-English paragraph.

    Returns the summary string, or ``None`` if the LLM call fails so that
    the consultation history record is still saved without a summary.

    Args:
        session: The completed :class:`SessionData` instance.  The conversation
            list must contain all clarification messages but must NOT yet
            include the final "Triage: severity=..." assistant message (that
            line is appended in ``chat.py`` after this function is called).

    Returns:
        A plain-English summary string, or ``None`` on error.
    """
    prompt = build_summary_prompt(
        symptoms_en=session.symptoms_en,
        duration=session.duration,
        existing_conditions=session.existing_conditions,
        conversation=session.conversation,
        gender=session.gender,
    )
    try:
        result = await _SUMMARY_AGENT.run(prompt)
        output = getattr(result, "output", None)
        if isinstance(output, str):
            return output.strip() or None
        return None
    except ModelHTTPError as exc:
        logger.warning("Summary agent ModelHTTPError — skipping summary: %s", exc)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Summary agent error — skipping summary: %s", exc)
        return None
