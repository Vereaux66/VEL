class ANVELIncidentResponse:
    def __init__(self, protocol=None):
        self.protocol = protocol
        self.log = []

    def respond(self, incident):
        if self.protocol:
            steps = self.protocol.run("incident_protocol")
            self.log.append((incident, steps))
            return f"[INCIDENT] Steps: {steps}"
        return "[INCIDENT] No protocol"
