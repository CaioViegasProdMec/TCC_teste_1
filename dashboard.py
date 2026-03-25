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

# ============ NOVAS CONFIGURAÇÕES PARA OEE ============
# Adicione estas variáveis após as configurações existentes

# Parâmetros da fábrica (você pode ajustar conforme sua simulação)
TEMPO_PLANEJADO = 480  # minutos por dia (8 horas)
PRODUCAO_TEORICA_POR_MINUTO = 2  # peças por minuto (ajuste conforme seu cenário)

# Variáveis para cálculo do OEE
tempo_operando = 0  # minutos
tempo_inicio_producao = None
total_pecas_produzidas = 0
pecas_defeituosas = 0
historico_oee = deque(maxlen=100)  # Guarda histórico do OEE

# ============ MQTT ============
def on_message(client, userdata, msg):
    """Callback quando uma mensagem MQTT é recebida"""
    global ultimo_evento, ultima_atualizacao, contagem_objetos
    global total_pecas_produzidas, pecas_defeituosas, tempo_operando, tempo_inicio_producao  # NOVAS VARIÁVEIS
    
    try:
        payload = msg.payload.decode()
        evento = json.loads(payload)
        
        # Atualiza estruturas existentes
        evento['recebido_em'] = datetime.now().isoformat()
        historico.append(evento)
        ultimo_evento = evento
        ultima_atualizacao = datetime.now()
        
        # ============ NOVO: ATUALIZA MÉTRICAS DE PRODUÇÃO ============
        objeto = evento['objeto']
        
        # Conta peças produzidas
        total_pecas_produzidas += 1
        
        # Verifica se é uma peça com defeito (exemplo: se o objeto for detectado como "defeito")
        # Você pode adaptar essa lógica conforme seu cenário
        # Por exemplo, se você tiver um objeto "defeito" ou uma propriedade no evento
        if 'status' in evento and evento['status'] == 'Falha':
            pecas_defeituosas += 1
        
        # Atualiza contagem normal
        contagem_objetos[objeto] = contagem_objetos.get(objeto, 0) + 1
        
        # Controla tempo de produção (inicia quando primeira peça chega)
        if tempo_inicio_producao is None:
            tempo_inicio_producao = datetime.now()
        
        # Atualiza tempo operando (minutos desde o início)
        tempo_agora = datetime.now()
        tempo_operando = (tempo_agora - tempo_inicio_producao).total_seconds() / 60
        
        print(f"Dashboard recebeu: {evento['objeto']}")
        print(f"Produção total: {total_pecas_produzidas} | Defeitos: {pecas_defeituosas}")
        
    except Exception as e:
        print(f"Erro ao processar mensagem MQTT: {e}")

def calcular_oee():
    """Calcula os indicadores OEE (Overall Equipment Effectiveness)"""
    global total_pecas_produzidas, pecas_defeituosas, tempo_operando
    
    # 1. Disponibilidade = Tempo operando / Tempo planejado
    disponibilidade = min(1.0, tempo_operando / TEMPO_PLANEJADO) if TEMPO_PLANEJADO > 0 else 0
    
    # 2. Performance = Produção real / Produção teórica
    producao_teorica = tempo_operando * PRODUCAO_TEORICA_POR_MINUTO
    performance = min(1.0, total_pecas_produzidas / producao_teorica) if producao_teorica > 0 else 0
    
    # 3. Qualidade = Peças boas / Total peças
    pecas_boas = total_pecas_produzidas - pecas_defeituosas
    qualidade = pecas_boas / total_pecas_produzidas if total_pecas_produzidas > 0 else 0
    
    # 4. OEE = Disponibilidade × Performance × Qualidade
    oee = disponibilidade * performance * qualidade
    
    # Registra no histórico
    historico_oee.append({
        'timestamp': datetime.now().isoformat(),
        'oee': oee * 100,  # Em porcentagem
        'disponibilidade': disponibilidade * 100,
        'performance': performance * 100,
        'qualidade': qualidade * 100
    })
    
    return {
        'oee': oee * 100,
        'disponibilidade': disponibilidade * 100,
        'performance': performance * 100,
        'qualidade': qualidade * 100,
        'total_pecas': total_pecas_produzidas,
        'pecas_defeituosas': pecas_defeituosas,
        'pecas_boas': pecas_boas,
        'tempo_operando': round(tempo_operando, 1),
        'tempo_planejado': TEMPO_PLANEJADO,
        'historico': list(historico_oee)
    }


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
    # Procurar aquivo dashboard.html
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
        dados_grafico['timeline'] = df[['timestamp', 'objeto']].to_dict('records')      # conversão para listas de dicionários
    
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
    """Retorna os indicadores OEE"""
    oee_data = calcular_oee()
    return jsonify(oee_data)

@app.route('/api/reset')
def api_reset():
    """Reseta contagens (útil para novos experimentos)"""
    global contagem_objetos, historico, total_pecas_produzidas, pecas_defeituosas
    global tempo_operando, tempo_inicio_producao, historico_oee
    
    contagem_objetos = {}
    historico.clear()
    total_pecas_produzidas = 0
    pecas_defeituosas = 0
    tempo_operando = 0
    tempo_inicio_producao = None
    historico_oee.clear()
    
    return jsonify({'status': 'resetado'})


if __name__ == '__main__':
    print(" Dashboard do Gêmeo Digital iniciando...")
    print(" Acesse: http://localhost:5000")
    app.run(debug=True, use_reloader=False)