Return one complete Python 3 module as plain source. Use only the standard library. No network services or subagents. Implement all seven independent functions.

* stable_sum(xs) returns an accurate float sum for finite IEEE double inputs with cancellation. The exact sum and intermediate partial sums fit in double.
* distances(edges, start) returns a dict of minimum unweighted directed hop counts for reachable integer vertices, including start. Edges may repeat and the graph may contain cycles.
* parse_rows(lines) yields each CSV row as a tuple of strings. Input is an iterator of physical text lines. Support quoted commas, double quotes and embedded newlines. Be lazy.
* parallel_map(fn, xs, workers) yields results in input order, with at most workers outstanding calls. xs can be infinite. fn is I/O bound. Propagate errors and release executor resources on close.
* count_bytes(stream, needle) returns occurrences of one integer byte in a binary stream without seeking. Handle short reads; never request more than 65536 bytes.
* read_frame(sock, limit) reads a 4-byte unsigned big-endian length followed by exactly that many bytes from a connected blocking socket. Avoid overreading the next frame, raise EOFError on truncation and ValueError for a length above limit before allocating payload.
* totals(conn) returns a dict mapping each integer account id to the sum of its transactions, including zero for accounts without transactions. SQLite schema: accounts(id INTEGER PRIMARY KEY), tx(account_id INTEGER, amount INTEGER). Use one SQL statement.
