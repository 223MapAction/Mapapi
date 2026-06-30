"""Thin HTTP client around the model-deploy chat endpoint."""
import os

import requests
from django.conf import settings


def ask_model_chat(messages, context):
    """Forward a chat conversation + structured context to the LLM service.

    ``messages`` is a list of ``{"role": "...", "content": "..."}`` items.
    ``context`` is the structured prediction dictionary (Prediction.full_response).
    Returns the assistant text response.
    Raises ``requests.exceptions.RequestException`` on transport errors.
    """
    chat_url = getattr(
        settings,
        "MODEL_DEPLOY_CHAT_URL",
        os.getenv("MODEL_DEPLOY_CHAT_URL", "http://localhost:8001/chat"),
    )
    timeout = int(getattr(
        settings,
        "MODEL_DEPLOY_CHAT_TIMEOUT",
        os.getenv("MODEL_DEPLOY_CHAT_TIMEOUT", 120),
    ))

    payload = {
        "messages": messages,
        "context": context,
    }

    response = requests.post(chat_url, json=payload, timeout=timeout)
    response.raise_for_status()

    # The model-deploy /chat endpoint returns plain text per the user's design.
    # If a future version returns JSON like {"message": "..."}, callers can
    # migrate without touching the views.
    return response.text
