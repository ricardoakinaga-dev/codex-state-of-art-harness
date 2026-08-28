# ADR P2-001 — Provider contract local

## Decisão

Providers implementam um protocolo pequeno: recebem uma `CapabilityInvocation`
já validada e um snapshot de manifest, e retornam `ProviderExecutionResult`
estruturado. Provider não classifica, roteia, autoriza, verifica ou decide
assurance. O registry de providers é immutable e a disponibilidade é explícita.

## Consequências

O primeiro walking skeleton usa providers locais determinísticos de sucesso e
falha. Não existe fallback oculto, rede, subprocesso, import dinâmico ou adapter
do host Codex. Um provider unavailable permanece uma falha tipada e observável.
