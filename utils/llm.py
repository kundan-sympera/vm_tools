import json
import os

from openai import OpenAI


def get_deepseek_response(system_prompt: str, user_prompt: str, model: str = None, temperature: float = 0) -> str:
    try:
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise RuntimeError("DEEPSEEK_API_KEY not found in environment")

        base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        if model is None:
            model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

        client = OpenAI(api_key=api_key, base_url=base_url)

        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=temperature,
        )
        return completion.choices[0].message.content

    except Exception as e:
        print(f"[LLM] Error: {e}")
        return ""


def parse_llm_response(content: str) -> dict | str:
    if not content:
        print("[LLM] parse_llm_response received empty string (LLM call likely failed)")
        return {}

    start = content.find("{")
    end   = content.rfind("}") + 1

    if start == -1 or end == 0:
        print(f"[LLM] No JSON object found in response, raw: {content[:200]}")
        return {}

    json_string = content[start:end]

    if json_string.startswith("{{") and json_string.endswith("}}"):
        json_string = json_string[1:-1]

    try:
        parsed = json.loads(json_string)
        return parsed
    except json.JSONDecodeError:
        print(f"[LLM] JSON parse failed, raw: {content[:200]}")
        return {}
