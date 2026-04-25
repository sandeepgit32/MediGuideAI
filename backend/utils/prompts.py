"""Prompt builders for all MediGuideAI agents.

Each function constructs the user-facing prompt string that is passed to a
Pydantic-AI ``Agent.run()`` call.  Keeping prompts here (rather than inlined
in agent modules) makes them easy to review, test, and iterate on without
touching agent logic.

Functions
---------
build_triage_prompt      — Clinical triage assessment (triage_agent).
build_translation_prompt — Language translation (language_agent).
build_safety_prompt      — Safety audit of a triage output (safety_agent).
build_escalation_prompt  — Emergency red-flag detection (escalation_agent).
"""

from typing import List


def build_triage_prompt(patient, context_texts: List[str], language: str = "en") -> str:
    """Construct a concise prompt for the LLM that requests structured JSON output.

    The prompt follows the engineering rules: disclaimer, uncertainty language,
    simple phrasing, and explicit JSON schema instruction.
    """
    context = "\n\n".join(context_texts) if context_texts else ""
    symptoms = ", ".join(patient.symptoms) if getattr(patient, "symptoms", None) else ""

    prompt = f"""
You are a medical triage assistant for low-resource settings. This is not a medical diagnosis.
Use simple language. Encourage the user to see a health worker. Avoid giving medication dosages or prescriptions.
If emergency red flags are present, set severity to "high" and recommend immediate medical attention.

Context (use if helpful):
{context}

Patient info:
age: {patient.age}
gender: {patient.gender}
symptoms: {symptoms}
duration: {patient.duration}
existing_conditions: {getattr(patient, "existing_conditions", [])}

Provide output in JSON ONLY with the following keys:
- severity: one of "low", "medium", "high"
- possible_conditions: list of short strings (non-diagnostic suggestions)
- recommended_action: short instruction: e.g., 'Home care and monitor', 'See doctor', 'Seek immediate medical help'
- urgency: short string e.g., 'immediate', 'within 24 hours', 'self-monitor'
- notes: optional uncertainty language (one sentence)

Keep answers short and suitable for translation. Do not provide prescriptions or exact diagnoses.
Return valid JSON only.
"""
    # If the user's language is not English, ask the model to respond in that language (but still JSON)
    if language and language != "en":
        prompt += f"\nRespond in language: {language}."

    return prompt


def build_translation_prompt(text: str, target: str) -> str:
    """Construct a prompt for the language agent to translate *text* into *target*.

    The prompt enforces low-literacy-appropriate language, faithful preservation
    of medical terminology, and a clean output (translated text only, no labels).

    Args:
        text:   Source text to be translated.
        target: ISO 639-1 code of the desired output language (e.g. ``"hi"``,
                ``"fr"``, ``"sw"``).  Callers must ensure ``target != "en"``
                before calling this function; no short-circuit logic is applied
                here.

    Returns:
        A prompt string ready to be passed to ``_LANG_AGENT.run()``.
    """
    return (
        f"Translate the following text into {target}.\n\n"
        "Requirements:\n"
        "- Use simple language suitable for a rural, low-literacy audience.\n"
        "- Preserve medical terminology; add a brief clarification in parentheses\n"
        "  only if the term would be unclear to a non-specialist.\n"
        "- Do not add advice, diagnoses, or commentary beyond what is in the source.\n"
        "- Return only the translated text — no labels or explanations.\n\n"
        f"Source text:\n{text}"
    )


def build_safety_prompt(triage, symptoms: List[str]) -> str:
    """Construct a prompt for the safety agent to audit a triage recommendation.

    Formats the triage output as an indented JSON block and the symptom list as
    a bullet list, then instructs the agent to call ``check_prescription_patterns``
    before finalising its ``SafetyOutput``.

    Args:
        triage:   A ``TriageOutput`` instance (duck-typed; must expose
                  ``model_dump_json(indent=2)``).
        symptoms: The patient's raw (English) symptom strings, used to
                  cross-check the triage output.

    Returns:
        A prompt string ready to be passed to ``_SAFETY_AGENT.run()``.
    """
    symptom_list = "\n".join(f"  - {s}" for s in symptoms)
    return (
        "Review the triage output and patient symptoms below.  Identify any safety issues and "
        "return a SafetyOutput JSON object.\n\n"
        "# Triage Output\n"
        f"```json\n{triage.model_dump_json(indent=2)}\n```\n\n"
        "# Patient Symptoms\n"
        f"{symptom_list}\n\n"
        "Call check_prescription_patterns on the recommended_action before finalising your assessment.\n"
        "Return ONLY valid SafetyOutput JSON: "
        '{"is_safe": <bool>, "risk_flags": [<flag_key>, ...], "override_message": <str|null>}'
    )


def build_escalation_prompt(
    symptoms: List[str], keyword_scan: dict | None = None
) -> str:
    """Construct a prompt for the escalation agent to detect emergency red flags.

    Formats the symptom list as a bullet list and includes the pre-computed
    keyword scan result so the LLM can use it as a first-pass signal without
    needing to call a tool.

    Args:
        symptoms: The patient's (English) symptom strings.
        keyword_scan: Optional dict with ``matched_flags`` (list[str]) and
            ``is_likely_emergency`` (bool) from a pre-run keyword scan.

    Returns:
        A prompt string ready to be passed to ``_AGENT.run()``.
    """
    symptom_lines = "\n".join(f"  - {s}" for s in symptoms)
    scan_section = ""
    if keyword_scan is not None:
        matched = keyword_scan.get("matched_flags", [])
        likely = keyword_scan.get("is_likely_emergency", False)
        flags_str = ", ".join(matched) if matched else "none"
        scan_section = (
            f"\n# Keyword Pre-Scan Result\n"
            f"  matched_flags: {flags_str}\n"
            f"  is_likely_emergency: {str(likely).lower()}\n"
        )
    return (
        "Analyze the patient symptoms below for life-threatening emergency signs.\n\n"
        "# Patient Symptoms\n"
        f"{symptom_lines}\n"
        f"{scan_section}\n"
        "Apply clinical reasoning to confirm or extend the keyword scan — catch any "
        "emergency signs not covered by keyword matching.\n"
        'Return ONLY valid EscalationOutput JSON: {"is_emergency": <bool>, "flags": [<flag_key>, ...]}'
    )
