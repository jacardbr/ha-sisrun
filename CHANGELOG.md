# Changelog

## 0.3.0

### Novo
- **Tempo de prova** (campo editável sob o título, já vem como 00:00:00; só administradores editam): você cadastra o tempo final de cada prova; fica guardado só no Home Assistant, salva ao sair do campo ou com Enter. Comando `ha_sisrun/set_race_time`.
- **Renomear prova só localmente** (lápis ✎ ao lado do título, só para administradores): o nome fica guardado no Home Assistant e o SisRUN não é alterado; salvar vazio volta ao nome original. Comando `ha_sisrun/set_race_name`.
- **Card Lovelace `custom:ha-sisrun-card`** com três abas: **Planilha** (semana atual), **VO2 Max**
  (último teste, gráfico de histórico e tabela) e **Provas** (objetivos/metas do SisRUN, com filtro por ano). Servido pela própria integração
  e carregado automaticamente; acha as entidades sozinho (ou via `entities:`).

- **Navegação de semanas** na aba Planilha (‹ › e *Hoje*); dias sem treino ficam ocultos.

- **Importar histórico na configuração**: campo novo ao adicionar a integração (e em Configurar) com o número de semanas passadas a importar; roda em segundo plano, uma vez por valor.
- **Importar todo o histórico**: opção na configuração e em Configurar; volta semana a semana até acabarem os treinos (16 semanas vazias seguidas ou 10 anos), com notificação do resultado; a ação `load_history` ganhou o campo `all`. O limite de semanas guardadas subiu de 104 para 520.

- **Inscrição nas provas**: tag vermelha/verde na aba Provas, marcada por você (dado local, não vem do SisRUN).

### Mudanças internas
- Comandos websocket `ha_sisrun/week`, `ha_sisrun/races` e `ha_sisrun/set_registration` (usados pelo card; o último exige administrador).
- `sisrun_api/races.py` (novo): leitor da tela de metas, com paginação (tenta pedir todas as linhas de uma vez; senão, página a página).
- `manifest.json` passa a depender de `http` e `frontend`.
- Novo `frontend/ha-sisrun-card.js` (sem dependências externas).

## 0.2.0

### Novo
- **Detalhes do treino de hoje** em sensores separados: km, intensidade e observação do treinador.
- **Botão "Atualizar agora"** para consultar o SisRUN sem esperar o intervalo.
- **Aviso quando a planilha muda**: evento `ha_sisrun_plan_changed` (tipos `added`, `changed`, `removed`),
  com frase pronta em `message`. Marcar treino como feito não gera aviso.
- **Aderência semanal (%)**: feitos ÷ prescritos da semana, com contagens e km nos atributos.
- **Histórico**: ação `ha_sisrun.load_history` busca até 52 semanas passadas e guarda no Home Assistant;
  o calendário passa a mostrá-las.
- **Sensores por dia da semana**: "Treino de segunda" até "Treino de domingo", sempre da semana atual, com
  o resumo do dia no estado e `date`, `statuses` e `workouts` nos atributos.
- **Teste de desempenho**: sensor com o VO2 máx do último teste e o histórico completo nos atributos
  (guardado no Home Assistant); evento `ha_sisrun_new_test` quando aparece um teste novo. Lê só a primeira
  página (15 testes) da lista do SisRUN.
- **Ícone e logo próprios** (pasta `brand/`, exibidos a partir do Home Assistant 2026.3): desenho original
  de um corredor, nas cores do Home Assistant. Fontes SVG em `design/`.

### Removido
- Binário **Treino pendente hoje** (existia na 0.1.0). Para lembretes, use o sensor **Treino de hoje**
  (vale `Sem treino` nos dias sem prescrição); exemplo no README.
- A integração apaga do registro de entidades as que foram retiradas (se você já as tinha instalado).

### Mudanças internas
- Os treinos lidos agora são guardados em `.storage/ha_sisrun.<id>` (apagado ao remover a integração).
- Toda consulta também lê a semana anterior (o SisRUN importa atividades do Garmin/Strava com atraso).
- Uma semana que vem sem os painéis de detalhe não sobrescreve a leitura anterior.
- `sisrun_api/fetch.py` (novo) junta cliente e parser; `client.py` e `parser.py` seguem idênticos ao
  sisrun-mcp.
- UIDs dos eventos do calendário passam a ser estáveis (data + ordem no dia).

## 0.1.0

Primeira versão: calendário, sensores (treino de hoje, próximo, km da semana) e binário "treino pendente hoje".
