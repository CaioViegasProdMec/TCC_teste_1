from flask import Flask, render_template, jsonify
import paho.mqtt.client as mqtt
import threading
import json
from collections import deque
import time
from datetime import datetime
import pandas as pd

app = Flask(__name__)

# ============ CONFIGURAÇÕES ============
MQTT_BROKER = "localhost"
MQTT_TOPIC = "fabrica/esteira/objeto"

# Estruturas para armazenar dados
historico = deque(maxlen=100)  # Últimos 100 eventos
contagem_objetos = {}  # Contagem por tipo de objeto
ultimo_evento = None
ultima_atualizacao = None

# ============ MQTT ============
def on_message(client, userdata, msg):
    """Callback quando uma mensagem MQTT é recebida"""
    global ultimo_evento, ultima_atualizacao, contagem_objetos
    
    try:
        payload = msg.payload.decode()
        evento = json.loads(payload)
        
        # Atualiza estruturas
        evento['recebido_em'] = datetime.now().isoformat()
        historico.append(evento)
        ultimo_evento = evento
        ultima_atualizacao = datetime.now()
        
        # Atualiza contagem
        objeto = evento['objeto']
        contagem_objetos[objeto] = contagem_objetos.get(objeto, 0) + 1
        
        print(f" Dashboard recebeu: {evento['objeto']}")
        
    except Exception as e:
        print(f"Erro ao processar mensagem MQTT: {e}")

def conectar_mqtt():
    """Conecta ao broker MQTT em background"""
    client = mqtt.Client()
    client.on_message = on_message
    client.connect(MQTT_BROKER)
    client.subscribe(MQTT_TOPIC)
    client.loop_forever()

# Inicia thread do MQTT
mqtt_thread = threading.Thread(target=conectar_mqtt, daemon=True)
mqtt_thread.start()

# ============ ROTAS FLASK ============
@app.route('/')
def index():
    """Página principal"""
    return render_template('dashboard.html')

@app.route('/api/status')
def api_status():
    """API para dados em tempo real"""
    # Prepara dados para gráficos
    df = pd.DataFrame(list(historico))
    dados_grafico = {}
    
    if not df.empty:
        # Contagem por objeto para gráfico de barras
        dados_grafico['contagem'] = contagem_objetos
        
        # Timeline dos últimos eventos
        dados_grafico['timeline'] = df[['timestamp', 'objeto']].to_dict('records')
    
    return jsonify({
        'ultimo_evento': ultimo_evento,
        'ultima_atualizacao': ultima_atualizacao.isoformat() if ultima_atualizacao else None,
        'contagem': contagem_objetos,
        'total_eventos': len(historico),
        'historico': list(historico),
        'dados_grafico': dados_grafico
    })

@app.route('/api/reset')
def api_reset():
    """Reseta contagens (útil para novos experimentos)"""
    global contagem_objetos, historico
    contagem_objetos = {}
    historico.clear()
    return jsonify({'status': 'resetado'})

if __name__ == '__main__':
    print(" Dashboard do Gêmeo Digital iniciando...")
    print(" Acesse: http://localhost:5000")
    app.run(debug=True, use_reloader=False)