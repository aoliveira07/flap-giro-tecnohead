# Changelog

## 0.1.0-alpha.12

- Aguarda a liberação do iTach depois do STOP antes de enviar Fechar.
- Trata a resposta `busyIR` como falha real, evitando informar fechamento concluído quando o iTach rejeitou o comando.

## 0.1.0-alpha.11

- Envia apenas um comando TCP `sendir` por ação.
- Mantém a repetição dentro do próprio campo de protocolo do iTach, evitando transmissões consecutivas do mesmo comando.

## 0.1.0-alpha.10

- Reforça cada quadro `sendir` com no mínimo 3 repetições internas no iTach.
- Mantém as 2 emissões TCP redundantes já existentes, mesmo quando a configuração antiga ainda está salva com `ir_repeats: 1`.
- Aumenta a probabilidade de recepção dos comandos Direita, Esquerda e Parar pelo receptor IR.

## 0.1.0-alpha.9

- Preserva a calibração HOME concluída ao abrir novamente o mecanismo.
- A posição só volta a ser incerta quando há interrupção ou falha real durante movimento ou calibração.

## 0.1.0-alpha.8

- Mantém o HOME/calibração protegido contra novos movimentos até a conclusão e preserva o zero calibrado.
- Atualiza a posição real da interface aproximadamente a cada segundo.
- Retorna uma mensagem operacional clara quando um movimento é solicitado durante a calibração.
- Envia cada comando IR pelo menos duas vezes, com intervalo de 1 ms, incluindo Direita, Esquerda e Parar.

## 0.1.0-alpha.7

- Faz os botões Direita e Esquerda percorrerem até `100%` e `0%`, respectivamente, em vez de avançarem em incrementos de `10%`.
- Ao pressionar Parar, sincroniza a meta do slider com a posição estimada alcançada.

## 0.1.0-alpha.6

- Corrige o endereço do conector IR do iTach para o formato Global Caché `1:3`.
- Converte automaticamente a configuração antiga `3` para `1:3`.
- Completa as traduções da configuração quando o idioma do Home Assistant está em `pt`.

## 0.1.0-alpha.5

- Alterada a porta interna do App para `8100` para evitar conflito com o NeoControl quando ambos usam `host_network`.
- Incluídas na publicação as traduções e opções em português do Brasil da versão anterior.

## 0.1.0-alpha.4

- Adicionadas traduções em português do Brasil para todas as opções do App.
- Valores dos seletores HOME e TV exibidos em português, mantendo compatibilidade com os valores internos anteriores.

## 0.1.0-alpha.3

- Corrigida a opção opcional `tv_initial_preset_id` para não ser enviada como `null` no schema do Home Assistant.

## 0.1.0-alpha.2

- Publicação multi-arquitetura corrigida para a tag consumida pelo Home Assistant.
- Versão do App/runtime alinhada à versão do pacote Docker.

## 0.1.0-alpha.1

- Primeira versão do App Flap de Giro Tecnohead.
- Perfil IR Pronto Hex e driver TCP Global Caché iTach.
- Persistência SQLite, posição temporizada, HOME/calibração e presets.
- API versionada, diagnóstico e interface Ingress mobile-first.
- MQTT Discovery para controles, sensores e entidade de televisão composta.
- Vínculo opcional com TV real do Home Assistant e reconciliação de estado.

