"""Prompt builders for all MediGuideAI agents.

Each function constructs the user-facing prompt string passed to a pydantic-ai
``Agent.run()`` call.

Functions
---------
build_triage_history_prompt  — Multi-turn triage assessment (triage_agent).
build_translation_prompt     — Language translation (language_agent).
build_safety_prompt          — Safety audit of a triage output (safety_agent).
build_followup_prompt        — Follow-up Q&A constrained to current session (followup_agent).
"""

import json
from typing import Dict, List, Optional


def build_triage_history_prompt(
    age: int,
    gender: Optional[str],
    symptoms_en: List[str],
    duration: str,
    existing_conditions: List[str],
    rag_contexts: List[str],
    conversation: List[Dict],
    clarification_count: int,
    max_clarifications: int,
    language: str = "en",
) -> str:
    """Construct the prompt for the multi-turn triage agent.

    Includes the full conversation history and a clarification budget so the
    agent knows whether it may still ask a question or must produce a result.

    Args:
        age: Patient age in years.
        gender: Patient gender string or None.
        symptoms_en: English symptom strings.
        duration: Duration string.
        existing_conditions: List of pre-existing conditions.
        rag_contexts: clinical guideline excerpts from RAG.
        conversation: Full ``[{role, content}]`` history in English.
        clarification_count: Number of clarifying questions already asked.
        max_clarifications: Maximum allowed clarifying questions.
        language: ISO 639-1 response language hint.

    Returns:
        Prompt string ready to pass to ``_TRIAGE_AGENT.run()``.
    """
    context_block = "\n\n".join(rag_contexts) if rag_contexts else "No guidelines available."
    symptoms_str = ", ".join(symptoms_en) if symptoms_en else "not specified"
    conditions_str = ", ".join(existing_conditions) if existing_conditions else "none reported"
    gender_str = gender or "not specified"

    # Build the conversation history block
    history_lines: List[str] = []
    for msg in conversation:
        role = msg.get("role", "user").capitalize()
        content = msg.get("content", "")
        history_lines.append(f"[{role}]: {content}")
    history_block = "\n".join(history_lines) if history_lines else "(no prior conversation)"

    budget_remaining = max_clarifications - clarification_count
    if budget_remaining <= 0:
        clarification_instruction = (
            "CLARIFICATION BUDGET EXHAUSTED — you MUST return response_type='result' now. "
            "Do NOT ask any more questions."
        )
    else:
        clarification_instruction = (
            f"Clarification budget: {budget_remaining} question(s) remaining. "
            "You may ask ONE targeted question only if it would materially change the severity "
            "assessment. If the information already available is sufficient, return a result."
        )

    prompt = f"""You are a medical triage assistant for low-resource settings. This is not a medical diagnosis.

# Clinical Context (clinical Guidelines)
{context_block}

# Patient Information
- Age: {age}
- Gender: {gender_str}
- Symptoms: {symptoms_str}
- Duration: {duration}
- Existing conditions: {conditions_str}

# Conversation History
{history_block}

# Clarification Policy
{clarification_instruction}

# Instructions
Return a TriageConsultResponse JSON object:
- If asking a clarifying question:
  {{"response_type": "question", "question": "<single plain-language question>", "severity": null, "possible_conditions": null, "recommended_action": null, "urgency": null, "notes": null}}
- If producing a triage result:
  {{"response_type": "result", "question": null, "severity": "<low|medium|high>", "possible_conditions": ["..."], "recommended_action": "<1-3 sentences>", "urgency": "<timeframe>", "notes": "<disclaimer>"}}

Use cautious, non-diagnostic language. Keep answers simple and suitable for translation.
Do not prescribe medications. Return valid JSON only.
"""
    if language and language != "en":
        prompt += f"\nWhen response_type='question', write the question in language: {language}."

    return prompt


def build_translation_prompt(text: str, target: str) -> str:
    """Construct a prompt for the language agent to translate *text* into *target*.

    Args:
        text:   Source text to be translated.
        target: ISO 639-1 code of the desired output language.

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

    Args:
        triage:   A ``TriageOutput`` instance.
        symptoms: The patient's raw (English) symptom strings.

    Returns:
        A prompt string ready to be passed to ``_SAFETY_AGENT.run()``.
    """
    symptom_list = "\n".join(f"  - {s}" for s in symptoms)

    emergency_flags_reminder = (
        "\nEMERGENCY RED FLAGS to check in symptoms list:\n"
        "  chest pain, difficulty breathing, stroke signs (facial droop/arm weakness/slurred speech),\n"
        "  loss of consciousness, seizure, severe uncontrolled bleeding, anaphylaxis (throat swelling),\n"
        "  fever >38C in infant <3 months, suspected poisoning/overdose.\n"
        "If ANY of these are present and severity != 'high', you MUST include 'missing_emergency_escalation'.\n"
    )

    return (
        "Review the triage output and patient symptoms below. Identify any safety issues and "
        "return a SafetyOutput JSON object.\n\n"
        "# Triage Output\n"
        f"```json\n{triage.model_dump_json(indent=2)}\n```\n\n"
        "# Patient Symptoms\n"
        f"{symptom_list}\n"
        f"{emergency_flags_reminder}\n"
        "Call check_prescription_patterns on the recommended_action before finalising your assessment.\n"
        'Return ONLY valid SafetyOutput JSON: '
        '{"is_safe": <bool>, "risk_flags": [<flag_key>, ...], "override_message": <str|null>}'
    )


def build_followup_prompt(
    question_en: str,
    conversation: List[Dict],
    triage_result: Dict,
    rag_contexts: List[str],
    language: str = "en",
) -> str:
    """Construct a prompt for the follow-up agent.

    The agent is constrained to answer only within the scope of the current
    triage session context.

    Args:
        question_en:   The patient's follow-up question (in English).
        conversation:  Full ``[{role, content}]`` history in English.
        triage_result: Dict representation of the triage result.
        rag_contexts:  clinical guideline excerpts from this session.
        language:      ISO 639-1 code for response language hint.

    Returns:
        A prompt string ready to pass to ``_FOLLOWUP_AGENT.run()``.
    """
    context_block = "\n\n".join(rag_contexts) if rag_contexts else "No guidelines available."

    history_lines: List[str] = []
    for msg in conversation:
        role = msg.get("role", "user").capitalize()
        history_lines.append(f"[{role}]: {msg.get('content', '')}")
    history_block = "\n".join(history_lines) if history_lines else "(none)"

    triage_block = json.dumps(triage_result, indent=2) if triage_result else "{}"

    prompt = f"""You are answering a follow-up question about this patient's CURRENT triage session.

# Session Triage Result
```json
{triage_block}
```

# Relevant clinical Guidelines (session context)
{context_block}

# Conversation History
{history_block}

# Patient's Follow-up Question
{question_en}

# Instructions
- Answer ONLY based on the triage result and symptoms above.
- If the question is unrelated, say: "I can only answer questions about your current assessment. Please start a new consultation for a different health concern."
- Use simple language. 2 to 5 sentences. Include a brief disclaimer that this is not a substitute for professional medical advice.
- Do NOT recommend prescription medications.
- Return only the answer text, no JSON.
"""
    if language and language != "en":
        prompt += f"\nRespond in language: {language}."

    return prompt
