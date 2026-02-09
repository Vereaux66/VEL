class ANVELOntologyManager:
    def __init__(self, mindnet=None):
        self.hierarchy = {}
        self.mindnet = mindnet

    def add_concept(self, parent, child):
        self.hierarchy.setdefault(parent, []).append(child)
        if self.mindnet:
            self.mindnet.link(parent, child, "subclass")
        return f"[ONTOLOGY] Added '{child}' under '{parent}'"

    def get_children(self, concept):
        return self.hierarchy.get(concept, [])

    def traverse(self, root):
        result = []

        def dfs(node):
            for child in self.hierarchy.get(node, []):
                result.append(child)
                dfs(child)

        dfs(root)
        return result
