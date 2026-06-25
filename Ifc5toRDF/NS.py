from pyoxigraph import NamedNode


class NS:
    def __init__(self, base):
        self._base = base

    def __getitem__(self, local):
        return NamedNode(self._base + local)

    def __getattr__(self, local):
        if local.startswith("_"):
            raise AttributeError(local)
        return NamedNode(self._base + local)

    def __str__(self):
        return self._base