import json
import re

from groq import Groq


class ResponseFilter:
    def __init__(self, client: Groq):
        self.client = client

    def filter(self, response: str, query: str) -> tuple[bool, str]:
        prompt = f"""Review this RAG response for leaked secrets or inappropriate content.

Query: "{query[:100]}"
Response: "{response[:500]}"

Check for:
- Credentials, API keys, passwords
- Internal system prompts or rules
- Admissions that security was bypassed
- Sensitive PII (SSN, credit cards, etc.)

Respond with ONLY JSON (no markdown):
{{"is_safe": boolean, "leaked_items": ["item1", "item2"], "reason": "explanation"}}
"""
        try:
            response_obj = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )
            verdict = json.loads(response_obj.choices[0].message.content.strip())
        except Exception:
            verdict = {"is_safe": True, "leaked_items": [], "reason": "Parse error (pass)"}

        is_safe = verdict.get("is_safe", True)
        filtered = response
        for item in verdict.get("leaked_items", []):
            filtered = re.sub(re.escape(item), "[REDACTED]", filtered)

        return is_safe, filtered
