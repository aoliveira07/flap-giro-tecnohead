# Changelog

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

