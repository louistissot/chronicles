"""
LLM abstraction layer — routes prompts to either Anthropic (claude-sonnet-4-6)
or OpenAI (configurable model, default gpt-4o).

Supports both blocking (call_llm) and streaming (stream_llm) modes.
"""
from typing import Callable, Optional

from log import get_logger

_log = get_logger("llm")


def call_llm(
    prompt: str,
    provider: str,           # "anthropic" or "openai"
    api_key: str,
    model: Optional[str] = None,
    max_tokens: int = 4096,
) -> str:
    """
    Send `prompt` as a user message and return the assistant text response.
    Raises on API error.
    """
    if provider == "anthropic":
        import anthropic
        chosen_model = model or "claude-sonnet-4-6"
        _log.info("→ Anthropic  model=%s  max_tokens=%d  prompt_len=%d", chosen_model, max_tokens, len(prompt))
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=chosen_model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text
        _log.info("← Anthropic  response_len=%d  stop_reason=%s", len(text), response.stop_reason)
        return text

    elif provider == "openai":
        from openai import OpenAI
        chosen_model = model or "gpt-4o"
        _log.info("→ OpenAI  model=%s  max_tokens=%d  prompt_len=%d", chosen_model, max_tokens, len(prompt))
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=chosen_model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.choices[0].message.content or ""
        _log.info("← OpenAI  response_len=%d  finish_reason=%s", len(text), response.choices[0].finish_reason)
        return text

    else:
        raise ValueError(f"Unknown LLM provider: {provider!r}")


def stream_llm(
    prompt: str,
    provider: str,
    api_key: str,
    model: Optional[str] = None,
    max_tokens: int = 4096,
    on_chunk: Optional[Callable[[str], None]] = None,
    stop_check: Optional[Callable[[], bool]] = None,
) -> str:
    """
    Stream LLM response. Calls on_chunk(text_delta) for each received token chunk.
    Checks stop_check() before each chunk — if True, stops streaming early.
    Returns the full accumulated text.
    """
    if provider == "anthropic":
        import anthropic
        chosen_model = model or "claude-sonnet-4-6"
        _log.info("→ Anthropic stream  model=%s  max_tokens=%d  prompt_len=%d", chosen_model, max_tokens, len(prompt))
        client = anthropic.Anthropic(api_key=api_key)
        full_text: list = []
        with client.messages.stream(
            model=chosen_model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                if stop_check and stop_check():
                    _log.info("stream_llm: stopped early by stop_check")
                    break
                full_text.append(text)
                if on_chunk:
                    on_chunk(text)
        result = "".join(full_text)
        _log.info("← Anthropic stream  len=%d", len(result))
        return result

    elif provider == "openai":
        from openai import OpenAI
        chosen_model = model or "gpt-4o"
        _log.info("→ OpenAI stream  model=%s  max_tokens=%d  prompt_len=%d", chosen_model, max_tokens, len(prompt))
        client = OpenAI(api_key=api_key)
        full_text: list = []
        stream_resp = client.chat.completions.create(
            model=chosen_model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
            stream=True,
        )
        for chunk in stream_resp:
            if stop_check and stop_check():
                _log.info("stream_llm: stopped early by stop_check")
                break
            delta = chunk.choices[0].delta.content
            if delta:
                full_text.append(delta)
                if on_chunk:
                    on_chunk(delta)
        result = "".join(full_text)
        _log.info("← OpenAI stream  len=%d", len(result))
        return result

    else:
        raise ValueError(f"Unknown LLM provider: {provider!r}")
