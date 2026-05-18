# utils/memory.py: Per-channel conversation memory and summarization.
# This module manages a short-term memory buffer for each channel, storing recent messages and their roles (user/model).

import asyncio
import logging
from collections import deque
from typing import TYPE_CHECKING

from google.genai import types

logger = logging.getLogger("FreesonaBot")

MEMORY_LIMIT  = 5
SUMMARY_PROMPT = "Summarize this conversation in 2-3 sentences, keeping key context only:"

channel_memory:  dict[int, deque] = {}
channel_summary: dict[int, str]   = {}

def get_memory(channel_id: int) -> deque:
    if channel_id not in channel_memory:
        channel_memory[channel_id] = deque(maxlen=MEMORY_LIMIT)
    return channel_memory[channel_id]


def memory_to_contents(channel_id: int) -> list:
    contents = []
    summary = channel_summary.get(channel_id)

    if summary:
        contents.append(types.Content(
            role="user",
            parts=[types.Part(text=f"[Conversation summary so far: {summary}]")]
        ))
        contents.append(types.Content(
            role="model",
            parts=[types.Part(text="Understood, I have context from earlier.")]
        ))

    for entry in get_memory(channel_id):
        if contents and contents[-1].role == entry["role"]:
            contents[-1].parts[0].text += f"\n{entry['text']}"
        else:
            contents.append(types.Content(
                role=entry["role"],
                parts=[types.Part(text=entry["text"])]
            ))

    return contents


async def maybe_summarize(channel_id: int, client, model_name: str): # Only summarize if we have enough memory entries to warrant it
    mem = get_memory(channel_id)
    if len(mem) < MEMORY_LIMIT:
        return
    oldest = list(mem)[:MEMORY_LIMIT // 2]
    block = "\n".join(e["display"] for e in oldest)
    prompt = f"{SUMMARY_PROMPT}\n\n{block}"
    try:
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=model_name,
            contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
            config=types.GenerateContentConfig(max_output_tokens=200)
        )
        if response and response.text:
            prev = channel_summary.get(channel_id, "")
            channel_summary[channel_id] = (prev + " " + response.text.strip()).strip()
    except Exception as e:
        logger.warning(f"Summary failed: {e}")


def push_memory(channel_id: int, role: str, text: str, display: str = "", *, client=None, model_name: str = ""):
    if client and model_name:
        asyncio.create_task(maybe_summarize(channel_id, client, model_name))
    get_memory(channel_id).append({
        "role": role,
        "text": text,
        "display": display or text
    })