# ADR-005: Account-Bound Execution, No Best-Bank Routing

## Status

Accepted

## Decision

Each `VirtualAccount` is bound to its own execution venue or bank. SilverPilot does not route an account's trade to another bank because that bank has a better spread.

## Consequences

Other bank prices may be used for benchmark reporting, but they are not execution candidates for a bound account. Cross-bank transfer simulation is out of scope for v1.
