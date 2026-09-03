# Threat model

## Protected properties

RunSpecimen is designed to prevent accidental or agent-driven double launch,
stale approval reuse, source/contract/executable drift, output overwrite, and
continuation past an uncertified predecessor. It records bounded output captures,
atomic lifecycle state, a hash-chained event log, and a verifiable receipt.

## Trusted boundary

The human invoking the TTY approval, the local operating-system account, the
RunSpecimen installation, Python runtime, workspace filesystem, and workload are
trusted. The Codex and Cursor adapters do not expand this boundary; they call the
same CLI and cannot manufacture an approval.

## Explicitly out of scope

- Hostile workload sandboxing or privilege isolation
- CPU, memory, network, filesystem-write, or child-process-count containment
- Protection from root, kernel, hypervisor, or full-workspace rewrite attacks
- Remote scheduling, distributed consensus, or exactly-once effects outside the workspace
- Proof that a scientific claim is true

## Residual risks

The wall-clock timeout kills the launched process group, but detached or hostile
process behavior is outside the security boundary. Native libraries, environment
variables, input services, and datasets are not automatically fingerprinted.
Place material local inputs in `source.roots`; use a container or OS sandbox when
the payload or its dependencies are not trusted.
