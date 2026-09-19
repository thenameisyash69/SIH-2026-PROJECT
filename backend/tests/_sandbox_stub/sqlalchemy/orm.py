"""Fake sqlalchemy.orm — see README.md in the parent directory."""
import types


class Session:
    """Placeholder — only used as a type hint in real code, never
    instantiated directly (sessionmaker() below returns FakeSession)."""
    pass


def relationship(*a, **kw):
    return None


class _Metadata:
    def create_all(self, bind=None):
        pass


_STORE = {}   # module-level shared in-memory "database", keyed by model class name


def _reset_store():
    _STORE.clear()


class FakeQuery:
    def __init__(self, rows):
        self.rows = list(rows)

    def filter(self, *exprs):
        rows = self.rows
        for e in exprs:
            rows = [r for r in rows if e.matches(r)]
        return FakeQuery(rows)

    def order_by(self, sort_spec):
        self.rows = sorted(
            self.rows,
            key=lambda r: (getattr(r, sort_spec.name, None) is None, getattr(r, sort_spec.name, None)),
            reverse=not sort_spec.ascending,
        )
        return self

    def all(self):
        return list(self.rows)

    def first(self):
        return self.rows[0] if self.rows else None

    def count(self):
        return len(self.rows)

    def limit(self, n):
        return FakeQuery(self.rows[:n])

    def scalar(self):
        return len(self.rows) if self.rows else None


class FakeSession:
    def query(self, model):
        table = _STORE.setdefault(model.__name__, [])
        return FakeQuery(table)

    def add(self, obj):
        table = _STORE.setdefault(type(obj).__name__, [])
        if getattr(obj, "id", None) is None:
            obj.id = len(table) + 1
        table.append(obj)

    def flush(self):
        pass

    def commit(self):
        pass

    def refresh(self, obj):
        pass

    def close(self):
        pass


def sessionmaker(*a, **kw):
    return lambda: FakeSession()


def declarative_base():
    class DeclarativeBase:
        metadata = _Metadata()

        def __init_subclass__(cls, **kwargs):
            super().__init_subclass__(**kwargs)
            cols = {}
            for base in reversed(cls.__mro__):
                for k, v in vars(base).items():
                    if isinstance(v, __import__("sqlalchemy").Column):
                        cols[k] = v
            cls._columns = cols

        def __init__(self, **kwargs):
            for name, col in type(self)._columns.items():
                if name in kwargs:
                    setattr(self, name, kwargs[name])
                else:
                    default = col.default
                    setattr(self, name, default() if callable(default) else default)

    return DeclarativeBase
