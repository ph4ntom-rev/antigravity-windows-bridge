# Security model

The bridge runs as the current Windows user. HTTP binds only to 127.0.0.1;
every endpoint requires a bearer token. The server rejects unexpected Host
headers and browser origins, duplicate authorization/content-length fields,
ambiguous JSON, oversized bodies, and chunked requests. It allows at most 16
simultaneous HTTP workers with a five-second socket timeout. This socket timeout
does not cancel an already-running Windows API call.

The normal token and the extension token are independent 256-bit session
secrets. Token files are written only after binding succeeds, using owner-only
DACLs on Windows. Restarting the server rotates them. The extension token can
only poll commands, report results, and query extension status. Pair only a
trusted extension; it can observe browser commands and supply their results.

REST and stdio MCP dispatch through the same capability and target policy.
Only `read` is enabled by default. Do not run the bridge as administrator unless
a specific operation requires it. Explicit process IDs are session targets;
Windows can reuse a PID after a process exits. Restart/reconfigure the bridge
when the target exits. Registry permissions apply to the configured subtree,
not similarly prefixed sibling keys. Registry links and other OS-level aliases
remain within the trust boundary of the local machine.

Enabling `exec` grants arbitrary local code execution as the bridge user.
Scripts run in a child interpreter with a ten-second deadline, a 256 KiB output
limit, and a Windows Job Object that kills descendants on close and limits each
process to 256 MiB. This is **not a sandbox**: scripts can access files, network,
and OS capabilities available to the account. The capability/target allowlists
do not constrain a script that was explicitly authorized to execute.

Browser JavaScript, input synthesis and UI actions can cause application-level
mutations. They require separate opt-in capabilities. They cannot be rolled
back reliably. An extension timeout can mean a command executed but its result
was lost; never automatically retry a mutation on that basis. Commands include
an expiry checked before execution, and expired/unknown results are rejected.

Audit events record handler name, capability and outcome, never scripts,
request bodies, query strings or tokens. HTTP rejects requests before dispatch
without logging their contents. Protect logs as operational data.

Report vulnerabilities using GitHub private vulnerability reporting when
available. Do not put tokens, personal screenshots or process-memory dumps in
public issues.
