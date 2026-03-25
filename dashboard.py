from flask import Flask, render_template, jsonify
import paho.mqtt.client as mqtt
import threading
import json
from collections import deque
import time
from datetime import datetime
import pandas as pd
import numpy as np

app = Flask(__name__)

# ============ CONFIGURACOES ============
MQTT_BROKER = "localhost"
MQTT_TOPIC = "fabrica/esteira/objeto"
TOPIC_TEMP = "fabrica/sensor/temperatura"
TOPIC_VIB = "fabrica/sensor/vibracao"
TOPIC_QUALIDADE = "fabrica/qualidade"
TOPIC_MANUTENCAO = "fabrica/manutencao"

# ============ ESTRUTURAS DE DADOS ============
historico = deque(maxlen=200)
contagem_objetos = {}
ultimo_evento = None
ultima_atualizacao = None

# Dados para OEE
total_pecas_produzidas = 0
pecas_defeituosas = 0
tempo_operando = 0
tempo_inicio_producao = None
TEMPO_PLANEJADO = 480
PRODUCAO_TEORICA_POR_MINUTO = 2

# Dados de sensores
historico_temperatura = deque(maxlen=50)
historico_vibracao = deque(maxlen=50)
ultima_temperatura = None
ultima_vibracao = None

# Dados de manutencao
historico_falhas = deque(maxlen=50)
total_falhas = 0
tempo_medio_reparo = 0
tempo_medio_entre_falhas = 0
ultima_falha = None
ultima_manutencao = None
tempo_em_falha = 0
falha_ativa = False
tempo_inicio_falha = None

# Indicadores de qualidade
taxa_defeito_atual = 0
historico_qualidade = deque(maxlen=100)
defeitos_por_produto = {}

# Indicadores de performance
tempos_ciclo = deque(maxlen=100)

# ============ MQTT CALLBACK ============
def on_message(client, userdata, msg):
    global ultimo_evento, ultima_atualizacao, contagem_objetos
    global total_pecas_produzidas, pecas_defeituosas, tempo_operando, tempo_inicio_producao
    global ultima_temperatura, ultima_vibracao
    global total_falhas, ultima_falha, falha_ativa, tempo_inicio_falha, tempo_em_falha
    global taxa_defeito_atual, defeitos_por_produto, tempos_ciclo
    
    try:
        payload = msg.payload.decode()
        evento = json.loads(payload)
        topic = msg.topic
        
        if topic == MQTT_TOPIC:
            evento['recebido_em'] = datetime.now().isoformat()
            historico.append(evento)
            ultimo_evento = evento
            ultima_atualizacao = datetime.now()
            
            if 'produto' in evento:
                produto = evento['produto']
            else:
                produto = evento.get('objeto', 'desconhecido')
            
            contagem_objetos[produto] = contagem_objetos.get(produto, 0) + 1
            total_pecas_produzidas += 1
            
            is_defeito = evento.get('status', 'OK') != 'OK' or evento.get('is_defeito', False)
            if is_defeito:
                pecas_defeituosas += 1
                defeitos_por_produto[produto] = defeitos_por_produto.get(produto, 0) + 1
            
            if 'tempo_ciclo' in evento:
                tempos_ciclo.append(evento['tempo_ciclo'])
            
            if tempo_inicio_producao is None:
                tempo_inicio_producao = datetime.now()
            tempo_agora = datetime.now()
            tempo_operando = (tempo_agora - tempo_inicio_producao).total_seconds() / 60
            
            if total_pecas_produzidas > 0:
                taxa_defeito_atual = (pecas_defeituosas / total_pecas_produzidas) * 100
            
            print("[PRODUCAO] " + produto + " - " + ("DEFEITO" if is_defeito else "OK"))
        
        elif topic == TOPIC_TEMP:
            ultima_temperatura = evento
            historico_temperatura.append(evento)
            print("[TEMPERATURA] " + str(evento['valor']) + "C")
        
        elif topic == TOPIC_VIB:
            ultima_vibracao = evento
            historico_vibracao.append(evento)
            print("[VIBRACAO] " + str(evento['valor']) + " mm/s")
        
        elif topic == TOPIC_MANUTENCAO:
            historico_falhas.append(evento)
            
            if 'tipo' in evento and 'FALHA' in evento['tipo'].upper():
                total_falhas += 1
                ultima_falha = evento
                falha_ativa = True
                tempo_inicio_falha = time.time()
                print("[FALHA] " + evento['tipo'])
            elif 'Manutencao' in evento.get('tipo', ''):
                falha_ativa = False
                if tempo_inicio_falha:
                    tempo_parado = time.time() - tempo_inicio_falha
                    tempo_em_falha += tempo_parado
                    print("[MANUTENCAO] Realizada. Parada: " + str(round(tempo_parado, 1)) + "s")
                ultima_manutencao = evento
            
            if total_falhas > 0:
                tempo_medio_reparo = tempo_em_falha / total_falhas
            
            if total_falhas > 0 and tempo_operando > 0:
                tempo_medio_entre_falhas = (tempo_operando * 60 - tempo_em_falha) / total_falhas
        
        elif topic == TOPIC_QUALIDADE:
            historico_qualidade.append(evento)
            print("[QUALIDADE] " + evento.get('status', 'N/A'))
            
    except Exception as e:
        print("Erro ao processar mensagem MQTT: " + str(e))

# ============ FUNCAO DE CALCULO DO OEE ============
def calcular_oee():
    disponibilidade = min(1.0, tempo_operando / TEMPO_PLANEJADO) if TEMPO_PLANEJADO > 0 else 0
    
    producao_teorica = tempo_operando * PRODUCAO_TEORICA_POR_MINUTO
    performance = min(1.0, total_pecas_produzidas / producao_teorica) if producao_teorica > 0 else 0
    
    pecas_boas = total_pecas_produzidas - pecas_defeituosas
    qualidade = pecas_boas / total_pecas_produzidas if total_pecas_produzidas > 0 else 0
    
    oee = disponibilidade * performance * qualidade
    
    return {
        'oee': oee * 100,
        'disponibilidade': disponibilidade * 100,
        'performance': performance * 100,
        'qualidade': qualidade * 100,
        'total_pecas': total_pecas_produzidas,
        'pecas_defeituosas': pecas_defeituosas,
        'pecas_boas': pecas_boas,
        'tempo_operando': round(tempo_operando, 1),
        'tempo_planejado': TEMPO_PLANEJADO
    }

# ============ FUNCOES PARA INDICADORES ============
def calcular_indicadores():
    taxa_defeito = (pecas_defeituosas / total_pecas_produzidas * 100) if total_pecas_produzidas > 0 else 0
    
    if tempo_operando > 0:
        produtividade = (total_pecas_produzidas / tempo_operando) * 60
    else:
        produtividade = 0
    
    tempo_medio_ciclo = np.mean(tempos_ciclo) if tempos_ciclo else 0
    
    temps = [t['valor'] for t in historico_temperatura if 'valor' in t]
    temp_media = np.mean(temps) if temps else 0
    temp_max = np.max(temps) if temps else 0
    
    vibs = [v['valor'] for v in historico_vibracao if 'valor' in v]
    vib_media = np.mean(vibs) if vibs else 0
    vib_max = np.max(vibs) if vibs else 0
    
    mtbf = tempo_medio_entre_falhas if total_falhas > 0 else 0
    mttr = tempo_medio_reparo if total_falhas > 0 else 0
    
    top_defeitos = sorted(defeitos_por_produto.items(), key=lambda x: x[1], reverse=True)[:5]
    
    return {
        'taxa_defeito': round(taxa_defeito, 2),
        'produtividade': round(produtividade, 1),
        'tempo_medio_ciclo': round(tempo_medio_ciclo, 2),
        'temperatura': {
            'atual': ultima_temperatura['valor'] if ultima_temperatura else 0,
            'media': round(temp_media, 1),
            'maxima': round(temp_max, 1)
        },
        'vibracao': {
            'atual': ultima_vibracao['valor'] if ultima_vibracao else 0,
            'media': round(vib_media, 2),
            'maxima': round(vib_max, 2)
        },
        'manutencao': {
            'total_falhas': total_falhas,
            'mtbf': round(mtbf, 1),
            'mttr': round(mttr, 1),
            'falha_ativa': falha_ativa,
            'ultima_falha': ultima_falha
        },
        'top_defeitos': top_defeitos,
        'alertas': {
            'temperatura': ultima_temperatura['valor'] > 100 if ultima_temperatura else False,
            'vibracao': ultima_vibracao['valor'] > 10 if ultima_vibracao else False,
            'defeito_alto': taxa_defeito > 10
        }
    }

# ============ THREAD MQTT ============
def conectar_mqtt():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_message = on_message
    client.connect(MQTT_BROKER)
    
    client.subscribe(MQTT_TOPIC)
    client.subscribe(TOPIC_TEMP)
    client.subscribe(TOPIC_VIB)
    client.subscribe(TOPIC_QUALIDADE)
    client.subscribe(TOPIC_MANUTENCAO)
    
    client.loop_forever()

mqtt_thread = threading.Thread(target=conectar_mqtt, daemon=True)
mqtt_thread.start()

# ============ ROTAS FLASK ============
@app.route('/')
def index():
    return render_template('dashboard.html')

@app.route('/api/status')
def api_status():
    df = pd.DataFrame(list(historico))
    dados_grafico = {}
    
    if not df.empty:
        dados_grafico['contagem'] = contagem_objetos
        coluna_nome = 'objeto' if 'objeto' in df.columns else 'produto'
        dados_grafico['timeline'] = df[['timestamp', coluna_nome]].to_dict('records')
    
    return jsonify({
        'ultimo_evento': ultimo_evento,
        'ultima_atualizacao': ultima_atualizacao.isoformat() if ultima_atualizacao else None,
        'contagem': contagem_objetos,
        'total_eventos': len(historico),
        'historico': list(historico),
        'dados_grafico': dados_grafico
    })

@app.route('/api/oee')
def api_oee():
    oee_data = calcular_oee()
    return jsonify(oee_data)

@app.route('/api/indicadores')
def api_indicadores():
    indicadores = calcular_indicadores()
    return jsonify(indicadores)

@app.route('/api/sensores')
def api_sensores():
    return jsonify({
        'temperatura': list(historico_temperatura),
        'vibracao': list(historico_vibracao),
        'falhas': list(historico_falhas)
    })

@app.route('/api/reset')
def api_reset():
    global contagem_objetos, historico, total_pecas_produzidas, pecas_defeituosas
    global tempo_operando, tempo_inicio_producao, defeitos_por_produto, tempos_ciclo
    global total_falhas, tempo_em_falha, historico_falhas
    
    contagem_objetos = {}
    historico.clear()
    total_pecas_produzidas = 0
    pecas_defeituosas = 0
    tempo_operando = 0
    tempo_inicio_producao = None
    defeitos_por_produto = {}
    tempos_ciclo.clear()
    total_falhas = 0
    tempo_em_falha = 0
    historico_falhas.clear()
    
    return jsonify({'status': 'resetado'})

if __name__ == '__main__':
    print("Dashboard do Gemeo Digital iniciando...")
    print("Acesse: http://localhost:5000")
    print("Inscrito nos topicos:")
    print("  - " + MQTT_TOPIC)
    print("  - " + TOPIC_TEMP)
    print("  - " + TOPIC_VIB)
    print("  - " + TOPIC_QUALIDADE)
    print("  - " + TOPIC_MANUTENCAO)
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)