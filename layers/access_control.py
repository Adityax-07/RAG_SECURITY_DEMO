import re


class AccessControl:
    def __init__(self, user_role: str = "public"):
        self.user_role = user_role

    def can_access(self, allowed_roles: list[str]) -> bool:
        return self.user_role in allowed_roles

    def mask_sensitive(self, text: str) -> str:
        text = re.sub(r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b', '[CC_REDACTED]', text)
        text = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', '[SSN_REDACTED]', text)
        text = re.sub(
            r'(api[_-]?key|secret)[:\s]*[a-zA-Z0-9\-_.]{20,}',
            r'\1: [KEY_REDACTED]',
            text,
            flags=re.IGNORECASE,
        )
        return text
