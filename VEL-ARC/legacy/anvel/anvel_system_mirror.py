class ANVELSystemMirror:
    def __init__(self):
        self.snaps = []

    def capture(self, ctx):
        snap = {k: v for k, v in ctx.items() if not k.startswith("_")}
        self.snaps.append(snap)
        return f"[MIRROR] keys:{len(snap)}"

    def compare(self, key, val):
        return next((s for s in self.snaps if s.get(key) == val), "[MIRROR]No match")
