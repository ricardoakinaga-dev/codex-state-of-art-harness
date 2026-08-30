# Concurrency report

O piloto usa threads reais para oito writers concorrentes. Para a mesma chave
de idempotência, todos retornam 201/replay e existe um único appointment. Para
chaves diferentes no mesmo slot, exatamente um writer retorna 201 e os sete
retornam `CONFLICT`.

Também há inicialização concorrente de migrations em processos separados. Os
testes de persistência exercitam writers concorrentes no mesmo snapshot. Isso
é a simulação mais forte disponível no fixture; não é uma alegação sobre todos
os bancos, filesystems ou cargas de produção.
