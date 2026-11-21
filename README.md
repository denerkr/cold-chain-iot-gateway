# Gateway de monitoramento e rastreamento de cadeia de frio

Protótipo distribuído para a disciplina DAS410103, desenvolvido por **Dener Kraus** e **Henrique Bueno de Morais**. A arquitetura integra ESP32 e DHT22 simulados no Wokwi, MQTT com Last Will and Testament (LWT), processamento de regras no Node-RED e um dashboard de telemetria.

> Este projeto é uma demonstração acadêmica. A simulação gera dados sintéticos e não substitui calibração, validação metrológica ou monitoramento de cargas reais.

## Arquitetura

```text
ESP32 + DHT22 + contato da porta
  ├─ cold-chain/<device_id>/telemetry  → temperatura, umidade e porta
  ├─ cold-chain/<device_id>/alarms     → excursão térmica e porta aberta
  └─ cold-chain/<device_id>/status     → online/offline (LWT retido)
                       │
                       ▼
             Broker MQTT Mosquitto
                       │
                       ▼
          Node-RED: validação e regras
                       │
                       ▼
        Dashboard em http://localhost:1880/ui
```

O ESP32 envia uma amostra a cada 10 segundos. Temperaturas fora de 2–8 °C geram evento na mudança de estado; porta aberta por mais de 30 segundos gera alarme. O keep-alive MQTT é de 30 segundos. Em uma desconexão abrupta, o broker publica o LWT `offline` retido após detectar a perda de conexão (o instante real depende do broker e da rede).

## Executar a simulação e gerar gráficos

Requer Python 3.9 ou superior. No PowerShell, na pasta do projeto:

```powershell
python -m pip install -r requirements.txt
python -m simulation.run_simulation
python -m unittest discover -s tests -v
```

A simulação é determinística (semente padrão `410103`), representa uma hora de dados em segundos de execução, introduz uma excursão térmica, abertura prolongada da porta, perda de mensagens configurável e desconexão inesperada do dispositivo. Ela é offline: as métricas são resultados do modelo sintético, não medições de um broker ou hardware real.

Os artefatos são salvos em [`reports/`](reports/):

- `performance_overview.png`: temperatura, faixa de conformidade, porta aberta, latência MQTT, alarmes e instante de desconexão.
- `system_performance.png`: latência média/P95, mensagens recebidas/perdidas e estimativa de detecção do LWT.
- `simulation_metrics.json`: volume de mensagens, taxa de entrega, latência média e P95, alarmes e latência estimada do LWT.
- `telemetry.csv` e `events.json`: amostras recebidas e eventos que permitem reproduzir a análise.

Para alterar a semente ou destino dos artefatos:

```powershell
python -m simulation.run_simulation --seed 123 --output-dir reports
```

## Executar broker e Node-RED

Requer Docker Desktop com Docker Compose:

```powershell
docker compose up -d
```

Abra `http://localhost:1880/ui` para o dashboard. Os fluxos são carregados de [`node-red/flows.json`](node-red/flows.json), e o Node-RED instala o pacote Dashboard declarado em [`node-red/package.json`](node-red/package.json). Os serviços ficam limitados a `127.0.0.1`; o Mosquitto usa acesso anônimo apenas para esta demonstração local. Não exponha essa configuração à rede ou à internet.

Para encerrar:

```powershell
docker compose down
```

Os fluxos assinam `cold-chain/+/telemetry`, `cold-chain/+/alarms` e `cold-chain/+/status`. O Node-RED descarta JSON inválido, valida os campos de telemetria, verifica a faixa térmica e monitora a duração de abertura da porta. O dashboard apresenta valores atuais, gráficos, estado do gateway e último alarme.

## ESP32 no Wokwi

1. Crie um projeto ESP32 no [Wokwi](https://wokwi.com/projects/new/esp32).
2. Copie [`wokwi/sketch.ino`](wokwi/sketch.ino) e [`wokwi/diagram.json`](wokwi/diagram.json) para o projeto. Cadastre as bibliotecas listadas em [`wokwi/libraries.txt`](wokwi/libraries.txt).
3. Execute a simulação e altere temperatura/umidade do DHT22 ou pressione `D` para abrir/fechar a porta.
4. O firmware de exemplo usa o broker público `broker.hivemq.com` sem TLS nem autenticação. Para integrar o Wokwi ao dashboard local, configure firmware e Node-RED para o mesmo broker acessível por ambos; o endereço `mosquitto` do Compose só é resolvido dentro da rede Docker e não é acessível diretamente pelo Wokwi. Para uso seguro e fora da demonstração, configure autenticação, TLS e um broker privado.

O status `online` é publicado após a conexão. O LWT `offline` é configurado com QoS 1 e retenção no handshake MQTT. Telemetria e alarmes são publicados sem retenção. O `PubSubClient` usado no sketch publica mensagens QoS 0; a assinatura do Node-RED solicita QoS 1, mas a entrega efetiva nunca supera o QoS oferecido pelo publicador.

## Roteiro sugerido para demonstração em vídeo

1. Apresentar a arquitetura distribuída e os tópicos MQTT.
2. Mostrar o ESP32, as leituras e o acionamento da porta no Wokwi.
3. Inspecionar no Node-RED a validação, os limiares e o fluxo de alarmes.
4. Apresentar o dashboard e os gráficos de desempenho da simulação.
5. Desconectar o nó abruptamente e observar a publicação do LWT `offline`.
6. Dividir a explicação do código e a demonstração igualmente entre os integrantes.
