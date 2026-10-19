# SisRUN para Home Assistant (não oficial)

Traz a sua planilha de treinos do SisRUN (app do **aluno**) para o Home Assistant:
calendário, sensores e um aviso de "treino pendente hoje" para usar em automações.

**Somente leitura**: nunca escreve nada no SisRUN. Não é afiliado nem apoiado pelo SisRUN.

## O que você ganha

| Entidade (nome no HA) | O que é |
|---|---|
| Calendário **Treinos** | Um evento de dia inteiro por treino prescrito. A descrição traz estrutura da sessão, intensidade, FC, observação do treinador e o que foi realizado. `✓` = feito, `✗` = não feito. |
| Sensor **Treino de hoje** | Texto curto (ex.: `Corrida · Intervalado · 8.5 km`) ou `Sem treino`. Atributo `workouts` com os detalhes. |
| Sensor **Próximo treino** | Data do próximo treino ainda não feito. Atributo `workout` com os detalhes. |
| Sensor **Km planejados na semana** | Soma dos km prescritos (usa o `planned_km` corrigido do sisrun-mcp). |
| Sensor **Km realizados na semana** | Soma dos km que o SisRUN associou como feitos (importa do Garmin/Strava). |
| Binário **Treino pendente hoje** | Ligado se existe treino de hoje ainda não feito (`Proposto`/`Programado`). |

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

### Opções

Em **SisRUN → Configurar**: de quantas em quantas horas consultar (padrão 3) e quantas semanas à frente
buscar (padrão 1). Cada semana extra é mais uma requisição ao SisRUN; os treinos mais distantes só
aparecem no calendário se você aumentar esse número.

## Exemplo de automação: lembrete de manhã

```yaml
automation:
  - alias: "Lembrete de treino SisRUN"
    triggers:
      - trigger: time
        at: "06:00:00"
    conditions:
      - condition: state
        entity_id: binary_sensor.sisrun_treino_pendente_hoje
        state: "on"
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
  sem alterações (commit em `sisrun_api/UPSTREAM_COMMIT.txt`).
- **Pode quebrar** quando o SisRUN mudar o site. Nesse caso, copie as versões novas desses dois arquivos do
  repositório original por cima e reinicie.
- **A senha fica guardada em texto puro** no armazenamento do Home Assistant
  (`.storage/core.config_entries`), como em qualquer integração. Se possível, use uma senha que você não
  repita em outros lugares.
- A integração só fala com `https://appsisrun.com.br`. Consulta poucas vezes por dia, com intervalo entre
  requisições, para não sobrecarregar o servidor. Respeite os Termos de Serviço do SisRUN.
- Os horários dos treinos **não existem** no SisRUN, por isso os eventos do calendário são de dia inteiro.
- `Feito Avulso` (atividade importada que o treinador não prescreveu) não aparece no calendário nem entra
  nos km planejados.

## Problemas comuns

- **"Não consegui falar com o SisRUN"**: rede do container sem saída para a internet, ou o site mudou.
  Veja **Configurações → Sistema → Registros** e filtre por `sisrun`.
- **Estrutura/observação do treinador vazias**: o log mostra `veio sem os detalhes dos treinos`. É o sinal
  de que o site mudou; abra uma issue no sisrun-mcp.
- Para mais detalhes nos logs, em `configuration.yaml`:

  ```yaml
  logger:
    logs:
      custom_components.ha_sisrun: debug
  ```
