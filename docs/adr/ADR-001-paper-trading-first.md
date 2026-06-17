# ADR-001: Paper Trading First

## Status

Accepted

## Decision

SilverPilot starts as a paper-trading simulator only. It does not place real bank orders, automate bank accounts, or execute real-money trades in v1.

## Consequences

All trading behavior is simulated through explicit domain models, testable cost assumptions, and account-bound execution context.
