class ANVELGeolocationCore:
    def __init__(self):
        self.positions = {}

    def update_position(self, entity, coords):
        self.positions[entity] = coords
        return f"[GEO] {entity}: {coords}"

    def locate(self, entity):
        return self.positions.get(entity, "[GEO] Unknown")

    def nearby(self, entity, radius):
        base = self.positions.get(entity)
        if not base:
            return []
        x0, y0 = base
        return [
            e
            for e, (x, y) in self.positions.items()
            if (x - x0) ** 2 + (y - y0) ** 2 <= radius**2
        ]
