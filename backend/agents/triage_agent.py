"""Clinical Triage Agent.

This module implements the core AI triage step (the preliminary assessment of patients)
in the MediGuideAI pipeline.

The triage agent receives:

* Patient demographics (age, gender).
* Reported symptoms and their duration.
* Known pre-existing conditions.
* Relevant WHO guideline excerpts retrieved via RAG.

It returns a validated :class:`~backend.schemas.triage.TriageOutput` with:

* ``severity``            — ``"low"`` / ``"medium"`` / ``"high"``
* ``possible_conditions`` — non-diagnostic suggestions (most likely first)
* ``recommended_action``  — a single actionable sentence for the patient
* ``urgency``             — timeframe string (e.g. ``"immediate"``, ``"within 24 hours"``)
* ``notes``               — optional disclaimer / uncertainty note

Severity classification criteria
---------------------------------
``"high"``
  Any life-threatening red flag is present (chest pain, breathing difficulty,
  stroke signs, loss of consciousness, severe bleeding, anaphylaxis, high fever
  in an infant < 3 months, suspected poisoning).

``"medium"``
  Professional care is needed but the condition is not immediately
  life-threatening (persistent fever, worsening pain, dehydration signs,
  symptoms not resolving after 48 h of home care).

``"low"``
  Mild, self-limiting symptoms appropriate for home care (common cold,
  minor cuts, mild indigestion).

**When in doubt, the agent errs toward a higher severity level.**

"""

import json
import logging
from typing import List

from ..schemas.patient import PatientInput
from ..schemas.triage import TriageOutput
from ..utils.prompts import build_triage_prompt
from ..config import settings
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelHTTPError
from ..utils.llm_fallback import extract_failed_generation_json, run_agent_with_retry

logger = logging.getLogger(__name__)

_AGENT = Agent(
    settings.get_llm_model(),
    output_type=TriageOutput,
    instructions=(
        "You are a conservative clinical triage assistant embedded in an AI system for low-resource "
        "rural health settings. Given patient demographics, symptoms, symptom duration, existing "
        "conditions, and WHO guideline context, produce a TriageOutput JSON object.\n\n"
        "Severity classification rules:\n"
        "  HIGH   — any life-threatening red flag: chest pain/tightness, breathing difficulty, "
        "stroke signs (facial droop / arm weakness / slurred speech), loss of consciousness, "
        "seizure, severe uncontrolled bleeding, anaphylaxis (throat swelling), fever > 38 °C in "
        "infant under 3 months, suspected poisoning or overdose.  Recommend immediate emergency care.\n"
        "  MEDIUM — non-emergency but requires professional evaluation: persistent fever (> 38.5 °C "
        "for > 48 h), worsening or spreading pain, signs of dehydration, confusion, symptoms not "
        "improving after 48 h of home care.  Recommend seeing a clinician within 24 hours.\n"
        "  LOW    — mild, self-limiting symptoms manageable at home: common cold, minor cuts without "
        "heavy bleeding, mild indigestion, mild headache without neurological signs.  Recommend home "
        "care with specific warning signs to watch for.\n\n"
        "Content rules:\n"
        "1. Use cautious, non-diagnostic phrasing: 'may suggest', 'could indicate', 'possible'.\n"
        "2. You may suggest common Over-the-Counter (OTC) medications with standard adult/paediatric "
        "dosages where appropriate (e.g. paracetamol, ibuprofen, oral rehydration salts, "
        "antihistamines, antacids). Always note the patient should confirm suitability with a "
        "pharmacist or clinician. You must NEVER name, recommend, or allude to any "
        "prescription-only medication.\n"
        "3. recommended_action must be one to three concise, actionable sentences.\n"
        "4. possible_conditions must list ≥ 1 entry; omit conditions with < ~10 % plausibility.\n"
        "5. notes must include a one-sentence disclaimer that this is not a medical diagnosis.\n"
        "6. When uncertain between two severity levels, choose the higher one.\n"
        "7. Call get_severity_guide() when unsure which severity level applies."
    ),
    system_prompt=(
        "Patient safety is your primary constraint. Never provide a diagnosis or recommend any "
        "prescription-only medication. You may suggest appropriate Over-the-Counter (OTC) medications "
        "with standard dosages, always advising confirmation with a pharmacist or clinician. "
        "Always recommend clinical review when uncertain. Every response must include a note that it "
        "is not a substitute for professional medical advice."
    ),
    name="triage_agent",
)


@_AGENT.tool_plain
def get_severity_guide() -> dict:
    """Return authoritative clinical criteria for each triage severity level.

    The agent may call this tool when it is uncertain which severity level
    applies to a given set of symptoms.  The returned dictionary maps each
    severity label to a list of representative clinical indicators.

    Returns:
        A dict with keys ``"high"``, ``"medium"``, and ``"low"``, each
        containing a list of indicator strings.
    """
    return {
        "high": [
            "chest pain or tightness",
            "difficulty breathing or shortness of breath",
            "stroke signs: facial droop, arm weakness, slurred speech, sudden severe headache",
            "loss of consciousness, unresponsive, or altered mental status",
            "seizures or uncontrolled convulsions",
            "severe or uncontrolled bleeding",
            "severe allergic reaction with throat swelling or hives",
            "fever above 38 °C or 100.4 °F in an infant under 3 months",
            "suspected poisoning or overdose",
        ],
        "medium": [
            "persistent fever above 38.5 °C or 101.3 °F for more than 48 hours",
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


async def triage(
    patient: PatientInput, context_texts: List[str], language: str = "en"
) -> TriageOutput:
    """Produce a validated :class:`TriageOutput` for the given patient.

    Constructs a structured prompt from the patient record and WHO guideline
    context, then runs the Pydantic-AI triage agent.  The agent may invoke
    :func:`get_severity_guide` during its reasoning pass to resolve severity
    ambiguity before committing to a final structured output.

    The function handles three output shapes returned by the agent runtime:

    * ``TriageOutput`` instance — returned directly.
    * ``dict``                  — coerced via ``TriageOutput(**output)``.
    * ``str`` (JSON)            — parsed then coerced.

    If none of the above match, :class:`ValueError` is raised so the caller
    can apply the heuristic fallback.

    Args:
        patient:       Validated patient input (age, gender, symptoms, duration,
                       existing_conditions).
        context_texts: WHO guideline excerpts retrieved by the RAG service for
                       the patient's symptom set.  May be empty if RAG is
                       unavailable; the agent degrades gracefully.
        language:      ISO 639-1 code used for response-language hints in the
                       prompt (default ``"en"``).

    Returns:
        A fully validated :class:`TriageOutput` instance.

    Raises:
        ValueError: When the agent returns an output that cannot be coerced
            into :class:`TriageOutput`.
        pydantic.ValidationError: When the agent output is parseable but
            violates the schema constraints.
        json.JSONDecodeError: When the agent returns a malformed JSON string.
    """
    prompt = build_triage_prompt(patient, context_texts, language)
    logger.info(
        "Triage agent invoked: age=%s gender=%s symptoms=%s context_docs=%d lang=%r",
        patient.age,
        patient.gender,
        patient.symptoms,
        len(context_texts),
        language,
    )

    try:
        result = await run_agent_with_retry(_AGENT, prompt)
        output = getattr(result, "output", None)
    except ModelHTTPError as exc:
        logger.warning(
            "Triage ModelHTTPError — attempting failed_generation fallback: %s", exc
        )
        data = extract_failed_generation_json(exc)
        if data is None:
            logger.error("Triage fallback failed; re-raising ModelHTTPError")
            raise
        logger.info("Triage fallback succeeded (keys=%s)", list(data.keys()))
        return TriageOutput(**data)
    if isinstance(output, TriageOutput):
        logger.info(
            "Triage output: severity=%r urgency=%r", output.severity, output.urgency
        )
        return output
    if isinstance(output, dict):
        logger.debug("Triage agent returned dict; coercing to TriageOutput")
        return TriageOutput(**output)
    if isinstance(output, str):
        logger.debug("Triage agent returned string; parsing JSON")
        data = json.loads(output)
        return TriageOutput(**data)

    logger.error("Triage agent returned unrecognised type: %s", type(output).__name__)
    raise ValueError(
        f"Triage agent returned an unrecognised output type: {type(output).__name__}"
    )
