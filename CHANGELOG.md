# Changelog

## 0.2.0

### Novo
- **Detalhes do treino de hoje** em sensores separados: km, intensidade e observação do treinador.
- **Botão "Atualizar agora"** para consultar o SisRUN sem esperar o intervalo.
- **Aviso quando a planilha muda**: evento `ha_sisrun_plan_changed` (tipos `added`, `changed`, `removed`),
  com frase pronta em `message`. Marcar treino como feito não gera aviso.
- **Aderência semanal (%)**: feitos ÷ prescritos da semana, com contagens e km nos atributos.
- **Histórico**: ação `ha_sisrun.load_history` busca até 52 semanas passadas e guarda no Home Assistant;
  o calendário passa a mostrá-las.

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
