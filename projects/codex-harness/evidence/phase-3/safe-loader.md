# Safe progressive loader

The loader exposes explicit levels and returns immutable load results:

| Level | Meaning | Context prepared | Host loaded | Execution |
| --- | --- | --- | --- | --- |
| L0 | identity | no | no | disabled |
| L1 | routing metadata | no | no | disabled |
| L2 | bounded instruction kernel | yes, when selected and fresh | no | disabled |
| L3 | selected, inventory-approved refs | yes, bounded and fresh | no | disabled |
| L4 | approved declarative package | yes, bounded and fresh | no | `DISABLED_PHASE3` |

The loader revalidates the package snapshot before L2+ disclosure; stale
bytes, file sets, metadata or aliases are blocked. References are resolved only
beneath the package, must be present in the discovered inventory and are
count/byte bounded; binary files are metadata-only. Script, provider, MCP,
shell and network surfaces are represented as disabled metadata. The real
sample load plan remains metadata-only and deliberately has no host-loaded
observation.
