# Telemetry and persistence report

Eventos são versionados, redacted, bounded, append-only e encadeados por
SHA-256. O ciclo inclui `RUN_CREATED`, classificação, rota, graph quando
aplicável, capability selection/load, invocation start/result/finish, retry,
verification, critique, assurance, stop, delivery quando aceito e
`RUN_COMPLETED`. `CAPABILITY_LOADED` só é emitido com observation/trace fresca.

Payload tem shape fixo; chaves e textos sensíveis são redacted. Limite de
telemetry trunca eventos com limitation observável. Um log corrompido não é
alterado; a persistência registra diagnóstico seguro e ainda grava o resultado
computado e seu summary. Writes são atômicos dentro da fronteira.

Sucesso local produz 19 eventos antes de qualquer truncation; `max_telemetry=2`
produz no máximo dois e a limitation. Replay idêntico de evento é idempotente;
colisão de ID é rejeitada.
