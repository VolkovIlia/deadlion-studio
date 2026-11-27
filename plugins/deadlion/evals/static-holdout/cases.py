"""Workload labels describe avoidable work under the type and ownership contracts."""
import json


def permissions(users, allowed: list):
    result = []
    for user in users:
        result.append(user in allowed)  # positive: repeated membership in a large list
    return result


def indexed(users, allowed: set):
    result = []
    for user in users:
        result.append(user in allowed)  # negative: prebuilt hash index
    return result


def comprehension(users, allowed: list):
    return [user in allowed for user in users]  # positive: same cost in comprehension


def ordered_batches(keys, batches):
    result = []
    for batch in batches:
        result.append((batch, sorted(keys)))  # positive: immutable integer tuple, read-only consumers
    return result


def local_orders(batches):
    result = []
    for batch in batches:
        result.append(sorted(batch))  # negative: each independent input needs its own ordering
    return result


def encode_config(config, recipients):
    for recipient in recipients:
        yield recipient, json.dumps(config)  # positive: unchanged plain JSON tree


def encode_messages(messages):
    for message in messages:
        yield json.dumps(message)  # negative: each payload is distinct


def query_users(db, ids):
    for user in ids:
        yield db.execute("SELECT name FROM users WHERE id=?", (user,)).fetchone()  # positive: batchable query


def independent_snapshots(buf, changes):
    for change in changes:
        buf.update(change)
        yield buf.copy()  # negative: downstream retains each independent snapshot


def redundant_copy(buf, queries):
    for key in queries:
        yield buf.copy().get(key)  # positive: read-only dictionary lookup
