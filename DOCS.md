# Documentação do App

## Arquitetura

O fluxo é Home Assistant → App → TCP/IP → Global Caché iTach → IR → Flap. O App não usa `remote.flap` nem a integração YAML legada para executar os cinco comandos IR.

O perfil embarcado `tecnohead_flap_giro_v1` contém Abrir, Fechar, Parar, Esquerda e Direita. O IP e os tempos são configuração da instalação e não fazem parte do perfil do equipamento.

## Estado e persistência

SQLite em `/data/flap_giro_tecnohead.db` guarda configuração, presets, logs e estado mecânico. O estado inclui posição, destino, direção, último comando, sequência, calibração e estado observado da TV. A posição nunca é tratada como precisa depois de um reinício durante movimento.

## HOME / Calibrar

HOME abre o Flap, gira no sentido configurado durante o curso total mais a margem de homing, envia Parar, define giro em 0%, marca a referência como calibrada e fecha. O limite físico interno do equipamento é a referência absoluta; não é necessário um sensor de retorno nesta versão.

## Presets e TV composta

Os presets iniciais são Cozinha (30%), Poltronas (65%) e Piscina (100%), mas são dados persistidos e editáveis. Ao selecionar uma TV real na configuração, o App renomeia a entidade física para o sufixo `_base` e cria a entidade MQTT composta usando o identificador e o nome originais da TV. A entidade composta publica `source/source_list`, `TURN_ON` e `TURN_OFF`; a entidade `_base` continua sendo a fonte real de energia e estado.

O `on/off` da TV composta é derivado exclusivamente do estado real da TV vinculada no Home Assistant. `unavailable` e `unknown` não são convertidos artificialmente para ON/OFF. A TV pode estar OFF enquanto o Flap ainda retorna a 0% ou fecha.

O App faz reconciliação periódica da entidade vinculada usando a API Core do Home Assistant. Para essa função, o ambiente do App precisa fornecer `SUPERVISOR_TOKEN`; sem token, a configuração do vínculo pode ser salva, mas o estado não será consultado.

## API

Base: `/api/v1`.

Principais endpoints: `/status`, `/config`, `/open`, `/close`, `/stop`, `/rotate/left`, `/rotate/right`, `/position`, `/preset/{id}/select`, `/calibrate/home`, `/turn_on`, `/turn_off`, `/presets`, `/tv/entities`, `/tv/reconcile`, `/diagnostics`.

## Migração e rollback

Instale e homologue em paralelo. Depois de validar iTach, tempos, HOME, presets, persistência, TV e HomeKit, desative as automações antigas, remova apenas os helpers que não forem mais usados e retire `remote: platform: itach`. Para rollback, pare o App e reative a configuração YAML antiga.

## Dependências de campo

Ainda precisam de validação física: tempos reais de abertura/fechamento, necessidade de repetição IR, direção HOME, margem adequada, resposta do fim de curso e comportamento da TV específica.

