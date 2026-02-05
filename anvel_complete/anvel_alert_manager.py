class ANVELAlertManager:
    def __init__(self, mesh=None):
        self.mesh = mesh
        if mesh:
            mesh.bind("threat", self._handle_threat)
        self.alerts = []

    def _handle_threat(self, payload):
        self.alerts.append(payload)
        return f"[ALERT] Handled: {payload}"

    def recent_alerts(self, limit=5):
        return self.alerts[-limit:]
