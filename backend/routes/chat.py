"""Multi-turn Chat Endpoint Module.

Replaces the old single-shot /consult endpoint with a session-based
multi-turn API:

  POST   /chat            — start a new consultation or continue an existing one
  DELETE /session/{id}    — explicitly end a session and clear its memory

Interaction types (``ChatRequest.type``):

  ``initial``
      First message.  Creates a new session, runs language detection +
      translation, queries RAG, and passes the full patient info to the
      triage agent.  May return a clarifying question or a final result.

  ``answer``
      Patient reply to a clarifying question.  Appended to the conversation
      history and re-evaluated by the triage agent.

  ``followup``
      Post-result "know more" question.  Handled by a dedicated follow-up
      agent constrained to the current triage context.
"""

import logging
from typing import Dict

from fastapi import APIRouter, HTTPException

from ..agents.language_agent import detect_language, translate_text
from ..agents.safety_agent import assess as safety_assess
from ..agents.triage_agent import (
    answer_followup,
    triage_result_to_triage_output,
    triage_with_history,
)
from ..config import settings
from ..schemas.chat import ChatRequest, ChatResponse
from ..services.agent_memory import memory_service
from ..services.rag_service import rag_service
from ..services.session_store import (
    MAX_CLARIFICATIONS,
    SessionData,
    create_session,
    delete_session,
    get_session,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _translate_if_needed(text: str, src_lang: str, target_lang: str) -> str:
    """Translate *text* from *src_lang* to *target_lang* if they differ."""
    if src_lang == target_lang or not text.strip():
        return text
    return await translate_text(text, target=target_lang)


async def _mem0_add(session_id: str, role: str, content: str) -> None:
    """Best-effort: store a single message turn in Mem0."""
    try:
        await memory_service.add_memory(
            session_id, [{"role": role, "content": content}]
        )
    except Exception:
        logger.debug("mem0 add failed for session %s (non-blocking)", session_id)


async def _run_triage_and_respond(session: SessionData) -> ChatResponse:
    """Run the triage agent against the current session state.

    Branches on agent response:
    - ``question`` → translate question to patient language, update session,
      store in mem0, return ChatResponse(type="question").
    - ``result``   → run safety agent, apply overrides, translate recommended
      action, update session, store in mem0, return ChatResponse(type="result").
    """
    resp = await triage_with_history(
        age=session.age,
        gender=session.gender,
        symptoms_en=session.symptoms_en,
        duration=session.duration,
        existing_conditions=session.existing_conditions,
        rag_contexts=session.rag_contexts,
        conversation=session.conversation,
        clarification_count=session.clarification_count,
        language=session.language,
    )

    if resp.response_type == "question" and resp.question:
        # -- Clarifying question path --
        question_translated = await _translate_if_needed(
            resp.question, "en", session.language
        )
        # Record in conversation history (in English for agent processing)
        session.conversation.append({"role": "assistant", "content": resp.question})
        session.clarification_count += 1
        await _mem0_add(session.session_id, "assistant", resp.question)
        logger.info(
            "Triage question %d/%d for session %s",
            session.clarification_count, MAX_CLARIFICATIONS, session.session_id,
        )
        return ChatResponse(
            type="question",
            session_id=session.session_id,
            question=question_translated,
        )

    # -- Result path --
    triage_output = triage_result_to_triage_output(resp)

    # Run safety agent
    safety = await safety_assess(triage_output, session.symptoms_en)

    # Apply emergency + safety overrides
    if "missing_emergency_escalation" in safety.risk_flags:
        triage_output.severity = "high"
        triage_output.urgency = "immediate"
    if not safety.is_safe and safety.override_message:
        triage_output.recommended_action = safety.override_message

    # Translate recommended_action to patient language
    action_translated = await _translate_if_needed(
        triage_output.recommended_action, "en", session.language
    )
    triage_output.recommended_action = action_translated

    # Store result in session
    session.triage_result = triage_output.model_dump()
    session.phase = "result_shown"

    # Mem0: store the full triage turn
    mem0_user = (
        f"Patient: age {session.age}, symptoms: {', '.join(session.symptoms_en)}, "
        f"duration: {session.duration}"
    )
    mem0_assistant = (
        f"Triage: severity={triage_output.severity}, "
        f"action={triage_output.recommended_action}, urgency={triage_output.urgency}"
    )
    session.conversation.append({"role": "assistant", "content": mem0_assistant})
    await _mem0_add(session.session_id, "user", mem0_user)
    await _mem0_add(session.session_id, "assistant", mem0_assistant)

    logger.info(
        "Triage result for session %s: severity=%r urgency=%r safe=%s",
        session.session_id, triage_output.severity, triage_output.urgency, safety.is_safe,
    )
    return ChatResponse(
        type="result",
        session_id=session.session_id,
        severity=triage_output.severity,
        possible_conditions=triage_output.possible_conditions,
        recommended_action=triage_output.recommended_action,
        urgency=triage_output.urgency,
        notes=triage_output.notes,
        safety=safety.model_dump(),
    )


# ---------------------------------------------------------------------------
# POST /chat
# ---------------------------------------------------------------------------

@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest) -> ChatResponse:
    """Unified multi-turn consultation endpoint.

    Handles three interaction types via ``payload.type``:
    - ``initial``: create a new session and start triage.
    - ``answer``: append patient reply to history and continue triage.
    - ``followup``: answer a "know more" question within the triage context.

    Returns a :class:`ChatResponse` with ``type`` set to ``"question"``,
    ``"result"``, or ``"answer"`` accordingly.
    """

    # ── INITIAL ──────────────────────────────────────────────────────────────
    if payload.type == "initial":
        if not payload.symptoms or not payload.age or not payload.duration:
            raise HTTPException(
                status_code=422,
                detail="'initial' requests require age, symptoms, and duration.",
            )

        joined_symptoms = " ".join(payload.symptoms)

        # Language detection
        detected = (
            detect_language(joined_symptoms)
            if not payload.language
            else payload.language
        )
        src_lang = detected or settings.DEFAULT_LANGUAGE
        logger.info("New chat session: lang=%r age=%s symptoms=%d",
                    src_lang, payload.age, len(payload.symptoms))

        # Translate symptoms to English
        symptoms_en_str = joined_symptoms
        if src_lang != "en":
            symptoms_en_str = await translate_text(joined_symptoms, target="en")
        symptoms_en = [s.strip() for s in symptoms_en_str.split(";") if s.strip()] or [symptoms_en_str]

        # RAG
        await rag_service.initialize()
        rag_contexts = rag_service.query(symptoms_en_str, top_k=settings.RAG_TOP_K)

        # Create session
        session = create_session(
            language=src_lang,
            symptoms_en=symptoms_en,
            rag_contexts=rag_contexts,
            age=payload.age,
            gender=payload.gender,
            duration=payload.duration,
            existing_conditions=payload.existing_conditions or [],
        )

        # Seed conversation with patient info
        patient_intro = (
            f"Patient info: age={payload.age}, gender={payload.gender or 'not specified'}, "
            f"symptoms={', '.join(symptoms_en)}, duration={payload.duration}, "
            f"existing_conditions={session.existing_conditions or 'none'}"
        )
        session.conversation.append({"role": "user", "content": patient_intro})
        await _mem0_add(session.session_id, "user", patient_intro)

        return await _run_triage_and_respond(session)

    # ── ANSWER ───────────────────────────────────────────────────────────────
    if payload.type == "answer":
        if not payload.session_id:
            raise HTTPException(status_code=422, detail="'answer' requires session_id.")
        if not payload.message or not payload.message.strip():
            raise HTTPException(status_code=422, detail="'answer' requires a non-empty message.")

        session = get_session(payload.session_id)
        if session is None:
            raise HTTPException(
                status_code=404,
                detail="Session not found or expired. Please start a new consultation.",
            )
        if session.phase == "result_shown":
            raise HTTPException(
                status_code=409,
                detail="Triage result already given. Use type='followup' for further questions.",
            )

        # Translate patient answer to English
        answer_en = await _translate_if_needed(
            payload.message.strip(), session.language, "en"
        )
        session.conversation.append({"role": "user", "content": answer_en})
        await _mem0_add(session.session_id, "user", answer_en)

        return await _run_triage_and_respond(session)

    # ── FOLLOWUP ─────────────────────────────────────────────────────────────
    if payload.type == "followup":
        if not payload.session_id:
            raise HTTPException(status_code=422, detail="'followup' requires session_id.")
        if not payload.message or not payload.message.strip():
            raise HTTPException(status_code=422, detail="'followup' requires a non-empty message.")

        session = get_session(payload.session_id)
        if session is None:
            raise HTTPException(
                status_code=404,
                detail="Session not found or expired. Please start a new consultation.",
            )
        if session.triage_result is None:
            raise HTTPException(
                status_code=409,
                detail="No triage result yet. Please complete the assessment first.",
            )

        # Translate question to English for processing
        question_en = await _translate_if_needed(
            payload.message.strip(), session.language, "en"
        )

        # Run follow-up agent (English)
        answer_en = await answer_followup(
            question_en=question_en,
            conversation=session.conversation,
            triage_result=session.triage_result,
            rag_contexts=session.rag_contexts,
            language="en",
        )

        # Translate answer back to patient language
        answer_translated = await _translate_if_needed(answer_en, "en", session.language)

        # Update conversation history and mem0
        session.conversation.append({"role": "user", "content": question_en})
        session.conversation.append({"role": "assistant", "content": answer_en})
        session.touch()
        await _mem0_add(session.session_id, "user", question_en)
        await _mem0_add(session.session_id, "assistant", answer_en)

        logger.info("Follow-up answered for session %s", session.session_id)
        return ChatResponse(
            type="answer",
            session_id=session.session_id,
            answer=answer_translated,
        )

    raise HTTPException(status_code=422, detail=f"Unknown request type: {payload.type!r}")


# ---------------------------------------------------------------------------
# DELETE /session/{session_id}
# ---------------------------------------------------------------------------

@router.delete("/session/{session_id}")
async def end_session(session_id: str) -> Dict:
    """Explicitly end a consultation session and clear its Mem0 memories.

    This is called when the user starts a new conversation. Clears session
    state from the in-memory store and removes associated mem0 vectors.

    Returns ``{"ok": true}`` whether or not the session existed.
    """
    existed = delete_session(session_id)
    # Best-effort: clear mem0 memories
    try:
        await memory_service.delete_session_memory(session_id)
    except Exception:
        logger.debug("mem0 cleanup failed for session %s (non-blocking)", session_id)
    logger.info("Session ended: %s (existed=%s)", session_id, existed)
    return {"ok": True}
