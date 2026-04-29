"""LLM Client Service Module.

This module provides a unified interface for calling OpenAI-compatible LLM APIs to generate
medical triage responses and other text completions. It handles both production and offline
scenarios:

  1. **Production Mode** (LLM_API_KEY configured): Calls the configured OpenAI-compatible
     LLM endpoint specified via `LLM_API_URL` and `MODEL_NAME` environment variables.
  2. **Offline/Fallback Mode** (no LLM_API_KEY): Uses a deterministic keyword-based heuristic
     to generate plausible medical triage responses locally without external API calls.

Key Features:
  - **Flexible API Support**: Handles multiple LLM response schemas (OpenAI, local models, etc.)
  - **Graceful Degradation**: Falls back to heuristic responses when no API key is configured
  - **Async-First Design**: All functions are async-compatible for non-blocking I/O
  - **Configurable Inference**: Supports custom temperature and max_tokens parameters
  - **Robust Error Handling**: Catches network/parsing errors and returns fallback responses

Environment Variables (via settings):
  - `LLM_API_URL`: Base URL of the OpenAI-compatible LLM service (e.g., http://ollama:11434/v1)
  - `LLM_API_KEY`: API key for authentication (if not set, uses heuristic fallback)
  - `MODEL_NAME`: Name of the model to use (e.g., "gpt-3.5-turbo", "mistral")

Example:
    Generate a medical triage response:

    >>> from services.llm_client import generate
    >>> response = await generate("Patient reports fever and cough for 3 days")
    >>> result = json.loads(response)
    >>> print(result["severity"])  # e.g., "medium"
"""

import json
import logging

import httpx

from ..config import settings

logger = logging.getLogger(__name__)


async def _local_heuristic_response(prompt: str) -> str:
    """Generate a deterministic medical triage response using keyword matching.

    This is a fallback function used when no LLM API is available (e.g., offline mode
    or missing API key). It performs simple keyword-based heuristics to classify symptom
    severity and recommend appropriate actions. The output is formatted as JSON to match
    the LLM API response structure.

    Args:
        prompt (str): The patient symptom description or triage query.

    Returns:
        str: A JSON-formatted string containing triage result with keys:
            - severity: One of "low", "medium", or "high"
            - possible_conditions: List of suspected condition descriptions
            - recommended_action: Text recommendation for the patient
            - urgency: Timeframe for seeking medical attention
            - notes: Explanation that this is a heuristic fallback response

    Note:
        This is purely for MVP functionality and testing. Real medical triage
        should always use a qualified LLM or clinical professional.
    """
    text = prompt.lower()
    severity = "low"
    # Classify severity as "high" if critical symptoms are detected
    if any(
        k in text
        for k in [
            "chest pain",
            "shortness of breath",
            "unconscious",
            "severe bleeding",
            "stroke",
        ]
    ):
        severity = "high"
    # Classify as "medium" for moderate symptoms requiring same-day medical attention
    elif any(k in text for k in ["fever", "severe pain", "vomiting", "dehydration"]):
        severity = "medium"

    # Generate severity-appropriate recommendations
    if severity == "high":
        recommended = "Seek immediate medical help (emergency)."
        urgency = "immediate"
        possible = ["serious condition - seek emergency care"]
    elif severity == "medium":
        recommended = "See a doctor within 24 hours."
        urgency = "within 24 hours"
        possible = ["common infection", "moderate illness"]
    else:
        recommended = "Home care and monitor; consult a clinician if symptoms worsen."
        urgency = "self-monitor"
        possible = ["non-urgent condition"]

    # Structure response to match LLM API output format
    out = {
        "severity": severity,
        "possible_conditions": possible,
        "recommended_action": recommended,
        "urgency": urgency,
        "notes": "Fallback heuristic used because LLM_API_KEY is not configured.",
    }
    return json.dumps(out)


async def generate(prompt: str, max_tokens: int = 512, temperature: float = 0.2) -> str:
    """Generate text completion using an OpenAI-compatible LLM API or fallback heuristic.

    Calls the configured LLM endpoint to generate structured medical triage responses.
    If no API key is configured, automatically uses a keyword-based heuristic for offline
    functionality. Handles multiple LLM response formats and recovers gracefully from
    network or parsing errors.

    Args:
        prompt (str): The input prompt for text generation (typically a patient symptom
            description for medical triage).
        max_tokens (int, optional): Maximum length of the generated response in tokens.
            Default is 512.
        temperature (float, optional): Sampling temperature for response randomness.
            Lower values (e.g., 0.2) produce more deterministic responses.
            Default is 0.2 (deterministic).

    Returns:
        str: The generated text response. Format depends on the LLM API being used:
            - For OpenAI-compatible APIs: typically raw text content
            - For heuristic fallback: JSON-formatted triage result

    Raises:
        None: This function never raises exceptions. Network/parsing failures are
        logged and the function returns a heuristic fallback response instead.

    Note:
        Response format varies by LLM provider. Consumers should handle both
        plain text and JSON-formatted responses.
    """
    # If no API key is configured, use deterministic heuristic to keep MVP functional offline
    if not settings.LLM_API_KEY:
        return await _local_heuristic_response(prompt)

    # Build request to OpenAI-compatible LLM endpoint
    url = settings.LLM_API_URL.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.MODEL_NAME,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            body = resp.json()

            # Parse response: support multiple LLM API response formats
            if isinstance(body, dict):
                # Format 1: Direct 'output' field (e.g., some local Ollama variants)
                if "output" in body and isinstance(body["output"], str):
                    return body["output"]
                # Format 2: 'outputs' array with 'content' field (e.g., some inference servers)
                if (
                    "outputs" in body
                    and isinstance(body["outputs"], list)
                    and body["outputs"]
                ):
                    first = body["outputs"][0]
                    if isinstance(first, dict) and "content" in first:
                        return first["content"]
                    return json.dumps(first)
                # Format 3: OpenAI-compatible 'choices' with 'text' or 'message' field
                if (
                    "choices" in body
                    and isinstance(body["choices"], list)
                    and body["choices"]
                ):
                    ch = body["choices"][0]
                    # Extract from choice.text (older completion format)
                    if isinstance(ch, dict) and "text" in ch:
                        return ch["text"]
                    # Extract from choice.message.content (chat completion format)
                    if (
                        isinstance(ch, dict)
                        and "message" in ch
                        and isinstance(ch["message"], dict)
                    ):
                        return ch["message"].get("content", "")

            # Last resort: decode raw bytes as UTF-8 to preserve non-ASCII text
            return resp.content.decode("utf-8", errors="replace")

        except Exception as e:
            # Log error and return deterministic fallback response
            logger.exception("LLM API call failed: %s", e)
            return await _local_heuristic_response(prompt)
