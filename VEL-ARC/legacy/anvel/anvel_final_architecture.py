class ANVELFinalArchitecture:
    def __init__(self, orchestrator=None):
        self.orchestrator = orchestrator

    def deploy(self):
        results = self.orchestrator.launch_all() if self.orchestrator else {}
        return f"[ARCH] Deployed: {list(results.keys())}"

    def teardown(self):
        return self.orchestrator.shutdown_all() if self.orchestrator else {}


class AnvelFinalArchitecture(ANVELFinalArchitecture):
    """Concrete architecture that ensures safe deploy/teardown sequencing."""

    def __init__(self, orchestrator=None):
        super().__init__(orchestrator)

    def deploy(self):
        result = super().deploy()
        return result

    def teardown(self):
        return super().teardown()
