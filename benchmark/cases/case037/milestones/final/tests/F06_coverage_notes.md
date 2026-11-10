# feature: F06

# Rekey timeout-scope repair

This is an in-place repair of
`F06_transport.py::test_rekey_limits_and_data_survival`, not a new collected
case. The requirement is Full_PRD.md:123; the public setting and failure
carriers are Interface_Contract.md:201, :219 and :267.

The historical F06 failure cancelled `independent_selection` readiness through
an outer 30-second deadline shared by sequential observations. The helper's
own readiness bound is 15 seconds. The historical ALL run passed 129 cases.
The pre-edit targeted rerun passed in 15.90 seconds, so the historical startup
latency and failure reproducibility remain unverified. The evidence supports
repairing cumulative deadline scope, not a product or import defect.

Each independent exchange or initial-setting check now starts a separate
`run_async` scope. Its setup, observation and context-manager cleanup are
inside its finite budget. The OpenSSH scope allows its existing 20-second
exchange bound plus 10 seconds of local setup, scheduling and cleanup reserve.
The independent-client scopes allow their existing 30-second bound plus the
same reserve. These helper bounds already include their 1.2-second observation.
The client-role scope allows 15 seconds for readiness, 10 for connection/session
setup, 1.3 for observation, 10 for channel communication, 20 for peer completion,
and 10 for local setup, scheduling and cleanup. Initial-setting scopes allow
10 seconds plus 10 seconds reserve. Established keepalive policy allows another
10 seconds for its checked exchange. No fixed outer deadline spans the
independent measurements.

Rejected updates, disabling keepalive, and the subsequent exchange retain the
same established connection: this stateful sequence has its own bounded scope.
`F06_helpers.py`, `F06_peer.py` and `_helpers.py` are unchanged. In particular,
readiness and exchange bounds, exception causes and diagnostics, and child
process termination/reaping are preserved. A real readiness failure remains a
failed prerequisite; dependent behavior is unobserved, not passed.

All rows below remain in the same collected test identity:

| Capability | Existing measurement and oracle retained |
| --- | --- |
| OpenSSH channel survival | Three exchanges: traffic threshold, positive time, zero time; renewal count plus exact binary output in `openssh_exchange` |
| Selected outgoing byte boundary | One `independent_exchange` measurement and `assert_rekey_boundary`; packet-length boundary and product-initiated ordering, with random binary data checked by the peer |
| Server time policy | Positive and zero intervals; renewal presence, first interval at least 0.95 seconds, no renewal when disabled, and independent peer data-integrity checks |
| Client time policy | Positive and zero intervals; independent server observations, the same first-interval lower bound and no-renewal oracle, and exact channel output |
| Invalid server settings | All six original initial settings still raise `ValueError`: zero/negative traffic, negative time/keepalive interval, negative/zero initial allowance |
| Invalid client settings | The same six original initial settings still raise `ValueError` |
| Established keepalive policy | Both original invalid updates raise `ValueError`; disabling keepalive and checked binary exchange remain on that same connection |

The seven direct behavioral assertions, six measurement call sites and all
refusal/keepalive calls compare identically as syntax trees. Only the scenario's
completion-string equality was removed; it did not measure product behavior.
No measurement was added or duplicated. Actual before/after/final collection
has the same 129 node identities in the same order (19 in F06). The collected
test function name is unchanged. Other F06 behavior and other features were
not expanded or consolidated.

Final verification uses the unmodified neutral reference via the prescribed
casebox test entry: offline, as the judge user, with read-only product/tests.
F06 passed 19 tests in 3820.07 seconds; ALL passed 129 in 3992.28 seconds.
A repeat with isolated host temporary/cache directories passed F06 in 3793.74
seconds and ALL in 3972.73 seconds; the final targeted node passed in 13.73
seconds. The one-hour default observation was actually executed. These passes
are not evidence of timing stability or a latency distribution.

Seven mutations of temporary product copies were actually rejected by the
retained assertions: missing traffic renewal, premature traffic renewal,
missing server-role time renewal, missing client-role time renewal, premature
time renewal, renewal despite zero time, and corrupted channel bytes. The
precise mutations, failures, commands, collection comparison and raw runtimes
are retained under `milestones/v2/repair/hand_tests_P001/`, including
`mutation-results.json`, `assertion-comparison.json`, `collection-comparison.json`,
`run-results.json`, `commands.txt` and the raw logs. The baseline was never
modified. These are real protocol/data observations, not product-reported
success counters or mocked behavior.

Two cache-staging infrastructure errors are retained separately and were not
counted as behavioral results; retries used separate host temporary directories
without changing container conditions or Pipeline code. The unsuccessful
preparatory mutation attempt is also retained and explicitly excluded from
mutation evidence. Full-suite warnings remain visible in the raw logs.

Coverage-honesty audit: every item in this repair's PLAN.md inventory maps to a
row above and the existing test reference; no planned capability is omitted.
Startup-latency distribution, repeated-failure probability and long-term timing
stability are unmeasured (outside this scope); no claim relies on them.
Unrelated capabilities and unrelated scenario deadlines were not redesigned
(out of scope). Harness tampering/isolation remains the existing runner's
responsibility, not a new product assertion. The requested unified `(none)`
ledger directory is outside this task's writable paths, so this ledger is
recorded in the live feature-owned tests directory instead.
