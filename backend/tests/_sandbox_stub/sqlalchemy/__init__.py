"""Minimal fake of the SQLAlchemy surface used by app/models.py — see README.md
in this directory. Not part of the shipped product."""


class _ColumnType:
    def __init__(self, *a, **kw): pass


Integer = _ColumnType
String = _ColumnType
Float = _ColumnType
Boolean = _ColumnType
DateTime = _ColumnType


class ForeignKey:
    def __init__(self, *a, **kw): pass


class FilterExpr:
    def __init__(self, name, op, value):
        self.name, self.op, self.value = name, op, value

    def matches(self, row):
        val = getattr(row, self.name, None)
        if self.op == "eq":
            return val == self.value
        if self.op == "ne":
            return val != self.value
        if self.op == "in":
            return val in self.value
        return False


class SortSpec:
    def __init__(self, name, ascending):
        self.name, self.ascending = name, ascending


class Column:
    """Doubles as both the class-level descriptor (for building filter
    expressions like Hotspot.category == 'x') and the default-value holder
    used by DeclarativeBase.__init__."""

    def __init__(self, *args, default=None, primary_key=False, nullable=True,
                 unique=False, index=False, onupdate=None, **kw):
        self.default = default
        self.name = None

    def __set_name__(self, owner, name):
        self.name = name

    def __eq__(self, other):
        return FilterExpr(self.name, "eq", other)

    def __ne__(self, other):
        return FilterExpr(self.name, "ne", other)

    def is_(self, other):
        return FilterExpr(self.name, "eq", other)

    def in_(self, other):
        return FilterExpr(self.name, "in", other)

    def asc(self):
        return SortSpec(self.name, True)

    def desc(self):
        return SortSpec(self.name, False)

    def __hash__(self):
        return id(self)


def create_engine(*a, **kw):
    return object()


class _FuncCount:
    """Extremely small stand-in for sqlalchemy.func — enough for the
    count()/max()/min() patterns used in stats.py/data_sources.py, which
    are NOT exercised by the pipeline dry-run but are imported transitively."""
    def count(self, *a, **kw):
        return ("count", a[0].name if a and hasattr(a[0], "name") else None)

    def max(self, *a, **kw):
        return ("max", a[0].name if a and hasattr(a[0], "name") else None)

    def min(self, *a, **kw):
        return ("min", a[0].name if a and hasattr(a[0], "name") else None)

    def distinct(self, *a, **kw):
        return ("distinct", a[0].name if a and hasattr(a[0], "name") else None)


func = _FuncCount()
