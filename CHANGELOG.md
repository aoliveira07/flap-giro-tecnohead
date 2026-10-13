# Changelog

## 0.1.0-alpha.22

- ao selecionar uma TV real, renomeia a entidade física para `*_base`;
- cria a entidade `media_player` composta usando o mesmo nome e identificador original da TV;
- mantém a TV física como base de energia e publica os presets na entidade composta.

## 0.1.0-alpha.21

- removeu os controles de ligar/desligar da TV composta no aplicativo;
- atualiza imediatamente no MQTT a lista de presets exposta como fontes da TV composta;
- mantém a publicação de descoberta e estado para o Home Assistant após alterações nos presets.

## 0.1.0-alpha.20

- Adiciona `icon.png` oficial do app, com monitor e estrelas, para substituir o ícone padrão de peça no Home Assistant.
- Mantém o mesmo símbolo no cabeçalho interno do aplicativo.

## 0.1.0-alpha.19

- Habilita o acesso à API do Home Assistant para listar entidades `media_player` no seletor de TV.
- Mostra a indisponibilidade da API no seletor e tenta carregar os televisores novamente automaticamente.

## 0.1.0-alpha.18

- Atualiza a identidade visual para o padrão azul-petróleo do LG Local Thing.
- Adiciona o ícone Flap Tecnohead no cabeçalho e reorganiza os comandos com símbolos de mídia.
- Move o histórico para depois da TV e HOME / Calibrar para o último elemento da tela.

## 0.1.0-alpha.17

- Reorganiza o painel de operação com HOME / Calibrar acima do histórico.
- Exibe os três últimos comandos IR confirmados, com origem e horário.

## 0.1.0-alpha.16

- Aguarda até o timeout configurado do iTach pela confirmação `completeir`; a resposta real do equipamento chega após aproximadamente 1 segundo.
- Evita marcar comandos válidos como falha e iniciar a posição estimada antes da confirmação.

## 0.1.0-alpha.15

- Inicia o relógio da posição estimada somente depois da confirmação `completeir` do iTach.
- Mantém a posição em espera durante o envio de Direita/Esquerda e só finaliza Parar após a confirmação do iTach.
- Aguarda a confirmação do iTach antes de iniciar os tempos de Abrir e Fechar.

## 0.1.0-alpha.14

- Calcula o tempo seguro de transmissão do quadro IR e impede colisões rápidas no iTach.
- Desabilita os comandos da interface até o próximo envio poder ser recebido com segurança.
- Retorna uma mensagem de aguardo em vez de erro interno quando um comando chega cedo demais.

## 0.1.0-alpha.13

- Mantém o Fechar com o Pronto Hex original (`repeat=1`) e duas emissões espaçadas.
- Mantém os demais comandos em uma única emissão com repetição interna do protocolo.
- Aplica `busyIR` como falha para qualquer comando do iTach.

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

