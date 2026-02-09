class ANVELSystemValidator:
    def __init__(self, validation_matrix=None):
        self.validation_matrix = validation_matrix

    def validate_all(self, state):
        return (
            {k: self.validation_matrix.validate(k, v) for k, v in state.items()}
            if self.validation_matrix
            else {}
        )

    def report(self):
        return self.validation_matrix.recent(5) if self.validation_matrix else []
