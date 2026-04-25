"""Patient Consultation Endpoint Module.

This module defines the primary REST API endpoint for patient medical consultations.
It orchestrates a multi-stage processing pipeline that:

1. **Language Detection & Translation**: Detects patient input language and translates
   to English for consistent processing.
2. **Contextual Information Retrieval**: Queries the RAG service to fetch relevant
   WHO medical guidelines matching the patient's symptoms.
3. **AI-Powered Triage**: Uses a specialized language model agent to assess symptom
   severity, identify possible conditions, and recommend appropriate actions.
4. **Emergency Escalation Detection**: Checks for life-threatening symptoms that
   require immediate emergency services.
5. **Safety Assessment**: Runs a safety filter to catch harmful recommendations and
   enforce conservative clinical overrides.
6. **Persistent Storage**: Saves the consultation to MongoDB for audit trails and
   stores patient memory in Mem0 for personalized future consultations.

The consultation flow is designed to be clinically credible while providing graceful
fallbacks for offline scenarios (e.g., when LLM APIs are unavailable).

Key Design Principles:
  - Non-blocking async I/O throughout to support high concurrency
  - Best-effort persistence (failures in memory/storage don't block response)
  - Conservative safety override: patient safety takes precedence over triage results
  - Multilingual support for diverse patient populations

Example Request:
    POST /consult
    {
        "age": 35,
        "gender": "female",
        "symptoms": ["fever", "cough"],
        "duration": "3 days",
        "language": "en"
    }

Example Response:
    {
        "severity": "medium",
        "possible_conditions": ["pneumonia", "bronchitis"],
        "recommended_action": "See a doctor within 24 hours",
        "urgency": "within 24 hours",
        "safety": {...},
        "emergency_flags": []
    }
"""

import uuid
from typing import Dict

from fastapi import APIRouter

from ..agents.escalation_agent import detect_emergency
from ..agents.language_agent import detect_language, translate_text
from ..agents.safety_agent import assess as safety_assess
from ..agents.triage_agent import triage as triage_agent
from ..config import settings
from ..schemas.patient import PatientInput
from ..schemas.safety import SafetyOutput
from ..schemas.triage import TriageOutput
from ..services.agent_memory import memory_service
from ..services.consultation_store import consultation_store
from ..services.rag_service import rag_service

router = APIRouter()


@router.post("/consult")
async def consult(payload: PatientInput) -> Dict:
    """Process a patient consultation request through the medical triage pipeline.

    This endpoint orchestrates the complete consultation workflow: language handling,
    contextual information retrieval, AI-powered triage assessment, emergency detection,
    safety validation, and persistent storage of results.

    Args:
        payload (PatientInput): Patient data including age, gender, symptoms, duration,
            and optional language preference. Pydantic validation ensures all required
            fields are present and valid.

    Returns:
        Dict: Consultation result containing:
            - severity (str): One of "low", "medium", or "high"
            - possible_conditions (list[str]): Suspected medical conditions
            - recommended_action (str): Clinical recommendation for the patient
            - urgency (str): Timeframe for seeking medical attention
            - safety (dict): Safety assessment details and override flags
            - emergency_flags (list[str]): Emergency indicators if any

    Raises:
        None: Failures in downstream services (RAG, agents, storage) are caught
        and handled gracefully; the endpoint always returns a valid response.

    Note:
        - Language translation to English ensures consistent LLM processing
        - RAG context significantly improves triage accuracy
        - Safety assessment may override triage recommendations for patient protection
        - Patient memory is stored for continuity of care across multiple consultations
    """
    # ----- Step 1: Language Detection & Translation -----
    # Pydantic validation ensures payload is well-formed before reaching this point
    # Combine symptoms into a single string for language detection
    joined_symptoms = " ".join(payload.symptoms)
    # Use provided language or auto-detect from symptom text
    detected = (
        detect_language(joined_symptoms) if not payload.language else payload.language
    )
    src_lang = detected or settings.DEFAULT_LANGUAGE

    # Translate symptoms to English for LLM processing and RAG queries
    # This ensures consistent triage logic regardless of patient's native language
    symptoms_en = joined_symptoms
    if src_lang != "en":
        symptoms_en = await translate_text(joined_symptoms, target="en")

    # ----- Step 2: Contextual Information Retrieval (RAG) -----
    # Initialize RAG service and retrieve WHO guidelines relevant to patient symptoms
    # Contextual documents significantly improve triage accuracy and evidence-based recommendations
    await rag_service.initialize()
    contexts = rag_service.query(symptoms_en, top_k=settings.RAG_TOP_K)

    # Prepare English-translated payload for triage agent
    # Split translated symptoms back into a list, handling both semicolon and single symptom formats
    payload_en = payload.model_copy(
        update={
            "symptoms": [s.strip() for s in symptoms_en.split(";") if s.strip()]
            or [symptoms_en]
        }
    )

    # ----- Step 3: AI-Powered Triage Assessment -----
    # Call the triage agent with English symptoms, RAG context, and original language
    # The agent returns severity, possible conditions, and recommended actions
    triage_result: TriageOutput = await triage_agent(
        payload_en, contexts, language=src_lang
    )

    # ----- Step 4: Emergency Escalation Detection -----
    # Check for life-threatening symptoms that require immediate emergency services
    # Emergency override takes precedence over triage assessment for patient safety
    emergency, emergency_flags = await detect_emergency(payload.symptoms)
    if emergency:
        # Force severity to high and override recommended action for emergency cases
        triage_result.severity = "high"
        triage_result.recommended_action = (
            "Seek immediate medical help (emergency services)."
        )
        triage_result.urgency = "immediate"

    # ----- Step 5: Safety Assessment & Override -----
    # Run safety filter to catch potentially harmful or clinically inappropriate recommendations
    # If safety issues detected, override triage recommendation with conservative alternative
    safety: SafetyOutput = await safety_assess(triage_result, payload.symptoms)
    if not safety.is_safe:
        # Override triage recommendation with conservative, safe alternative
        # Patient safety check takes absolute precedence
        triage_result.recommended_action = (
            safety.override_message or "Seek medical attention."
        )

    # ----- Step 6: Persistent Storage (Best-Effort) -----
    # Save consultation results to agent memory (Mem0) and MongoDB for continuity of care
    # and audit compliance. Failures in this step do not block the response.
    try:
        # Generate unique consultation identifier
        consultation_id = str(uuid.uuid4())
        # Structure complete consultation record for MongoDB
        consultation_data = {
            "last_input": payload.model_dump(),
            "triage": triage_result.model_dump(),
            "safety": safety.model_dump(),
            "emergency_flags": emergency_flags,
        }

        # Format consultation as OpenAI-style conversation for Mem0 fact extraction
        # Mem0 will extract structured facts about symptoms, diagnosis, and recommendations
        # These facts are vectorized and stored for retrieval on future patient consultations
        mem0_messages = [
            {
                "role": "user",
                "content": f"Patient: age {payload.age}, symptoms: {', '.join(payload.symptoms)}, duration: {payload.duration}",
            },
            {
                "role": "assistant",
                "content": f"Triage: severity={triage_result.severity}, action={triage_result.recommended_action}, urgency={triage_result.urgency}",
            },
        ]

        # Use age-gender fingerprint as patient identifier for memory continuity
        # TODO: In production, replace with authenticated patient UUID from identity system
        patient_memory_id = f"patient-{payload.age}-{payload.gender or 'unknown'}"

        # Store memory for personalized future consultations
        await memory_service.add_memory(patient_memory_id, mem0_messages)
        # Persist complete consultation record to MongoDB for analytics and compliance
        await consultation_store.save(consultation_id, consultation_data)
    except Exception:
        # Non-blocking failure: storage errors do not prevent response delivery
        pass

    # ----- Step 7: Return Structured Response -----
    # Assemble final consultation result with all assessment components
    return {
        "severity": triage_result.severity,
        "possible_conditions": triage_result.possible_conditions,
        "recommended_action": triage_result.recommended_action,
        "urgency": triage_result.urgency,
        "safety": safety.dict(),
        "emergency_flags": emergency_flags,
    }
