# Retry, timeout and cancellation report

Foram testados retry de lock transitório, retry budget exaurido, falha não
retryable, timeout antes/depois de observação, cancelamento sem interrupt ack,
cancelamento após início de turn, partial result, dependency failure e host
unavailable.

As invariantes são explícitas: timeout/cancelamento/partial não viram `PASS`,
falha desconhecida fecha o lifecycle, retry de mutação não idempotente não é
cego e o orçamento impede loop infinito.
