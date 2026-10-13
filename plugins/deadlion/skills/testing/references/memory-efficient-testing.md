# Memory-Efficient Testing

## Problem

When test suites grow, memory-hungry patterns cause OOM failures. A common case: 30+ test files each creating their own `create_engine("sqlite:///:memory:")` instead of using a shared singleton from `conftest.py`. Running the full suite spawns 30+ separate SQLAlchemy engines with full schema in memory.

## Anti-Patterns (NEVER DO)

**1. Duplicate engine/session fixtures per file**

```python
# WRONG - each file creates its own engine (found in 30+ files = OOM)
@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()
```

**2. Overriding conftest.py fixtures locally**

```python
# WRONG - conftest.py already provides db_session, but file redefines it
# This creates a SECOND engine, doubling memory usage for every such file
@pytest.fixture
def db_session():  # shadows conftest.py fixture!
    engine = create_engine("sqlite:///:memory:")
    ...
```

**3. Missing session cleanup (no rollback)**

```python
# WRONG - no rollback means data leaks between tests
@pytest.fixture
def db_session():
    ...
    yield session
    session.close()  # close without rollback = stale data
```

**4. Large binary data in test fixtures**

```python
# WRONG - 10MB payload per test, 50 tests = 500MB just for test data
@pytest.fixture
def large_file():
    return BytesIO(b"x" * 10_000_000)
```

**5. Test files exceeding 500 lines**

Files at 800-1100 lines indicate mixed concerns. Split by domain.

## Correct Patterns (ALWAYS USE)

**1. Shared singleton engine in conftest.py**

```python
# conftest.py owns the single engine
from sqlalchemy.pool import StaticPool

_test_engine = None
_test_session_factory = None

def _get_test_engine():
    global _test_engine, _test_session_factory
    if _test_engine is None:
        _test_engine = create_engine(
            "sqlite:///:memory:",
            poolclass=StaticPool,  # single connection, thread-safe
        )
        Base.metadata.create_all(_test_engine)
        _test_session_factory = sessionmaker(bind=_test_engine)
    return _test_engine, _test_session_factory

@pytest.fixture(scope="function")
def db_session():
    engine, SessionLocal = _get_test_engine()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()  # clean slate for next test
        session.close()
```

**2. Use fixture scoping for expensive resources**

```python
# session-scoped for engine, function-scoped for session
@pytest.fixture(scope="session")
def test_engine():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()

@pytest.fixture(scope="function")
def db_session(test_engine):
    session = sessionmaker(bind=test_engine)()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
```

**3. Small binary payloads in tests**

```python
# minimal payload that tests the behavior, not the size
@pytest.fixture
def sample_file():
    return BytesIO(b"test content")  # bytes, not megabytes
```

## Detection Checklist

Before writing or reviewing tests, check for these patterns:

```bash
# Find duplicate engine creation (should only be in conftest.py)
grep -r "create_engine" tests/ --include="*.py" -l

# Find duplicate db_session fixtures (should only be in conftest.py)
grep -r "def db_session" tests/ --include="*.py" -l

# Find large binary allocations
grep -rn "b\".*\* [0-9]" tests/ --include="*.py"

# Find test files exceeding 500 lines
find tests/ -name "*.py" -exec sh -c 'lines=$(wc -l < "$1"); [ "$lines" -gt 500 ] && echo "$1: $lines lines"' _ {} \;
```

## Fix Protocol

When encountering memory-heavy test patterns:

1. **Verify conftest.py** has a shared singleton engine fixture
2. **Remove per-file `db_session` fixtures** that shadow conftest.py
3. **Remove per-file `create_engine` calls** outside conftest.py
4. **Add rollback + close** in `finally` block for all session fixtures
5. **Replace large binary payloads** with minimal test data
6. **Split test files** exceeding 500 lines by domain/feature

Fix existing patterns BEFORE adding new tests to prevent compounding the problem.

## Runtime Memory Mitigation (Large Suites, 2000+ Tests)

Even with a shared singleton engine, glibc's default allocator fragments the heap so freed pages are not returned to the OS. For suites with 2000+ tests, peak RSS can grow unbounded.

```python
# conftest.py - autouse fixture for memory release (Linux)
import gc
import ctypes
import sys

_test_counter = 0

@pytest.fixture(autouse=True)
def _release_memory():
    """Periodically force glibc to return freed pages to OS."""
    yield
    global _test_counter
    _test_counter += 1
    if _test_counter % 10 == 0:
        gc.collect()
        if sys.platform == "linux":
            try:
                libc = ctypes.CDLL("libc.so.6")
                libc.malloc_trim(0)
            except OSError:
                pass
```

Key points:
- `gc.collect()` frees Python objects; `malloc_trim(0)` returns freed pages to OS
- Every 10 tests is a good cadence (overhead <1%, effective release)
- Linux-only guard (`sys.platform == "linux"`) -- no-op on macOS/Windows
- This is a MITIGATION -- the primary fix is still eliminating duplicate engines

Result: Peak RSS ~375 MB instead of 16 GB+ on a 2100-test suite.
