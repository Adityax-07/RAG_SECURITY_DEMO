from datetime import datetime


class AuditLogger:
    def __init__(self):
        self.incidents: list[dict] = []

    def log_incident(self, query: str, reason: str, layer: str):
        self.incidents.append({
            "timestamp": datetime.now().isoformat(),
            "query": query[:80],
            "reason": reason,
            "layer": layer,
        })

    def get_incidents(self) -> list[dict]:
        return self.incidents[-10:]
