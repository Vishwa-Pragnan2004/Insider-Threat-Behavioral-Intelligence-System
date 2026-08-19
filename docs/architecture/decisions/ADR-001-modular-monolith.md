# ADR-001 — Modular Monolith Architecture

**Status:** Accepted  
**Date:** 2026-08-19  
**Deciders:** Engineering Team

## Context

ITBIS is a complex platform with 14 distinct functional modules. We need to choose between:
1. Full microservices from day one
2. Monolith
3. Modular Monolith

## Decision

Use a **Modular Monolith** approach initially — a single deployable FastAPI application with clearly bounded internal modules.

## Rationale

| Factor | Microservices | Modular Monolith |
|---|---|---|
| Development speed | Slow (infra overhead) | Fast |
| Operational complexity | High | Low |
| Team size fit | Large teams | Small–medium teams |
| Boundary enforcement | Forced by network | Enforced by code convention |
| Future flexibility | N/A | Can extract to services later |
| Testability | Hard (network mocks) | Easy (in-process) |

## Consequences

- Each module must maintain strict internal isolation.
- Cross-module communication only via defined interfaces or domain events.
- No direct model imports across module boundaries.
- Modules can be extracted to independent microservices when scale demands it.
