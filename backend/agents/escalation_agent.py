"""Emergency Escalation Detection Agent.

This module implements the emergency-detection step in the MediGuideAI pipeline.

The escalation agent scans a patient's reported symptoms for life-threatening
red flags that require *immediate* emergency intervention.  When any flag is
detected the calling route forces ``severity = "high"`` in the final response,
regardless of the triage agent's assessment.

Emergency flag vocabulary
--------------------------
``chest_pain``         — chest tightness, pressure, or pain.
``breathing``          — difficulty breathing, shortness of breath, or respiratory arrest.
``stroke``             — facial drooping, arm weakness, slurred speech, sudden severe headache.
``bleeding``           — severe, uncontrolled, or internal bleeding.
``unconscious``        — loss of consciousness, unresponsive, or altered mental status.
``seizure``            — convulsions or uncontrolled shaking.
``anaphylaxis``        — severe allergic reaction with throat or tongue swelling.
``high_fever_infant``  — fever above 38 °C in a child under 3 months.
``poisoning``          — suspected ingestion of a toxic substance or overdose.
``severe_dehydration`` — inability to keep fluids down, sunken eyes, or no urine output.

Design notes
------------
* Built on **Pydantic-AI** :class:`~pydantic_ai.Agent` with ``output_type``
  set to :class:`EscalationOutput` for validated structured output.
* The ``scan_emergency_keywords`` tool performs a fast keyword scan so the LLM
  has concrete evidence before producing its final assessment.  The LLM then
  applies clinical reasoning on top of this signal to catch rephrased or
  implicit emergency descriptions that keyword matching alone would miss.
"""

from typing import List, Tuple
import json

from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelHTTPError

from ..schemas.escalation import EscalationOutput
from ..config import settings
from ..utils.prompts import build_escalation_prompt
from ..utils.llm_fallback import extract_failed_generation_json

# ---------------------------------------------------------------------------
# Keyword lookup table used by the scan_emergency_keywords tool
# ---------------------------------------------------------------------------
_EMERGENCY_KEYWORDS: dict[str, list[str]] = {
    "chest_pain": [
        "chest pain",
        "chest tightness",
        "chest pressure",
        "heart pain",
    ],
    "breathing": [
        "difficulty breathing",
        "shortness of breath",
        "can't breathe",
        "cannot breathe",
        "breathing difficulty",
        "respiratory distress",
        "choking",
    ],
    "stroke": [
        "facial droop",
        "face drooping",
        "arm weakness",
        "slurred speech",
        "sudden severe headache",
        "sudden headache",
        "vision loss suddenly",
    ],
    "bleeding": [
        "severe bleeding",
        "heavy bleeding",
        "uncontrolled bleeding",
        "blood loss",
        "bleeding heavily",
        "internal bleeding",
    ],
    "unconscious": [
        "unconscious",
        "fainted",
        "loss of consciousness",
        "unresponsive",
        "passed out",
        "not waking up",
    ],
    "seizure": [
        "seizure",
        "convulsion",
        "convulsions",
        "fit",
        "shaking uncontrollably",
    ],
    "anaphylaxis": [
        "throat swelling",
        "anaphylaxis",
        "severe allergic",
        "tongue swelling",
        "hives and breathing",
    ],
    "high_fever_infant": [
        "high fever infant",
        "fever baby",
        "infant fever",
        "fever newborn",
    ],
    "poisoning": [
        "poisoning",
        "swallowed toxin",
        "ingested toxic",
        "overdose",
        "swallowed medication",
    ],
    "severe_dehydration": [
        "cannot keep fluids",
        "no urine",
        "sunken eyes",
        "severe dehydration",
        "not urinating",
    ],
}

_AGENT = Agent(
    settings.get_llm_model(),
    output_type=EscalationOutput,
    instructions=(
        "You are an emergency-detection agent for a medical triage system.  "
        "Given a list of patient-reported symptoms, identify any life-threatening red flags.\n\n"
        "Emergency flag vocabulary — use ONLY these exact keys in the 'flags' list:\n"
        "  'chest_pain'          — chest tightness, pressure, or pain\n"
        "  'breathing'           — difficulty breathing, shortness of breath, respiratory arrest\n"
        "  'stroke'              — facial drooping, arm weakness, slurred speech, sudden severe headache\n"
        "  'bleeding'            — severe, uncontrolled, or internal bleeding\n"
        "  'unconscious'         — loss of consciousness, unresponsive, altered mental status\n"
        "  'seizure'             — convulsions or uncontrolled shaking\n"
        "  'anaphylaxis'         — severe allergic reaction with throat or tongue swelling\n"
        "  'high_fever_infant'   — fever above 38 °C in a child under 3 months\n"
        "  'poisoning'           — suspected ingestion of a toxic substance or overdose\n"
        "  'severe_dehydration'  — inability to keep fluids down, sunken eyes, no urine output\n\n"
        "Assessment rules:\n"
        "1. A keyword pre-scan result is provided in the prompt — use it as a first-pass signal.\n"
        "2. Set is_emergency=True if ANY flag applies — even if the keyword scan returns no matches but "
        "   clinical reasoning suggests an emergency (e.g. rephrased descriptions).\n"
        "3. Populate flags with every applicable flag key from the vocabulary above.\n"
        "4. Do NOT add narrative or explanations — return only the EscalationOutput JSON.\n"
        "5. Err on the side of caution: a false positive is safer than a missed emergency."
    ),
    system_prompt=(
        "You are a triage safety net.  If a symptom could plausibly indicate a life-threatening "
        "emergency, set is_emergency=True and include the relevant flag.  Missing a real emergency "
        "is far more dangerous than a false alarm."
    ),
    name="escalation_agent",
)


def scan_emergency_keywords(symptoms_text: str) -> dict:
    """Keyword-scan *symptoms_text* for known emergency patterns.

    Performs a fast, case-insensitive substring search against a curated
    keyword table covering all ten emergency flag categories.  The result
    gives the LLM a concrete first-pass signal; the LLM then applies clinical
    reasoning to catch rephrased or implicit emergency descriptions not covered
    by the keyword list.

    Args:
        symptoms_text: The combined patient symptom string to scan (e.g. the
            symptoms joined by commas or spaces).

    Returns:
        A dict with:

        * ``matched_flags`` (list[str]) — flag keys where at least one keyword
          matched.
        * ``is_likely_emergency`` (bool) — ``True`` if any flag matched.

    Example::

        scan_emergency_keywords("chest pain and shortness of breath")
        # → {"matched_flags": ["chest_pain", "breathing"], "is_likely_emergency": True}
    """
    lower = symptoms_text.lower()
    matched: list[str] = [
        flag
        for flag, keywords in _EMERGENCY_KEYWORDS.items()
        if any(kw in lower for kw in keywords)
    ]
    return {"matched_flags": matched, "is_likely_emergency": bool(matched)}


async def detect_emergency(symptoms: List[str]) -> Tuple[bool, List[str]]:
    """Detect life-threatening emergency flags in *symptoms*.

    Runs the Pydantic-AI escalation agent, which calls
    :func:`scan_emergency_keywords` as a first-pass keyword signal and then
    applies clinical reasoning to produce a validated
    :class:`EscalationOutput`.

    The function handles three output shapes returned by the agent runtime:

    * ``EscalationOutput`` instance — fields returned directly.
    * ``dict``                       — ``is_emergency`` and ``flags`` extracted.
    * ``str`` (JSON)                 — parsed then fields extracted.

    Args:
        symptoms: List of symptom strings in English as reported or translated
                  from the patient.

    Returns:
        A two-tuple ``(is_emergency, flags)`` where:

        * ``is_emergency`` (bool)   — ``True`` if any emergency sign detected.
        * ``flags`` (list[str])     — list of matched emergency flag keys
          (see module docstring for the full vocabulary).

    Raises:
        ValueError: When the agent returns an output that cannot be interpreted
            as an :class:`EscalationOutput`.
        json.JSONDecodeError: When the agent returns a malformed JSON string.
    """
    symptoms_text = " ".join(symptoms)
    keyword_result = scan_emergency_keywords(symptoms_text)
    prompt = build_escalation_prompt(symptoms, keyword_result)

    try:
        result = await _AGENT.run(prompt)
        output = getattr(result, "output", None)
    except ModelHTTPError as exc:
        data = extract_failed_generation_json(exc)
        if data is None:
            raise
        return bool(data.get("is_emergency")), list(data.get("flags", []))
    if isinstance(output, EscalationOutput):
        return output.is_emergency, output.flags
    if isinstance(output, dict):
        return bool(output.get("is_emergency")), list(output.get("flags", []))
    if isinstance(output, str):
        data = json.loads(output)
        return bool(data.get("is_emergency")), list(data.get("flags", []))

    raise ValueError(
        f"Escalation agent returned an unrecognised output type: {type(output).__name__}"
    )
