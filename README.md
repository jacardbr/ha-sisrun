# SisRUN para Home Assistant (não oficial)

Traz a sua planilha de treinos do SisRUN (app do **aluno**) para o Home Assistant: calendário, sensores,
aviso quando o treinador muda a planilha e histórico de semanas passadas.

**Somente leitura**: nunca escreve nada no SisRUN. Não é afiliado nem apoiado pelo SisRUN.

Versão atual: **0.4.0** (veja o [CHANGELOG](CHANGELOG.md)).

## O que você ganha

| Entidade (nome no HA) | O que é |
|---|---|
| Calendário **Treinos** | Um evento de dia inteiro por treino prescrito, inclusive o histórico carregado. A descrição traz estrutura da sessão, intensidade, FC, observação do treinador e o que foi realizado. `✓` = feito, `✗` = não feito. |
| Botão **Atualizar agora** | Consulta o SisRUN na hora, sem esperar o intervalo. |
| Sensor **Treino de hoje** | Texto curto (ex.: `Corrida · Intervalado · 8.5 km`) ou `Sem treino`. Atributo `workouts` com os detalhes. |
| Sensores **do treino de hoje** | `Km do treino de hoje`, `Intensidade do treino de hoje` e `Observação do treinador (hoje)`. Ficam sem valor (`unknown`) quando não há treino ou o campo está vazio. Com dois treinos no dia, valem para o primeiro ainda pendente. A estrutura completa e a FC ficam no atributo `workouts` do sensor **Treino de hoje** e na descrição do evento no calendário. |
| Sensor **Próximo treino** | Data do próximo treino ainda não feito. Atributo `workout` com os detalhes. |
| Sensor **Km planejados na semana** | Soma dos km prescritos (usa o `planned_km` corrigido do sisrun-mcp). |
| Sensor **Km realizados na semana** | Soma dos km que o SisRUN associou como feitos (importa do Garmin/Strava). |
| Sensor **Aderência semanal** | % de treinos feitos entre os prescritos da semana (feitos ÷ feitos + não feitos + pendentes). `Justificado` fica fora da conta. Atributos: `done`, `pending`, `missed`, `justified`, `total`, `planned_km`, `done_km`, `km_percent`. Sem treino prescrito na semana, fica sem valor. |
| Sensores **Treino de segunda … Treino de domingo** | Um por dia da semana atual. O estado é o mesmo resumo do **Treino de hoje** (`Corrida · Intervalado · 8.5 km`, ou `Sem treino`; com dois treinos no dia, aparecem juntos). Atributos: `date`, `statuses` (status de cada treino do dia) e `workouts` (detalhes completos: estrutura, FC, intensidade, observação do treinador e o que foi realizado). Na virada da semana (segunda, 00:00) passam a mostrar a semana nova. |
| Sensor **Teste de desempenho** | Estado: **VO2 máx** do teste mais recente (mL/(kg·min)). Atributos: `date`, `protocol`, `distance_km`, `time`, `pace`, `speed_kmh`, `vo2max`, `tests_count` e `history` (lista com até 50 testes, do mais novo ao mais antigo, cada um com os mesmos campos). Lê a página *Teste de Desempenho* do SisRUN. |

Os IDs das entidades dependem do idioma do seu Home Assistant (ex.: `sensor.sisrun_treino_de_hoje`).
Confirme os reais em **Ferramentas do desenvolvedor → Estados**.

## Instalar (Home Assistant em Docker)

1. Descubra a pasta do seu volume de configuração (a que está mapeada para `/config` no container).
2. Copie a pasta `custom_components/ha_sisrun` deste pacote para dentro dela:

   ```bash
   cp -r custom_components/ha_sisrun /caminho/do/seu/config/custom_components/
   ```

   Se `custom_components` não existir, crie-a. O resultado deve ser
   `/caminho/do/seu/config/custom_components/ha_sisrun/manifest.json`.
3. Reinicie o container:

   ```bash
   docker restart homeassistant   # troque pelo nome do seu container
   ```
4. No Home Assistant: **Configurações → Dispositivos e serviços → Adicionar integração → SisRUN**.
5. Informe o e-mail e a senha que você usa no app do aluno e escolha o histórico: marque **Importar todo o histórico** ou, deixando desmarcado, informe na tela seguinte quantas semanas importar (padrão 12; 0 = não importar). A importação roda em segundo plano logo após a configuração e alimenta o calendário e as semanas anteriores do card.

Precisa do Home Assistant **2025.1 ou mais novo**. O ícone e o logo da integração (pasta `brand/`) só são
exibidos a partir da **2026.3**; em versões anteriores aparece o ícone genérico, sem afetar o funcionamento.

**Atualizando da 0.1.0:** apague `custom_components/ha_sisrun` antigo, copie o novo e reinicie. A conta
configurada continua valendo; as entidades novas aparecem sozinhas. O binário "Treino pendente hoje" da
0.1.0 foi retirado, e a integração o apaga do registro ao iniciar (ajuste automações que usavam
`binary_sensor.sisrun_treino_pendente_hoje`, por exemplo com o exemplo de lembrete abaixo).

### Opções

Em **SisRUN → Configurar**: de quantas em quantas horas consultar (padrão 3), quantas semanas à frente
buscar (padrão 1) e quantas semanas de histórico importar (aumentar o número importa o que falta, uma vez; a ação `ha_sisrun.load_history` continua disponível). Cada semana extra é mais uma requisição ao SisRUN. Em toda consulta a integração lê também
a semana anterior, porque o SisRUN importa as atividades do Garmin/Strava com atraso.

## Histórico

**Todo o histórico:** na configuração (ou em SisRUN → Configurar) marque *Importar todo o histórico*. A integração volta semana a semana (cerca de 1 requisição por semana, ~1 s cada) até o começo do que o SisRUN mostra; para quando encontra 16 semanas seguidas sem treino ou chega a 10 anos, e não guarda essa cauda vazia. Roda em segundo plano, pode levar alguns minutos e acontece uma vez; ao terminar, uma notificação do Home Assistant informa quantas semanas foram lidas e a data do treino mais antigo (se o SisRUN não tiver nada anterior, é ali que ele para). Para repetir depois, use a ação `ha_sisrun.load_history` com **Todo o histórico** ligado.

Para o calendário mostrar treinos antigos, chame a ação uma vez (**Ferramentas do desenvolvedor → Ações**):

```yaml
action: ha_sisrun.load_history
data:
  weeks: 12        # de 1 a 52; padrão 12
```

Cada semana é uma requisição ao SisRUN (com pausa entre elas), então 12 semanas levam alguns segundos e 52
levam cerca de um minuto. O histórico fica guardado no Home Assistant (até 104 semanas) e é apagado se você
remover a integração. Rodar de novo atualiza as semanas já guardadas.

## Aviso quando a planilha muda

Quando o treinador **adiciona, altera ou remove** um treino (da semana atual em diante), a integração dispara
o evento `ha_sisrun_plan_changed`, um por mudança:

| Campo | Conteúdo |
|---|---|
| `type` | `added`, `changed` ou `removed` |
| `date` | Dia do treino (`AAAA-MM-DD`) |
| `message` | Frase pronta, ex.: `Treino de 21/10 alterado (estrutura): Corrida · Longo · 16.0 km → ...` |
| `fields` | Em `changed`, o que mudou (`estrutura`, `distância`, `intensidade`...) |
| `before`, `after` | O treino antes e depois (completo) |
| `config_entry_id` | Conta do SisRUN |

Marcar um treino como feito **não** gera aviso; só mudanças na prescrição. Na primeira instalação, e para
semanas que a integração nunca tinha visto, não há avisos (senão você receberia a planilha inteira como
"novidade").

```yaml
automation:
  - alias: "Avisar quando o treinador mudar a planilha"
    triggers:
      - trigger: event
        event_type: ha_sisrun_plan_changed
    actions:
      - action: notify.notify          # troque pelo seu serviço de notificação
        data:
          title: "Planilha SisRUN"
          message: "{{ trigger.event.data.message }}"
```

## Testes de desempenho

O sensor **Teste de desempenho** guarda todos os testes que já apareceram na página do SisRUN. O histórico
fica no Home Assistant (`.storage`): se a página mostrar menos testes no futuro, os antigos não somem.
`history` fica fora do banco do recorder, para não inchá-lo; o estado (VO2 máx) é gravado normalmente.

- A página tem 15 testes por tela e a integração lê só a primeira. Quem tem mais de 15 testes terá, no
  máximo, os 15 mais recentes lidos de uma vez (um aviso vai para o log).
- Na primeira leitura os testes existentes viram só a "linha de base", sem avisos. Depois, cada teste novo
  dispara o evento `ha_sisrun_new_test`, com os campos do teste (`date`, `protocol`, `distance_km`, `time`,
  `pace`, `speed_kmh`, `vo2max`), uma frase pronta em `message` e `config_entry_id`.
- A ação `ha_sisrun.load_history` não relê os testes; eles vêm da atualização normal.

```yaml
automation:
  - alias: "Parabenizar pelo teste de desempenho"
    triggers:
      - trigger: event
        event_type: ha_sisrun_new_test
    actions:
      - action: notify.notify
        data:
          message: "{{ trigger.event.data.message }}"
```

## Card Lovelace

A integração traz o card **SisRUN** e o carrega sozinha (não precisa cadastrar recurso). Depois de reiniciar,
adicione em um painel: **Editar painel → Adicionar card → SisRUN**, ou em YAML:

```yaml
type: custom:ha-sisrun-card
title: SisRUN          # opcional; "" esconde o título
default_tab: plan      # plan | vo2 | races
```

Três abas:

- **Planilha**: a semana dia a dia (hoje em destaque; dias sem treino não aparecem), com os controles « ‹ › » (« e » vão para a primeira e a última semana registradas; ‹ e › andam uma semana) abaixo da barra de progresso para voltar e avançar semanas (botão *Hoje* para retornar), com status, km, intensidade, FC, o que foi
  realizado e a estrutura/observação do treinador (toque em *Estrutura*). No topo: km planejados, km
  realizados e aderência da semana mostrada. Só há dados das semanas que a integração já leu: a atual, a anterior e as à frente configuradas; para mais antigas use a ação `ha_sisrun.load_history`.
- **VO2 Max**: VO2 máx do último teste e variação em relação ao anterior, gráfico do histórico (passe o mouse
  ou toque num ponto para ver o teste) e tabela com todos os testes.
- **Provas**: suas provas e objetivos (tela *Objetivos/Metas* do SisRUN), com filtro por ano (chips *Todos*, 2026, 2025...; abre no ano atual). Mostra data, nome, distância, prioridade (★ Principal), situação e quanto falta ou quanto passou; a próxima prova fica destacada. Cada prova tem a tag **Inscrição**: vermelha (✗) até você tocar nela, quando fica verde (✓, inscrito). Essa informação o SisRUN não fornece: é guardada só no Home Assistant, junto das provas, e sobrevive às releituras (só administradores do Home Assistant conseguem marcar). Lê todas as páginas da lista (o SisRUN mostra 15 por vez) e guarda no Home Assistant; provas excluídas no SisRUN somem na próxima leitura.

O card acha as entidades sozinho. Se você tiver duas contas, ou ele não achar, indique-as:

```yaml
type: custom:ha-sisrun-card
entities:
  monday: sensor.sisrun_treino_de_segunda
  # ... tuesday a sunday
  performance: sensor.sisrun_teste_de_desempenho
  planned_km: sensor.sisrun_km_planejados_na_semana
  done_km: sensor.sisrun_km_realizados_na_semana
  adherence: sensor.sisrun_aderencia_semanal
```

Se o card não aparecer na lista depois de atualizar, recarregue o navegador sem cache (Ctrl+F5).

## Exemplo de automação: lembrete de manhã

O sensor **Treino de hoje** vale `Sem treino` nos dias sem prescrição, então ele serve de condição:

```yaml
automation:
  - alias: "Lembrete de treino SisRUN"
    triggers:
      - trigger: time
        at: "06:00:00"
    conditions:
      - condition: template
        value_template: >-
          {{ states('sensor.sisrun_treino_de_hoje') not in ['Sem treino', 'unknown', 'unavailable'] }}
    actions:
      - action: notify.notify          # troque pelo seu serviço de notificação
        data:
          title: "Treino de hoje"
          message: "{{ states('sensor.sisrun_treino_de_hoje') }}"
```

## Como funciona e cuidados

- O SisRUN **não tem API pública**. Esta integração usa o cliente do projeto
  [cdutr/sisrun-mcp](https://github.com/cdutr/sisrun-mcp) (MIT), que entra com o seu login e lê as mesmas
  páginas que você vê no navegador. Os arquivos `sisrun_api/client.py` e `sisrun_api/parser.py` são cópias
  sem alterações (commit em `sisrun_api/UPSTREAM_COMMIT.txt`); `sisrun_api/fetch.py` é código desta integração.
- **Pode quebrar** quando o SisRUN mudar o site. Nesse caso, copie as versões novas de `client.py` e
  `parser.py` do repositório original por cima e reinicie.
- Se uma leitura vier **sem os detalhes** dos treinos (sinal de que o site mudou), a integração mantém a
  leitura anterior daquela semana em vez de apagar a estrutura e disparar avisos falsos, e registra um aviso
  no log.
- **A senha fica guardada em texto puro** no armazenamento do Home Assistant
  (`.storage/core.config_entries`), como em qualquer integração. Se possível, use uma senha que você não
  repita em outros lugares.
- Os treinos lidos ficam em `.storage/ha_sisrun.<id>` (histórico e última planilha conhecida). Remover a
  integração apaga esse arquivo.
- A integração só fala com `https://appsisrun.com.br`. Consulta poucas vezes por dia, com intervalo entre
  requisições, para não sobrecarregar o servidor. Respeite os Termos de Serviço do SisRUN.
- O ícone e o logo são desenhos originais desta integração (fontes em `design/`), nas cores do Home Assistant;
  não reproduzem a marca do SisRUN. Para trocar o texto ou as cores, edite o SVG e regere os PNGs de
  `custom_components/ha_sisrun/brand/` (`icon` 256×256 e `logo`, mais as versões `@2x` e `dark_`).
- Os horários dos treinos **não existem** no SisRUN, por isso os eventos do calendário são de dia inteiro.
- `Feito Avulso` (atividade importada que o treinador não prescreveu) não aparece no calendário, não entra
  nos km planejados nem na aderência.

## Problemas comuns

- **"Não consegui falar com o SisRUN"**: rede do container sem saída para a internet, ou o site mudou.
  Veja **Configurações → Sistema → Registros** e filtre por `sisrun`.
- **Estrutura/observação do treinador vazias**: o log mostra `veio sem os detalhes dos treinos`. É o sinal
  de que o site mudou; abra uma issue no sisrun-mcp.
- **O botão "Atualizar agora" não fez nada**: o Home Assistant limita pedidos repetidos em poucos segundos;
  espere um pouco e tente de novo.
- Para mais detalhes nos logs, em `configuration.yaml`:

  ```yaml
  logger:
    logs:
      custom_components.ha_sisrun: debug
  ```
