# Safe progressive loader

The loader exposes explicit levels and returns immutable load results:

| Level | Meaning | Context prepared | Host loaded | Execution |
| --- | --- | --- | --- | --- |
| L0 | identity | no | no | disabled |
| L1 | routing metadata | no | no | disabled |
| L2 | bounded instruction kernel | yes, when selected | no | disabled |
| L3 | selected in-package refs | yes, bounded | no | disabled |
| L4 | approved declarative package | yes, bounded | no | `DISABLED_PHASE3` |

References are resolved only beneath the package and are count/byte bounded;
binary files are metadata-only. Script, provider, MCP, shell and network
surfaces are represented as disabled metadata. The real sample load plan
prepares context but deliberately has no host-loaded observation.
