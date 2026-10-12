# Changelog

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

