"""Language Detection and Translation Agent.

This module provides two capabilities for the MediGuideAI pipeline:

1. **Language detection** — probabilistic identification of a text's ISO 639-1
   language code using the ``langdetect`` library (port of Google's
   language-detection algorithm).

2. **LLM-backed translation** — an ``Agent`` that renders text into any
   target language using simple, low-literacy-appropriate phrasing suitable
   for patients in rural or low-resource settings.

The agent is *intentionally narrow*: it translates without interpreting,
diagnosing, or adding clinical commentary.  All medical terminology is
preserved verbatim (with an optional parenthetical clarification) so that
downstream triage and safety agents receive accurate symptom descriptions.

Typical usage in the consultation pipeline::

    detected_lang = detect_language(joined_symptoms)
    # Translate patient text to English for consistent downstream processing
    symptoms_en = await translate_text(joined_symptoms, target="en")
    # After triage, translate the response back to the patient's language
    localised_response = await translate_text(response_text, target=detected_lang)
"""

import logging
from typing import Optional

from langdetect import LangDetectException, detect
from pydantic_ai import Agent

from ..config import settings
from ..utils.prompts import build_translation_prompt

logger = logging.getLogger(__name__)


def detect_language(text: str) -> Optional[str]:
    """Detect the ISO 639-1 language code of *text*.

    Uses ``langdetect`` (Google language-detection algorithm) which performs
    probabilistic n-gram analysis.  Accuracy improves significantly for inputs
    longer than ~20 characters; very short or numeric-only inputs may return
    incorrect results.

    Args:
        text: The string whose language is to be identified.

    Returns:
        An ISO 639-1 code (e.g. ``"en"``, ``"hi"``, ``"fr"``, ``"sw"``) on
        success, or ``None`` when detection fails — for example when *text* is
        empty, numeric-only, or contains only punctuation.

    Example::

        >>> detect_language("Je me sens très fatigué")
        'fr'
        >>> detect_language("")  # empty input → None
        None
    """
    try:
        lang = detect(text)
        logger.info("Language detected: %r (text_length=%d)", lang, len(text))
        return lang
    except LangDetectException:
        logger.warning(
            "Language detection failed for text_length=%d; returning None", len(text)
        )
        return None


# ---------------------------------------------------------------------------
# Language Agent
# ---------------------------------------------------------------------------
_LANG_AGENT = Agent(
    settings.get_llm_model(),
    instructions=(
        "You are a professional medical translator for patients in rural, low-resource settings.\n\n"
        "Translation rules:\n"
        "1. Translate the supplied text accurately into the requested target language.\n"
        "2. Use the simplest vocabulary available — aim for a primary-school reading level.\n"
        "3. Preserve medical terms exactly; where a direct translation may confuse the reader, "
        "   append a brief clarification in parentheses, e.g. 'hypertension (high blood pressure)'.\n"
        "4. Do NOT add medical advice, diagnoses, reassurances, or any content not present in the "
        "   source text.\n"
        "5. Maintain the original tone and urgency — do not soften or escalate the message.\n"
        "6. Return ONLY the translated text — no preamble, no labels, no explanations.\n"
        "7. If the text is already in the requested target language, return it unchanged."
    ),
    system_prompt=(
        "You are a concise, accurate medical translator. Your sole job is to render text faithfully "
        "into another language for non-specialist readers. Never interpret symptoms, never add clinical "
        "commentary, and never alter the urgency of the original message."
    ),
    name="language_agent",
)


async def translate_text(text: str, target: str = "en") -> str:
    """Translate *text* into *target* language using the language agent.

    This is a thin coroutine around ``_LANG_AGENT.run``.  It short-circuits
    (returns *text* unchanged) when:

    * *target* equals ``"en"`` and no translation is needed (caller has
      confirmed the text is already in English), **or**
    * *text* is empty or whitespace-only.

    The prompt instructs the model to return only the translated string so
    callers can use the output directly without stripping extra prose.

    Args:
        text:   The source text to translate.  May be a single sentence or a
                multi-sentence patient description.
        target: ISO 639-1 code of the desired output language (default
                ``"en"`` for English).  Examples: ``"hi"`` (Hindi),
                ``"fr"`` (French), ``"sw"`` (Swahili).

    Returns:
        The translated string, or the original *text* if the target is
        English or the input is blank.  Leading/trailing whitespace is
        stripped from the model output.

    Example::

        translated = await translate_text("J'ai de la fièvre", target="en")
        # → "I have a fever"
    """
    if not text or not text.strip():
        logger.debug("translate_text called with empty text; returning as-is")
        return text
    if target == "en":
        return text

    logger.info("Translating text to %r (source_length=%d)", target, len(text))
    prompt = build_translation_prompt(text, target)
    result = await _LANG_AGENT.run(prompt)
    out = getattr(result, "output", "")
    translated = (out or "").strip()
    logger.info("Translation complete: output_length=%d", len(translated))
    return translated
