"""Clinical Triage Agent — multi-turn session support.

This module provides two public coroutines:

``triage_with_history``
    Core clinical assessment.  On each call the agent inspects the full
    conversation history and either asks ONE clarifying question (when
    ``clarification_count < MAX_CLARIFICATIONS`` and more information would
    materially improve accuracy) or produces a final triage result.  Once
    ``clarification_count >= MAX_CLARIFICATIONS`` the agent is forced to
    produce a result regardless.

    Returns a :class:`TriageConsultResponse` whose ``response_type`` is either
    ``"question"`` or ``"result"``.

``answer_followup``
    Answers a patient's "know more" question **strictly within** the context of
    the current triage session (reported symptoms, demographics, triage result,
    and clinical guideline excerpts).  Off-topic health questions are politely
    declined.

    Returns a plain ``str`` answer suitable for direct display (after translation).

Both coroutines delegate to pydantic-ai Agents and reuse the existing
``run_agent_with_retry`` / ``extract_failed_generation_json`` fallback helpers.
"""

import json
import logging
from typing import Dict, List, Optional

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelHTTPError

from ..config import settings
from ..schemas.triage import TriageOutput
from ..utils.llm_fallback import extract_failed_generation_json, run_agent_with_retry
from ..utils.prompts import build_followup_prompt, build_triage_history_prompt

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# TriageConsultResponse — unified output for multi-turn triage
# ---------------------------------------------------------------------------


class TriageConsultResponse(BaseModel):
    """Output type for the multi-turn triage agent.

    When ``response_type`` is ``"question"`` only ``question`` is populated.
    When ``response_type`` is ``"result"`` all triage fields are populated and
    ``question`` is ``None``.
    """

    response_type: str = Field(
        ...,
        description="Either 'question' (need more info) or 'result' (assessment ready)",
    )
    # Clarifying question (populated when response_type="question")
    question: Optional[str] = Field(
        None, description="Single targeted clinical question for the patient"
    )
    # Triage result fields (populated when response_type="result")
    severity: Optional[str] = Field(None, description="low / medium / high")
    possible_conditions: Optional[List[str]] = Field(
        None, description="Most-likely conditions (non-diagnostic)"
    )
    recommended_action: Optional[str] = Field(
        None, description="Concise actionable recommendation"
    )
    urgency: Optional[str] = Field(None, description="Timeframe for seeking care")
    notes: Optional[str] = Field(
        None, description="Optional disclaimer / uncertainty note"
    )


# ---------------------------------------------------------------------------
# Triage Agent
# ---------------------------------------------------------------------------

_TRIAGE_AGENT = Agent(
    settings.get_llm_model(),
    output_type=TriageConsultResponse,
    instructions=(
        "You are a conservative clinical triage assistant for low-resource rural health settings.\n\n"
        "You will receive patient demographics, symptoms, and the conversation so far.\n\n"
        "PATIENT MEMORY — If a '# Patient Memory (from previous consultations)' section is present "
        "in the prompt, you MUST actively use it to:\n"
        "  a) Smart Follow-up: If the patient had a similar complaint recently, note whether symptoms "
        "are persisting, worsening, or recurring, and factor this into severity assessment.\n"
        "  b) Chronic Conditions: If the patient has a recorded chronic condition (e.g. asthma, "
        "diabetes, hypertension), take it into account when assessing current symptoms and urgency. "
        "Escalate severity if the current complaint could be a complication of that condition.\n"
        "  c) Allergy Safety: If the patient has any recorded allergies (e.g. penicillin, NSAIDs), "
        "explicitly call them out in 'notes' and ensure your recommended_action does NOT suggest "
        "any medication they are allergic to.\n\n"
        "DECISION:\n"
        "  A) If a single targeted clarifying question would materially change the severity "
        "assessment AND the clarification budget is not exhausted, set response_type='question' "
        "and populate 'question' with ONE short, plain-language question. Leave all other fields null.\n"
        "  B) Otherwise — including when the clarification budget IS exhausted — set "
        "response_type='result' and populate ALL triage fields. Leave 'question' null.\n\n"
        "Severity rules:\n"
        "  HIGH   — any life-threatening red flag: chest pain/tightness, breathing difficulty, "
        "stroke signs (facial droop/arm weakness/slurred speech), loss of consciousness, seizure, "
        "severe uncontrolled bleeding, anaphylaxis (throat swelling), fever >38\u00b0C in infant <3 months, "
        "suspected poisoning/overdose. Recommend immediate emergency care.\n"
        "  MEDIUM — non-emergency but requires professional evaluation: persistent fever >38.5\u00b0C >48h, "
        "worsening or spreading pain, signs of dehydration, confusion, symptoms not improving after "
        "48h home care. Recommend seeing a clinician within 24 hours.\n"
        "  LOW    — mild, self-limiting symptoms manageable at home. Recommend home care with specific "
        "warning signs to watch for.\n\n"
        "Content rules:\n"
        "1. Use cautious, non-diagnostic phrasing: 'may suggest', 'could indicate', 'possible'.\n"
        "2. You may suggest common OTC medications (paracetamol, ibuprofen, ORS, antihistamines, "
        "antacids) with standard adult/paediatric dosages where appropriate. Always note the patient "
        "should confirm suitability with a pharmacist or clinician. NEVER name or recommend any "
        "prescription-only medication.\n"
        "3. recommended_action must be one to three concise, actionable sentences.\n"
        "4. possible_conditions must list >= 1 entry (when response_type='result').\n"
        "5. notes must include a one-sentence disclaimer that this is not a medical diagnosis. "
        "If the patient has any known allergies retrieved from memory, also mention them in notes.\n"
        "6. When uncertain between two severity levels, choose the higher one.\n"
        "7. Call get_severity_guide() when unsure which severity level applies."
    ),
    system_prompt=(
        "Patient safety is your primary constraint. Never provide a diagnosis or recommend any "
        "prescription-only medication. Always recommend clinical review when uncertain. Every result "
        "response must include a note that it is not a substitute for professional medical advice. "
        "Always check patient memory for known allergies and chronic conditions before making recommendations."
    ),
    name="triage_agent",
)


@_TRIAGE_AGENT.tool_plain
def get_severity_guide() -> dict:
    """Return authoritative clinical criteria for each triage severity level."""
    return {
        "high": [
            "chest pain or tightness",
            "difficulty breathing or shortness of breath",
            "stroke signs: facial droop, arm weakness, slurred speech, sudden severe headache",
            "loss of consciousness, unresponsive, or altered mental status",
            "seizures or uncontrolled convulsions",
            "severe or uncontrolled bleeding",
            "severe allergic reaction with throat swelling or hives",
            "fever above 38 C or 100.4 F in an infant under 3 months",
            "suspected poisoning or overdose",
        ],
        "medium": [
            "persistent fever above 38.5 C or 101.3 F for more than 48 hours",
            "worsening or spreading localised pain",
            "signs of dehydration: dry mouth, sunken eyes, no urine output",
            "confusion, disorientation, or unusual behaviour",
            "symptoms not improving after 48 hours of appropriate home care",
            "wound showing signs of infection: redness, warmth, pus",
        ],
        "low": [
            "mild cold or flu with manageable symptoms",
            "minor cuts or bruises without significant bleeding",
            "mild digestive upset without signs of dehydration",
            "mild headache without visual changes or neck stiffness",
            "mild sore throat without difficulty swallowing or breathing",
        ],
    }


async def triage_with_history(
    age: int,
    gender: Optional[str],
    symptoms_en: List[str],
    duration: str,
    existing_conditions: List[str],
    rag_contexts: List[str],
    conversation: List[Dict],
    clarification_count: int,
    language: str = "en",
    mem0_history: Optional[List[str]] = None,
) -> TriageConsultResponse:
    """Run the multi-turn triage agent given the full conversation history."""
    from ..services.session_store import MAX_CLARIFICATIONS

    prompt = build_triage_history_prompt(
        age=age,
        gender=gender,
        symptoms_en=symptoms_en,
        duration=duration,
        existing_conditions=existing_conditions,
        rag_contexts=rag_contexts,
        conversation=conversation,
        clarification_count=clarification_count,
        max_clarifications=MAX_CLARIFICATIONS,
        language=language,
        mem0_history=mem0_history,
    )
    logger.info(
        "Triage agent (multi-turn): age=%s symptoms=%s clarification_count=%d/%d lang=%r",
        age,
        symptoms_en,
        clarification_count,
        MAX_CLARIFICATIONS,
        language,
    )
    try:
        result = await run_agent_with_retry(_TRIAGE_AGENT, prompt)
        output = getattr(result, "output", None)
    except ModelHTTPError as exc:
        logger.warning("Triage ModelHTTPError — attempting fallback: %s", exc)
        data = extract_failed_generation_json(exc)
        if data is None:
            raise
        return TriageConsultResponse(**data)

    if isinstance(output, TriageConsultResponse):
        return output
    if isinstance(output, dict):
        return TriageConsultResponse(**output)
    if isinstance(output, str):
        return TriageConsultResponse(**json.loads(output))

    raise ValueError(
        f"Triage agent returned unrecognised output type: {type(output).__name__}"
    )


def triage_result_to_triage_output(resp: TriageConsultResponse) -> TriageOutput:
    """Convert a result-type TriageConsultResponse into a TriageOutput."""
    return TriageOutput(
        severity=resp.severity or "medium",
        possible_conditions=resp.possible_conditions or ["Unknown"],
        recommended_action=resp.recommended_action
        or "Please consult a healthcare professional.",
        urgency=resp.urgency or "as soon as possible",
        notes=resp.notes,
    )


# ---------------------------------------------------------------------------
# Follow-up Agent
# ---------------------------------------------------------------------------

_FOLLOWUP_AGENT = Agent(
    settings.get_llm_model(),
    output_type=str,
    instructions=(
        "You are a clinical follow-up assistant that answers questions about a patient's "
        "CURRENT triage session only.\n\n"
        "Rules:\n"
        "1. You MUST restrict your answer strictly to the patient's reported symptoms, "
        "demographics, existing conditions, and the triage result already produced. "
        "Do NOT introduce new medical topics or conditions not mentioned in the session.\n"
        "2. If the question is unrelated to the current triage context, respond with: "
        "'I can only answer questions about your current assessment. Please start a new "
        "consultation for a different health concern.'\n"
        "3. Use simple, plain language suitable for a low-literacy audience.\n"
        "4. You may expand on OTC medications already mentioned in the triage result. "
        "NEVER recommend prescription medications.\n"
        "5. Always remind the patient that this is guidance only and not a substitute for "
        "professional medical advice.\n"
        "6. Keep answers concise: 2 to 5 sentences."
    ),
    name="followup_agent",
)


async def answer_followup(
    question_en: str,
    conversation: List[Dict],
    triage_result: Dict,
    rag_contexts: List[str],
    language: str = "en",
) -> str:
    """Answer a follow-up question within the scope of the current triage session."""
    prompt = build_followup_prompt(
        question_en=question_en,
        conversation=conversation,
        triage_result=triage_result,
        rag_contexts=rag_contexts,
        language=language,
    )
    logger.info(
        "Follow-up agent invoked: question=%r lang=%r", question_en[:80], language
    )
    try:
        result = await run_agent_with_retry(_FOLLOWUP_AGENT, prompt)
        output = getattr(result, "output", None)
    except ModelHTTPError as exc:
        logger.warning("Followup ModelHTTPError — attempting fallback: %s", exc)
        data = extract_failed_generation_json(exc)
        if data is None:
            raise
        if isinstance(data, dict):
            return data.get("output", str(data))
        return str(data)

    if isinstance(output, str):
        return output
    if isinstance(output, dict):
        return output.get("output", str(output))

    raise ValueError(
        f"Follow-up agent returned unrecognised output type: {type(output).__name__}"
    )
