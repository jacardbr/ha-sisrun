# SisRUN para Home Assistant (não oficial)

Traz a sua planilha de treinos do SisRUN (app do **aluno**) para o Home Assistant: calendário, sensores,
aviso quando o treinador muda a planilha e histórico de semanas passadas.

**Somente leitura**: nunca escreve nada no SisRUN. Não é afiliado nem apoiado pelo SisRUN.

Versão atual: **0.2.0** (veja o [CHANGELOG](CHANGELOG.md)).

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
5. Informe o e-mail e a senha que você usa no app do aluno.

Precisa do Home Assistant **2025.1 ou mais novo**.

**Atualizando da 0.1.0:** apague `custom_components/ha_sisrun` antigo, copie o novo e reinicie. A conta
configurada continua valendo; as entidades novas aparecem sozinhas. O binário "Treino pendente hoje" da
0.1.0 foi retirado, e a integração o apaga do registro ao iniciar (ajuste automações que usavam
`binary_sensor.sisrun_treino_pendente_hoje`, por exemplo com o exemplo de lembrete abaixo).

### Opções

Em **SisRUN → Configurar**: de quantas em quantas horas consultar (padrão 3) e quantas semanas à frente
buscar (padrão 1). Cada semana extra é mais uma requisição ao SisRUN. Em toda consulta a integração lê também
a semana anterior, porque o SisRUN importa as atividades do Garmin/Strava com atraso.

## Histórico

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
