class ANVELSequenceEngine:
    def __init__(self):
        self.steps = []
        self.ptr = 0

    def add_step(self, instr):
        self.steps.append(instr)
        return f"[SEQUENCE] Added: {instr}"

    def next(self):
        if self.ptr >= len(self.steps):
            return "[SEQUENCE] End"
        s = self.steps[self.ptr]
        self.ptr += 1
        return f"[SEQUENCE] Step{self.ptr}: {s}"

    def rewind(self):
        self.ptr = 0
        return "[SEQUENCE] Reset"
