import re


class InputValidator:
    def __init__(self):
        self.dangerous_patterns = [
            r'ignore.*instruction',
            r'forget.*rule',
            r'bypass.*security',
            r'show.*secret',
            r'admin.*mode',
            r'system.*prompt',
            r'jailbreak',
            r'reveal.*password',
            r'override',
        ]
        self.max_length = 500

    def validate(self, query: str) -> tuple[bool, str]:
        if len(query) > self.max_length:
            return False, f"Query exceeds {self.max_length} chars"

        query_normalized = query.encode('utf-8', 'ignore').decode('utf-8')
        query_normalized = re.sub(r'[\x00-\x1F\x7F]', '', query_normalized)

        for pattern in self.dangerous_patterns:
            if re.search(pattern, query.lower(), re.IGNORECASE):
                return False, f"Blocked by regex: '{pattern}'"

        return True, query_normalized
