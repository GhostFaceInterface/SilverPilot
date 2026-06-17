# ADR-003: Decimal/Numeric For Money And Quantity

## Status

Accepted

## Decision

Python code uses `Decimal` for money, prices, and quantities. Future PostgreSQL schemas use fixed-precision `numeric` columns.

## Consequences

Float arithmetic is not allowed in financial value models. Tests must cover Decimal construction and float rejection.
