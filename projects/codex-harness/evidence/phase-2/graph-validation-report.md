# Graph validation report

`validate_execution_graph` rejeita antes de qualquer provider: IDs
duplicados, dependencies/edges duplicadas ou dangling, self-edge, ciclo,
acceptance ausente, owner ausente, merge/conflict inválido, política de merge
desconhecida, authority negada e node/graph budgets impossíveis.

`execute_graph` só agenda o DAG validado, respeita `max_nodes`,
`max_invocations`, `max_duration_ms` e cancellation, e ordena de forma
determinística. Falha de dependency bloqueia descendentes por padrão;
`allow_failed_dependencies` é explícito no node e não apaga o failure.

Evidência: `test_phase2_adversarial.py` cobre ciclos, dangling refs,
duplicatas, budgets, falha com partial independente e cancellation; os testes
de execução cobrem graph success e dependency failure com artifact/evidence por
node.
