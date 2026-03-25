# simulador_sensores.py
import random
import time
import json
import paho.mqtt.client as mqtt

MQTT_BROKER = "localhost"

tipos_pecas = ["Motor_100CV", "Motor_50CV", "Motor_25CV", "Inversor"]
qualidade = ["OK", "OK", "OK", "Falha"]  # 75% OK, 25% Falha

client = mqtt.Client()
client.connect(MQTT_BROKER)

while True:
    peca = random.choice(tipos_pecas)
    status = random.choices(qualidade, weights=[75, 25])[0]
    
    evento = {
        "timestamp": time.time(),
        "peca": peca,
        "status": status,
        "estacao": "Inspecao_Qualidade"
    }
    
    client.publish("fabrica/qualidade", json.dumps(evento))
    print(f"{evento}")
    
    time.sleep(random.uniform(1, 3))