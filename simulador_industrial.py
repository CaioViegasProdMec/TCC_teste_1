#!/usr/bin/env python3
"""
Simulador Industrial - Gêmeo Digital
Simula sensores de uma linha de produção com dados realistas
Pensado para integracao com a WEG
"""

import random
import time
import json
import paho.mqtt.client as mqtt
from datetime import datetime
import threading

# ============ CONFIGURACOES ============
MQTT_BROKER = "localhost"
MQTT_PORT = 1883

# Topic MQTT (cada um representa um sensor diferente)
TOPIC_ESTEIRA = "fabrica/esteira/objeto"
TOPIC_SENSOR_TEMP = "fabrica/sensor/temperatura"
TOPIC_SENSOR_VIB = "fabrica/sensor/vibracao"
TOPIC_QUALIDADE = "fabrica/qualidade"
TOPIC_MANUTENCAO = "fabrica/manutencao"

# ============ DADOS INDUSTRIAIS ============
# Produtos da WEG (simulados)
produtos_weg = [
    "Motor_W22_10CV",
    "Motor_W22_15CV", 
    "Motor_W22_20CV",
    "Inversor_CFW500",
    "Inversor_CFW900",
    "Soft_Starter_SW3000",
    "Contador_Eletrico",
    "Sensor_Temperatura_PT100"
]

# Defeitos possiveis com probabilidades
defeitos = {
    "OK": 0.85,
    "Falha_Isolamento": 0.05,
    "Falha_Rolamento": 0.04,
    "Vibracao_Excessiva": 0.03,
    "Superaquecimento": 0.02,
    "Falha_Comunicacao": 0.01
}

# Estacoes de producao
estacoes = [
    "Montagem",
    "Bobinagem",
    "Inspecao_Qualidade",
    "Teste_Funcional",
    "Embalagem"
]

# ============ ESTATISTICAS GLOBAIS ============
total_produzido = 0
total_defeitos = 0
historico_producao = []
falhas_por_estacao = {estacao: 0 for estacao in estacoes}
tempos_ciclo = []

# ============ SIMULACAO DE FALHAS E MANUTENCAO ============
falha_ativa = False
tempo_inicio_falha = None
tempo_ultima_falha = None
tempo_ultima_manutencao = None
total_falhas = 0
total_tempo_parado = 0

# ============ CLIENTE MQTT ============
def conectar_mqtt():
    """Conecta ao broker MQTT"""
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        print("Conectado ao MQTT broker em " + MQTT_BROKER + ":" + str(MQTT_PORT))
        return client
    except Exception as e:
        print("Erro ao conectar MQTT: " + str(e))
        return None

def publicar(client, topic, data):
    """Publica dados no MQTT"""
    if client:
        client.publish(topic, json.dumps(data))

# ============ GERADOR DE DADOS DE SENSORES ============
def gerar_temperatura():
    """Gera temperatura simulada do motor (normal: 40-80C, falha: >100C)"""
    if falha_ativa and random.random() < 0.3:
        return random.uniform(100, 150)
    else:
        return random.uniform(40, 80)

def gerar_vibracao():
    """Gera vibracao simulada (normal: 0-5mm/s, falha: >10mm/s)"""
    if falha_ativa and random.random() < 0.2:
        return random.uniform(10, 25)
    else:
        return random.uniform(0, 5)

def gerar_produto():
    """Gera um produto aleatorio da linha"""
    return random.choice(produtos_weg)

def gerar_status_qualidade():
    """Gera status de qualidade baseado nas probabilidades"""
    sorteio = random.random()
    acumulado = 0
    for defeito, prob in defeitos.items():
        acumulado += prob
        if sorteio <= acumulado:
            return defeito

def gerar_tempo_ciclo():
    """Gera tempo de ciclo baseado na complexidade do produto"""
    return random.uniform(1.5, 4.0)

# ============ SIMULACAO DE FALHAS ============
def verificar_e_gerar_falha():
    """Verifica se deve gerar uma falha aleatoria na linha"""
    global falha_ativa, tempo_inicio_falha, total_falhas, tempo_ultima_falha
    
    if not falha_ativa and random.random() < 0.02:
        falha_ativa = True
        tempo_inicio_falha = time.time()
        tempo_ultima_falha = datetime.now().isoformat()
        total_falhas += 1
        
        tipos_falha = [
            "Superaquecimento do motor",
            "Vibracao excessiva no eixo",
            "Falha no inversor de frequencia",
            "Quebra do rolamento",
            "Falha no sistema de refrigeracao",
            "Desalinhamento da esteira"
        ]
        falha_escolhida = random.choice(tipos_falha)
        
        print("FALHA DETECTADA: " + falha_escolhida)
        
        return {
            "tipo": falha_escolhida,
            "timestamp": datetime.now().isoformat(),
            "severidade": random.choice(["Alta", "Media", "Critica"]),
            "estacao": random.choice(estacoes)
        }
    return None

def verificar_recuperacao_falha():
    """Verifica se a falha foi corrigida"""
    global falha_ativa, tempo_inicio_falha, total_tempo_parado, tempo_ultima_manutencao
    
    if falha_ativa:
        tempo_falha = time.time() - tempo_inicio_falha
        if tempo_falha > random.uniform(5, 30):
            falha_ativa = False
            total_tempo_parado += tempo_falha
            tempo_ultima_manutencao = datetime.now().isoformat()
            print("Falha corrigida apos " + str(round(tempo_falha, 1)) + " segundos")
            return True
    return False

# ============ LOOP PRINCIPAL DO SIMULADOR ============
def simular_producao():
    """Loop principal que simula a producao continua"""
    global total_produzido, total_defeitos, tempos_ciclo, historico_producao
    
    print("SIMULADOR INDUSTRIAL INICIADO")
    print("Simulando linha de producao da WEG...")
    print("Pressione Ctrl+C para parar")
    print("-" * 50)
    
    mqtt_client = conectar_mqtt()
    
    ultimo_tempo_temp = time.time()
    ultimo_tempo_vib = time.time()
    intervalo_sensores = 2.0
    
    try:
        while True:
            tempo_atual = time.time()
            
            if not falha_ativa:
                tempo_ciclo = gerar_tempo_ciclo()
                time.sleep(tempo_ciclo)
                
                produto = gerar_produto()
                status = gerar_status_qualidade()
                estacao_atual = random.choice(estacoes)
                
                total_produzido += 1
                tempos_ciclo.append(tempo_ciclo)
                
                is_defeito = status != "OK"
                if is_defeito:
                    total_defeitos += 1
                    falhas_por_estacao[estacao_atual] += 1
                
                evento = {
                    "timestamp": datetime.now().isoformat(),
                    "produto": produto,
                    "status": status,
                    "tempo_ciclo": round(tempo_ciclo, 2),
                    "estacao": estacao_atual,
                    "is_defeito": is_defeito,
                    "id": produto + "_" + str(total_produzido)
                }
                
                historico_producao.append(evento)
                if len(historico_producao) > 100:
                    historico_producao.pop(0)
                
                publicar(mqtt_client, TOPIC_ESTEIRA, evento)
                
                if is_defeito:
                    publicar(mqtt_client, TOPIC_QUALIDADE, evento)
                
                status_icon = "OK" if not is_defeito else "DEFEITO"
                print("[" + str(total_produzido) + "] " + produto + " - " + status + " - Ciclo: " + str(round(tempo_ciclo, 2)) + "s - " + estacao_atual)
                
            else:
                print("[PARADA] Falha ativa - Aguardando manutencao...")
                time.sleep(2)
            
            if tempo_atual - ultimo_tempo_temp >= intervalo_sensores:
                temp = gerar_temperatura()
                publicar(mqtt_client, TOPIC_SENSOR_TEMP, {
                    "timestamp": datetime.now().isoformat(),
                    "valor": round(temp, 1),
                    "unidade": "C",
                    "alerta": temp > 100
                })
                ultimo_tempo_temp = tempo_atual
                
                if temp > 100:
                    print("ALERTA: Temperatura alta! " + str(round(temp, 1)) + "C")
            
            if tempo_atual - ultimo_tempo_vib >= intervalo_sensores:
                vib = gerar_vibracao()
                publicar(mqtt_client, TOPIC_SENSOR_VIB, {
                    "timestamp": datetime.now().isoformat(),
                    "valor": round(vib, 2),
                    "unidade": "mm/s",
                    "alerta": vib > 10
                })
                ultimo_tempo_vib = tempo_atual
                
                if vib > 10:
                    print("ALERTA: Vibracao excessiva! " + str(round(vib, 1)) + " mm/s")
            
            if not falha_ativa:
                falha_info = verificar_e_gerar_falha()
                if falha_info:
                    publicar(mqtt_client, TOPIC_MANUTENCAO, falha_info)
            
            if falha_ativa:
                if verificar_recuperacao_falha():
                    publicar(mqtt_client, TOPIC_MANUTENCAO, {
                        "tipo": "Manutencao_Realizada",
                        "timestamp": datetime.now().isoformat(),
                        "tempo_parado": round(time.time() - tempo_inicio_falha, 1)
                    })
                    
    except KeyboardInterrupt:
        print("\n" + "="*50)
        print("ESTATISTICAS FINAIS DO SIMULADOR")
        print("Total produzido: " + str(total_produzido))
        print("Total defeitos: " + str(total_defeitos))
        if total_produzido > 0:
            taxa = (total_defeitos / total_produzido) * 100
            print("Taxa de defeito: " + str(round(taxa, 1)) + "%")
        print("Total falhas: " + str(total_falhas))
        print("Tempo total parado: " + str(round(total_tempo_parado, 1)) + "s")
        print("="*50)
        print("Simulador encerrado")

if __name__ == "__main__":
    simular_producao()