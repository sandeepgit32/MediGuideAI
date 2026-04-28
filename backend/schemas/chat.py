"""Chat API request and response schemas for MediGuideAI multi-turn sessions."""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Unified request body for the POST /chat endpoint.

    Three interaction types share this schema:

    ``initial``
        First message in a new consultation.  Provide all patient demographics.
        Leave ``session_id`` as ``None`` — a new UUID is created server-side.

    ``answer``
        Patient's reply to a clarifying question.  ``session_id`` is required.
        Provide the reply text in ``message``.

    ``followup``
        A "know more" question after the triage result has been shown.
        ``session_id`` is required.  Provide the question in ``message``.
        Answers are constrained to the current triage context.
    """

    type: Literal["initial", "answer", "followup"] = Field(
        ..., description="Interaction type"
    )
    session_id: Optional[str] = Field(
        None,
        description="Existing session UUID (required for 'answer' and 'followup')",
    )

    # --- Initial-request fields (type="initial") ---
    age: Optional[int] = Field(None, ge=0, le=120, description="Patient age in years")
    gender: Optional[str] = Field(None, description="Patient gender (optional)")
    symptoms: Optional[List[str]] = Field(
        None, min_length=1, description="List of symptom phrases"
    )
    duration: Optional[str] = Field(
        None, description="How long symptoms have been present"
    )
    existing_conditions: Optional[List[str]] = Field(
        None, description="Pre-existing medical conditions"
    )
    language: Optional[str] = Field(
        None, description="ISO 639-1 language code (e.g. 'en', 'hi', 'bn', 'es', 'fr')"
    )

    # --- Follow-on fields (type="answer" or "followup") ---
    message: Optional[str] = Field(
        None,
        description="Patient reply to a clarifying question, or a follow-up question",
    )


class ChatResponse(BaseModel):
    """Response from POST /chat.

    The ``type`` field determines which fields are populated:

    ``question``
        The triage agent needs one more piece of information.
        ``question`` contains the translated question to display.

    ``result``
        A triage result is ready.  All result fields are populated.

    ``answer``
        A follow-up answer in response to a ``followup`` request.
        ``answer`` contains the translated answer text.
    """

    type: Literal["question", "result", "answer"] = Field(
        ..., description="Response type"
    )
    session_id: str = Field(..., description="Session UUID for subsequent requests")

    # --- type="question" ---
    question: Optional[str] = Field(
        None, description="Translated clarifying question for the patient"
    )

    # --- type="result" ---
    severity: Optional[Literal["low", "medium", "high"]] = None
    possible_conditions: Optional[List[str]] = None
    recommended_action: Optional[str] = None
    urgency: Optional[str] = None
    notes: Optional[str] = None
    safety: Optional[dict] = None

    # --- type="answer" ---
    answer: Optional[str] = Field(None, description="Translated follow-up answer")
