"""Clinical Safety Assessment Agent.

This module implements the safety-guardrail step in the MediGuideAI pipeline.

The safety agent audits the triage output produced by the triage agent and
the raw patient symptoms to detect unsafe, inappropriate, or potentially
harmful recommendations before they are shown to the patient.

It returns a validated :class:`~backend.schemas.safety.SafetyOutput` with:

* ``is_safe``          — ``True`` only when no risk flags apply.
* ``risk_flags``       — list of flag keys identifying the safety issue(s).
* ``override_message`` — conservative alternative action when ``is_safe`` is
  ``False``; ``None`` otherwise.

Risk flag vocabulary
--------------------
``prescription_mentioned``
  The recommendation contains a specific drug name or dosage.

``missing_emergency_escalation``
  Symptoms suggest an emergency but severity is not ``"high"``.

``underestimated_severity``
  Severity appears too low relative to the reported symptoms.

``dangerous_home_care_advice``
  Recommends staying home when professional or emergency care is warranted.

``contradictory_recommendation``
  The ``recommended_action`` contradicts the stated ``severity``.

``hallucination_like``
  The triage output contains medically implausible conditions or advice.

``insufficient_urgency``
  The ``urgency`` field understates the clinical need.

Design notes
------------
* Built on **Pydantic-AI** :class:`~pydantic_ai.Agent` with ``output_type``
  set to :class:`SafetyOutput`.
* The ``check_prescription_patterns`` tool performs a fast regex scan of the
  triage recommendation text so the LLM has concrete evidence when deciding
  whether to raise the ``prescription_mentioned`` flag.
* The agent is deliberately conservative: ambiguous cases produce
  ``is_safe=False`` and a generic override message.
"""

import json
import logging
import re
from typing import List

from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelHTTPError

from ..schemas.safety import SafetyOutput
from ..schemas.triage import TriageOutput
from ..config import settings
from ..utils.prompts import build_safety_prompt
from ..utils.llm_fallback import extract_failed_generation_json

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prescription-pattern heuristics used by the check_prescription_patterns tool
# ---------------------------------------------------------------------------
_PRESCRIPTION_PATTERNS: list[tuple[str, str]] = [
    (r"\b\d+\s*mg\b", "dosage_mention"),
    (r"\b(take|prescribe|administer|give)\s+\w+", "prescriptive_verb"),
    (
        r"\b(ibuprofen|paracetamol|acetaminophen|amoxicillin|metformin|aspirin|"
        r"penicillin|ciprofloxacin|metronidazole|diazepam|codeine|morphine)\b",
        "named_drug",
    ),
]

_SAFETY_AGENT = Agent(
    settings.get_llm_model(),
    output_type=SafetyOutput,
    instructions=(
        "You are the clinical safety guardrail for an AI triage system deployed in low-resource settings. "
        "Evaluate the triage output and the patient's reported symptoms for safety issues.\n\n"
        "Risk flag vocabulary — use ONLY these exact keys in risk_flags:\n"
        "  'prescription_mentioned'       — recommendation refers to a specific drug or dosage\n"
        "  'missing_emergency_escalation' — symptoms indicate an emergency but severity ≠ 'high'\n"
        "  'underestimated_severity'      — severity is too low for the reported symptoms\n"
        "  'dangerous_home_care_advice'   — advises home care when professional care is clearly needed\n"
        "  'contradictory_recommendation' — recommended_action contradicts severity level\n"
        "  'hallucination_like'           — output contains medically implausible conditions or advice\n"
        "  'insufficient_urgency'         — urgency field understates the clinical need\n\n"
        "Assessment rules:\n"
        "1. Call check_prescription_patterns with the recommended_action text to detect drug mentions.\n"
        "2. Set is_safe=True only when no risk flags apply.\n"
        "3. Populate risk_flags with every applicable flag key from the vocabulary above.\n"
        "4. When is_safe=False, override_message must be a single conservative action sentence "
        "   (e.g. 'Please seek immediate medical care at the nearest health facility.').\n"
        "5. When is_safe=True, set override_message to null.\n"
        "6. For ambiguous cases prefer is_safe=False — patient safety outweighs false positives."
    ),
    system_prompt=(
        "You are the final safety gate before a triage recommendation reaches the patient. "
        "Any response that could cause a patient to delay necessary care, self-medicate dangerously, "
        "or underestimate a life-threatening condition MUST be flagged and overridden with a safe, "
        "conservative message."
    ),
    name="safety_agent",
)


@_SAFETY_AGENT.tool_plain
def check_prescription_patterns(recommendation_text: str) -> dict:
    """Scan *recommendation_text* for prescription-like patterns.

    Performs a fast regex search for drug dosages, prescriptive verbs, and
    named common medications.  The results give the safety agent concrete
    evidence when deciding whether to raise the ``prescription_mentioned``
    risk flag.

    Args:
        recommendation_text: The ``recommended_action`` string from the
            ``TriageOutput`` to be scanned.

    Returns:
        A dict with:

        * ``has_prescription_pattern`` (bool) — ``True`` if any pattern matched.
        * ``matched_pattern_types`` (list[str]) — symbolic names of matched
          pattern categories (e.g. ``["named_drug", "dosage_mention"]``).
    """
    matched_types: list[str] = []
    for pattern, label in _PRESCRIPTION_PATTERNS:
        if re.search(pattern, recommendation_text, re.IGNORECASE):
            matched_types.append(label)
    return {
        "has_prescription_pattern": bool(matched_types),
        "matched_pattern_types": matched_types,
    }


async def assess(triage: TriageOutput, symptoms: List[str]) -> SafetyOutput:
    """Audit a triage recommendation for clinical safety issues.

    Runs the Pydantic-AI safety agent against the triage output and the
    patient's raw symptom list.  The agent calls
    :func:`check_prescription_patterns` to gather evidence before producing
    its final :class:`SafetyOutput`.

    The function handles three output shapes returned by the agent runtime:

    * ``SafetyOutput`` instance — returned directly.
    * ``dict``                  — coerced via ``SafetyOutput(**output)``.
    * ``str`` (JSON)            — parsed then coerced.

    Args:
        triage:   The :class:`TriageOutput` produced by the triage agent that
                  is to be audited.
        symptoms: The patient's raw (English) symptom list used to cross-check
                  the triage output against the original complaint.

    Returns:
        A validated :class:`SafetyOutput` describing the safety assessment.

    Raises:
        ValueError: When the agent returns an output that cannot be coerced
            into :class:`SafetyOutput`.
        json.JSONDecodeError: When the agent returns a malformed JSON string.
    """
    prompt = build_safety_prompt(triage, symptoms)
    try:
        result = await _SAFETY_AGENT.run(prompt)
        output = getattr(result, "output", None)
    except ModelHTTPError as exc:
        data = extract_failed_generation_json(exc)
        if data is None:
            raise
        return SafetyOutput(**data)
    if isinstance(output, SafetyOutput):
        return output
    if isinstance(output, dict):
        return SafetyOutput(**output)
    if isinstance(output, str):
        data = json.loads(output)
        return SafetyOutput(**data)
    raise ValueError(
        f"Safety agent returned an unrecognised output type: {type(output).__name__}"
    )
