import cv2
import numpy as np
from ultralytics import YOLO
import paho.mqtt.client as mqtt
import json
import time
from datetime import datetime

# ============ CONFIGURACOES ============
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_TOPIC = "fabrica/esteira/objeto"

# Dicionario para mapear objetos YOLO para produtos industriais
# Isso ajuda a integrar com o simulador que usa nomes de produtos da WEG
MAPEAMENTO_PRODUTOS = {
    "bottle": "Motor_W22_10CV",
    "cup": "Motor_W22_15CV",
    "book": "Inversor_CFW500",
    "cell phone": "Sensor_Temperatura_PT100",
    "apple": "Contador_Eletrico",
    "banana": "Soft_Starter_SW3000",
    "orange": "Motor_W22_20CV",
    "mouse": "Inversor_CFW900",
    "keyboard": "Motor_W22_10CV"
}

# Inicializa o modelo YOLO
model = YOLO('yolov8n.pt')

# Dicionario para rastrear objetos ja detectados
tempo_ultima_deteccao = {}
DETECTION_COOLDOWN = 2

# ============ MQTT ============
def conectar_mqtt():
    """Conecta ao broker MQTT"""
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        print("Conectado ao MQTT broker em " + MQTT_BROKER + ":" + str(MQTT_PORT))
        return client
    except Exception as e:
        print("Erro ao conectar MQTT: " + str(e))
        return None

def publicar_evento(client, produto, confianca, objeto_original):
    """Publica a deteccao no MQTT no formato esperado pelo dashboard"""
    if client is None:
        return
    
    # Gera um status baseado na confianca (simula qualidade)
    if confianca > 0.85:
        status = "OK"
    elif confianca > 0.7:
        status = "OK"
    else:
        status = "Falha_Isolamento"
    
    evento = {
        "timestamp": datetime.now().isoformat(),
        "produto": produto,
        "objeto_original": objeto_original,
        "status": status,
        "confianca": round(float(confianca), 2),
        "tempo_ciclo": round(2.0 + (1 - confianca) * 2, 2),
        "estacao": "Inspecao_Qualidade",
        "is_defeito": status != "OK",
        "id": produto + "_" + str(int(time.time()))
    }
    
    client.publish(MQTT_TOPIC, json.dumps(evento))
    
    status_texto = "DEFEITO" if evento["is_defeito"] else "OK"
    print("[PERCEPCAO] " + produto + " - " + status_texto + " (conf: " + str(round(confianca, 2)) + ")")

# ============ PROCESSAMENTO ============
def processar_frame(frame, client):
    """Processa um frame da webcam e publica deteccoes"""
    results = model(frame, verbose=False)
    
    for r in results:
        boxes = r.boxes
        if boxes is not None:
            for box in boxes:
                cls = int(box.cls[0])
                conf = float(box.conf[0])
                nome_classe = model.names[cls]
                
                objetos_uteis = list(MAPEAMENTO_PRODUTOS.keys())
                
                if nome_classe in objetos_uteis and conf > 0.5:
                    chave = f"{nome_classe}_{int(box.xyxy[0][0])}"
                    agora = time.time()
                    
                    if chave not in tempo_ultima_deteccao or \
                       (agora - tempo_ultima_deteccao[chave]) > DETECTION_COOLDOWN:
                        tempo_ultima_deteccao[chave] = agora
                        
                        produto = MAPEAMENTO_PRODUTOS[nome_classe]
                        publicar_evento(client, produto, conf, nome_classe)
                        
                        x1, y1, x2, y2 = box.xyxy[0]
                        cv2.rectangle(frame, (int(x1), int(y1)), 
                                     (int(x2), int(y2)), (0, 255, 0), 2)
                        
                        texto = f"{produto} {conf:.2f}"
                        cv2.putText(frame, texto, 
                                   (int(x1), int(y1)-10), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0), 2)
    
    return frame

# ============ FUNCAO PARA SIMULAR QUANDO NAO HA WEBCAM ============
def modo_simulacao():
    """Modo simulacao para quando nao ha webcam disponivel"""
    print("Modo simulacao ativado - gerando deteccoes aleatorias")
    
    produtos = list(MAPEAMENTO_PRODUTOS.values())
    objetos = list(MAPEAMENTO_PRODUTOS.keys())
    intervalo = 2.0
    
    try:
        while True:
            indice = random.randint(0, len(produtos) - 1)
            produto = produtos[indice]
            objeto_original = objetos[indice]
            confianca = random.uniform(0.65, 0.95)
            
            print("[SIMULACAO] Gerando " + produto)
            publicar_evento(mqtt_client, produto, confianca, objeto_original)
            
            time.sleep(intervalo)
            
    except KeyboardInterrupt:
        print("Simulacao interrompida")

# ============ WEBCAM REAL ============
def webcam_real():
    """Tenta acessar a webcam real"""
    print("Tentando acessar webcam real...")
    
    cap = None
    for idx in [0, 1, 2]:
        for backend in [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]:
            try:
                cap = cv2.VideoCapture(idx, backend)
                if cap.isOpened():
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        print("Webcam encontrada no indice " + str(idx) + " com backend " + str(backend))
                        return cap
            except:
                pass
        if cap:
            cap.release()
    
    print("Nenhuma webcam encontrada")
    return None

# ============ MAIN ============
def main():
    global mqtt_client
    
    print("Iniciando sistema de percepcao do Gemeo Digital")
    
    mqtt_client = conectar_mqtt()
    
    cap = webcam_real()
    
    if cap is None:
        print("Webcam nao encontrada. Ativando modo simulacao...")
        modo_simulacao()
        return
    
    print("Webcam ativa. Pressione 'q' para sair.")
    
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("Falha ao capturar frame")
                break
            
            frame_processado = processar_frame(frame, mqtt_client)
            cv2.imshow('Percepcao - Gemeo Digital', frame_processado)
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    
    except KeyboardInterrupt:
        print("Interrompido pelo usuario")
    
    finally:
        cap.release()
        cv2.destroyAllWindows()
        if mqtt_client:
            mqtt_client.disconnect()
        print("Sistema encerrado")

if __name__ == "__main__":
    main()