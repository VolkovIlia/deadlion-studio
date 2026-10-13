# Anti-cheat: tricks that game the limits

Code that fits the numbers by compression is rejected. Each pattern below is a violation
even when `dl-size` is silent. Report as `BLOCKING path:line — <pattern> — <evidence>`.

## 1. Line cramming
Multiple statements per line.
```python
x=d['a'];y=d['b'];z=x+y;return{'r':z}        # bad
```
Detect: `;` separating statements (outside strings and C-style `for` headers).
Fix: one statement per line; extract a function if it no longer fits.

## 2. Cryptic names
```python
def calc(np, nu, ts): pn = np.pref_name        # bad
def format_recipient(preference, user, fmt):   # good
```
Detect: 1–2 character names, except `i j k` loop indices, `e` for exceptions, `_` for unused.

## 3. Deleted WHY-comments
```python
# Prevent algorithm substitution attacks (CVE-2015-9235)
if header["alg"] not in ALLOWED_ALGORITHMS:
    return False
```
Detect: comments removed in the diff, especially security rationale, business rules,
TODO/FIXME with tracking info, references to CVEs, RFCs or tickets.

## 4. Whitespace elimination
Detect: a function with >15 consecutive non-blank lines (missing logical groupings).
Fix: blank lines between phases (validate / build / compute / persist), or extract phases.

## 5. Obscure one-liners
```python
return [u for u in users if u.role=='admin' and u.active and u.verified and not u.banned]
```
Detect: a comprehension with >3 conditions (`and`, `or`, `if` inside `[]`, `{}`, `()`).
Fix: a loop with guard `continue`s or named predicate helpers.

## 6. Nested ternaries
```python
return 0.3 if t == 'gold' else 0.2 if t == 'silver' else 0.1 if t == 'bronze' else 0   # bad
TIER_DISCOUNTS = {'gold': 0.3, 'silver': 0.2, 'bronze': 0.1}                           # good
return TIER_DISCOUNTS.get(t, 0)
```
Detect: more than one ternary on a line.

## Correct refactoring techniques
1. Extract method — move a logical section into a named function.
2. Table-driven dispatch — replace if/elif chains with lookup tables.
3. Early returns — guard clauses instead of nesting.
4. Split modules — separate concerns into different files.

## Quality gates after a refactor
- Cyclomatic complexity per function ≤10 and not higher than before (`radon cc -s FILE` for Python, `lizard` otherwise).
- Cognitive complexity per function ≤15 (nesting is penalised; early returns help).
- Readability: each function is understandable without scrolling, its name says what it
  does, the top-level function reads like a table of contents, and each logical step can
  take a breakpoint.

If complexity rose or any pattern above appears, the refactor is rejected even when the
line counts went down.
