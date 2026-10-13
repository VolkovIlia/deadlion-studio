# Composition patterns

How separate programs talk. Pick one per edge in `system.md`; name it on the edge.
Every pattern keeps the suckless rule that each part is small enough to read in
one sitting and is built, tested and released alone
([philosophy](https://suckless.org/philosophy/), [sucks](https://suckless.org/sucks/)).

## 1. Pipe: line or JSONL stream
- **When:** data flows one way, producer and consumer can run as one shell line,
  each record is independent.
- **Interface:** stdin/stdout, one record per line (TSV or JSON Lines), exit code
  for success, diagnostics on stderr. Header-less; field order fixed by the contract.
- **Example:** `sbase`/coreutils filters; `curl -s URL | parse | dedupe > items.jsonl`.
  <https://core.suckless.org/sbase/>
- **Separate builds:** each stage is its own binary with its own `make test` that
  feeds a fixture file on stdin and compares stdout byte for byte.
- **Wrong when:** a stage needs to answer back (two-way dialogue), or needs global
  state across records (then put that state in a file, pattern 2).

## 2. Filesystem and FIFO as the API
- **When:** long-lived state that several tools or a human inspect and change;
  event streams that are appended to and tailed.
- **Interface:** a directory tree. Read state with `cat`, act by writing a line into
  a FIFO or a file, watch with `tail -f`. `ii` creates one directory per server,
  channel and nick, each with an `in` FIFO and an `out` file
  (<https://git.suckless.org/ii/file/README.html>). `mblaze` keeps mail in Maildir
  and passes message paths line by line between `mlist`, `mpick`, `mseq`, `mshow`
  (<https://github.com/leahneukirchen/mblaze>).
- **Separate builds:** the daemon owning the tree is one project; every reader or
  writer is another, tested against a fixture directory.
- **Wrong when:** writers race on the same file without a single owner, or
  consumers need transactions across many files (use one owner process + pattern 8).

## 3. Exec chain (chain loading)
- **When:** a process must be set up in steps (privileges, limits, environment,
  working directory, file descriptors) before the real program runs.
- **Interface:** argv. Each program does one change to its own process state, then
  `exec`s into the rest of its command line. execline scripts are a single argv
  ([grammar](https://skarnet.org/software/execline/grammar.html)); daemontools
  uses `setuidgid`, `envdir`, `softlimit` the same way
  (<https://cr.yp.to/daemontools.html>).
- **Separate builds:** each link is a tiny binary with its own test: run it with
  `env` or `id` as the tail and assert the changed state.
- **Wrong when:** a link needs to run code after the tail starts (it cannot, it was
  replaced), or links must share data other than environment, fds and argv.

## 4. Privilege-separated pipeline
- **When:** untrusted input (network, user files) meets privileged state (queue,
  mailbox, keys).
- **Interface:** small programs under different uids, connected by pipes or a
  queue directory with a fixed file format. qmail splits SMTP receipt, queueing,
  scheduling and delivery into mutually distrustful programs, each with the least
  privilege it needs ([qmail security, Bernstein 2007](https://cr.yp.to/qmail/qmailsec-20071101.pdf)).
  s6 supervises each such service with its own process and log
  (<https://skarnet.org/software/s6/why.html>).
- **Separate builds:** one project per trust level; tests feed hostile fixtures to
  the untrusted side and assert it never touches privileged paths.
- **Wrong when:** every stage runs as the same user anyway; then use pattern 1.

## 5. Plumbing and porcelain
- **When:** a system needs both a stable scriptable core and a friendly UI.
- **Interface:** plumbing commands with machine-readable, versioned output
  (`git cat-file`, `git rev-list`, `git update-ref`); porcelain commands built only
  on plumbing output (<https://git-scm.com/docs/git>, "Low-level commands" vs
  "High-level commands").
- **Separate builds:** plumbing is one project with exact-output tests; porcelain is
  another (often sh) whose tests run against the plumbing binaries.
- **Wrong when:** the porcelain reaches into plumbing internals instead of its
  output, or plumbing output changes without a contract version bump.

## 6. One binary per command over a tiny shared library
- **When:** a family of related commands share helpers (option parsing, UTF-8,
  error reporting) but nothing else.
- **Interface:** each command is a standalone binary; the shared code is a static
  library of ≤300 SLOC with no state. sbase builds every utility from one `.c` file
  plus `libutil`/`libutf` (<https://core.suckless.org/sbase/>).
- **Separate builds:** `projects/lib<name>/` builds the static library and tests it;
  each command project links it and tests its own binary.
- **Wrong when:** the library grows policy, configuration or global state, or a
  change in it forces every command to change: that is a framework.

## 7. Protocol embedding
- **When:** a container program manages windows or sessions of other independent
  programs.
- **Interface:** an existing protocol, not a plugin API. `tabbed` hosts any XEmbed
  client and passes its window id on the client's command line
  (`tabbed surf -e`; <https://tools.suckless.org/tabbed/>).
- **Separate builds:** container and clients are unrelated projects; tests start the
  container with a trivial client.
- **Wrong when:** container and client exchange anything beyond the protocol
  (shared config files, private messages).

## 8. Front end / back end over a socket
- **When:** a long-running engine holds state; several thin UIs (CLI, TUI, web)
  drive it. TAOUP's Rule of Separation: separate interfaces from engines
  (<http://www.catb.org/esr/writings/taoup/html/ch01s06.html>, §1.6.4).
- **Interface:** a line-based text protocol over a Unix socket (TCP only when the
  boundary is a network): one request line, response lines, a terminating
  `OK`/`ERR <reason>` line. mpd and its clients (`mpc`, `ncmpc`) work this way.
- **Separate builds:** the back end has protocol tests driven through `socat` or
  `nc -U`; each front end tests against a fake back end that replays the
  contract example.
- **Wrong when:** only one client will ever exist and the engine has no state
  between runs; then a pipe (pattern 1) is enough.

## 9. File server (Plan 9 / 9P)
- **When:** a service's state and controls map naturally onto files and every
  client already speaks files.
- **Interface:** a synthetic file tree: `ctl` files take text commands, data files
  read and write content, `event` files stream changes. Plan 9 serves the network,
  windows and editors (`/net`, rio, acme) this way
  (<https://en.wikipedia.org/wiki/9P_(protocol)>). On Unix: plan9port, FUSE, or a
  plain directory (pattern 2) when no synthesis is needed.
- **Separate builds:** the server is one project tested by mounting it and running
  `cat`/`echo`; clients are sh scripts with their own tests.
- **Wrong when:** no client uses the files directly; then a socket protocol
  (pattern 8) is simpler.

## General rules
- **Adapters.** Each external system (API, DB, queue, filesystem layout) sits behind
  one narrow adapter that translates it to the internal text format. One adapter
  per resource; swapping it must not change the core.
- **Message passing.** Programs talk only through explicit messages (requests,
  responses, events, files): no shared mutable state, no reaching into another
  program's storage. Every flow appears in the Composition diagram.
- **Pipelines over orchestrators.** `a | b | c` where each stage is restartable from
  its input file beats a central controller that knows every step.
- **Contract first.** The `contracts/<name>.md` file is written before any
  implementation and is what tests assert against.
- **Plain text and small code** are the defaults, not goals to trade for features
  ([coding style](https://suckless.org/coding_style/)).
