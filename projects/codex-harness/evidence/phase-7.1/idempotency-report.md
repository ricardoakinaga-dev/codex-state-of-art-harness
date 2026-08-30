# Idempotency report

Cobertura observada:

- mesma request/chave: replay estável, sem segunda mutação;
- mesma chave/payload idêntico: resposta armazenada é reutilizada;
- mesma chave/payload conflitante: `IDEMPOTENCY_KEY_REUSE`/409;
- nova chave/payload igual: conflito de slot impede duplicação;
- retry após lock transitório: retry bounded e segunda tentativa bem-sucedida;
- retry após sucesso: replay persistente bloqueia novo host call;
- chave concorrente: oito writers deixam uma única entidade.

`test_corrupt_saved_idempotency_response_fails_closed` também impede que uma
resposta persistida corrompida seja aceita silenciosamente.
