# Flap de Giro Tecnohead

Repositório independente para o Home Assistant App de controle do Flap de Giro Tecnohead diretamente por um Global Caché iTach. O App mantém posição estimada por tempo, persistência, calibração HOME, presets, diagnóstico, API local e uma entidade `media_player` composta para TV/HomeKit via MQTT Discovery.

## Instalação

Adicione o repositório ao App Store do Home Assistant, instale **Flap de Giro Tecnohead**, inicie e abra pelo Ingress. O App usa `host_network: true` para alcançar o iTach na rede local e solicita o serviço MQTT do Home Assistant quando disponível.

## Primeira configuração

Preencha na tela de configuração:

- iTach: `192.168.0.46`
- porta TCP: `4998`
- `connaddr`: `3`
- curso total inicial: `37` segundos
- HOME: direção `Esquerda` e margem adicional inicialmente `2` segundos

Selecione a entidade `media_player` real da TV somente depois que o vínculo com o Home Assistant estiver disponível. A entidade composta publica os presets como sources e espelha o estado de power da TV real; o estado mecânico do Flap aparece separadamente.

## Primeiro teste físico

1. Mantenha a configuração YAML antiga disponível e evite que ela e o App enviem comandos simultaneamente.
2. Teste conexão TCP.
3. Teste individualmente Abrir, Parar, Esquerda, Direita e Fechar.
4. Execute `HOME / Calibrar` e confirme o fim de curso físico.
5. Valide 0%, 30%, 65%, 100%, retorno ao HOME e fechamento.
6. Só depois vincule a TV, valide ligar/desligar e exponha a entidade composta pela HomeKit Bridge.

## Segurança operacional

A posição é estimada por relógio monotônico durante o movimento. Um reinício durante movimento marca a referência como `UNCERTAIN` e bloqueia fechamentos automáticos baseados nessa posição até uma nova calibração HOME. `Parar` cancela a operação ativa e tem prioridade.

## Desenvolvimento local

```powershell
$env:PYTHONPATH = "$PWD\flap-giro-tecnohead"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8099
```

## Documentação

- [Documentação do App](DOCS.md)
- [Histórico de versões](CHANGELOG.md)

