from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import threading
import time
import boto3 
import sys

if hasattr(sys.stdout, 'reconfigure'):
  sys.stdout.reconfigure(line_buffering=True)
  
# Inicializar cliente SQS
sqs = boto3.client("sqs", region_name="us-east-1")

queue_name = "v2x-events"
respuesta_url = sqs.get_queue_url(QueueName=queue_name)
queue_url = respuesta_url["QueueUrl"]

# Estado global en memoria para almacenar coches y alertas de proximidad
estado_coches = {}
alertas_proximidad_activas = []
PAREJAS_NOTIFICADAS = set()  # Control para evitar spam en consola


def verificar_proximidad():
  """Compara la posición X de todos los coches registrados.

  Genera avisos si la distancia entre dos coches es menor a 100 metros.
  """
  global alertas_proximidad_activas
  alertas = []
  vehiculos = list(estado_coches.values())

  # Limpiar flag de proximidad previo en todos los coches
  for v in vehiculos:
    v["alerta_proximidad"] = False

  for i in range(len(vehiculos)):
    for j in range(i + 1, len(vehiculos)):
      v1 = vehiculos[i]
      v2 = vehiculos[j]

      distancia = abs(v1["x"] - v2["x"])

      if distancia < 100.0:
        v1["alerta_proximidad"] = True
        v2["alerta_proximidad"] = True

        alerta_info = {
            "coche1": v1["source_id"],
            "coche2": v2["source_id"],
            "distancia": round(distancia, 1),
            "mismo_sentido": v1["direction"] == v2["direction"],
        }
        alertas.append(alerta_info)

        # Imprimir en consola solo si es un evento nuevo
        pareja_key = tuple(sorted([v1["source_id"], v2["source_id"]]))
        if pareja_key not in PAREJAS_NOTIFICADAS:
          PAREJAS_NOTIFICADAS.add(pareja_key)
          print(
              f"⚠️ AVISO PROXIMIDAD: {v1['source_id']} y {v2['source_id']} están"
              f" a {distancia:.1f}m!",
              flush=True,
          )

  # Limpiar parejas notificadas que ya se han separado (> 120m)
  parejas_a_remover = set()
  for pareja in PAREJAS_NOTIFICADAS:
    if (
        pareja[0] in estado_coches
        and pareja[1] in estado_coches
        and abs(estado_coches[pareja[0]]["x"] - estado_coches[pareja[1]]["x"])
        > 120.0
    ):
      parejas_a_remover.add(pareja)

  PAREJAS_NOTIFICADAS.difference_update(parejas_a_remover)
  alertas_proximidad_activas = alertas


def consumidor_sqs():
  """Hilo en segundo plano que consume de SQS y actualiza el estado."""
  print(f"👂 Escuchando SQS en segundo plano: {queue_url}")

  while True:
    try:
      response = sqs.receive_message(
          QueueUrl=queue_url,
          MaxNumberOfMessages=10,
          WaitTimeSeconds=2,
          MessageAttributeNames=["All"],
      )

      if "Messages" in response:
        for mensaje in response["Messages"]:
          try:
            cuerpo = json.loads(mensaje["Body"])
            source_id = cuerpo.get("source_id")

            if source_id:
              location = cuerpo.get("location", {})
              payload = cuerpo.get("payload", {})
              event_type = cuerpo.get("event_type", "position")

              # 🚨 IMPRIMIR SOLO SI EL EVENTO ES DISTINTO DE "position"
              if event_type != "position":
                print(
                    f"🚨 NUEVO EVENTO [{event_type.upper()}]: Vehículo"
                    f" {source_id} en X={location.get('x', 0.0)}m",
                    flush=True,
                )
                
              estado_coches[source_id] = {
                  "source_id": source_id,
                  "x": location.get("x", 0.0),
                  "speed": payload.get("speed", 0.0),
                  "direction": payload.get("direction", "ida"),
                  "hazard": payload.get("hazard", False),
                  "event_type": cuerpo.get("event_type", "position"),
                  "last_update": datetime.now().strftime("%H:%M:%S"),
                  "alerta_proximidad": False,
              }
          except Exception as e:
            print(f"Error procesando mensaje: {e}")

          # Borrar mensaje
          sqs.delete_message(
              QueueUrl=queue_url, ReceiptHandle=mensaje["ReceiptHandle"]
          )

        # Evaluar proximidad tras actualizar posiciones
        verificar_proximidad()

    except Exception as e:
      print(f"Error en recepción SQS: {e}")

    time.sleep(0.1)


# --- PLANTILLA HTML / JS EMBEBIDA ---
HTML_DASHBOARD = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Monitor V2X - Carretera 5 km</title>
    <style>
        body { font-family: Arial, sans-serif; background: #1e1e2f; color: #fff; margin: 30px; }
        h1 { text-align: center; color: #4caf50; }
        
        .carretera-container {
            background: #2b2b3d;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 4px 10px rgba(0,0,0,0.5);
            margin-top: 20px;
        }

        .carril-label { font-weight: bold; margin-bottom: 5px; color: #aaa; }

        .carril {
            position: relative;
            height: 50px;
            background: #444;
            border-radius: 5px;
            margin-bottom: 20px;
        }

        .linea-discontinua {
            position: absolute;
            top: 50%;
            width: 100%;
            border-top: 2px dashed #888;
        }

        .coche {
            position: absolute;
            top: 10px;
            width: 30px;
            height: 30px;
            border-radius: 50%;
            background-color: #2196F3;
            color: white;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 10px;
            font-weight: bold;
            transition: left 0.5s linear, background-color 0.3s;
            transform: translateX(-50%);
            box-shadow: 0 0 8px rgba(33, 150, 243, 0.8);
        }

        /* Aviso de proximidad (< 100 m) */
        .coche.proximidad {
            background-color: #ff9800 !important;
            box-shadow: 0 0 12px #ff9800;
        }

        /* Estado de Alerta/Peligro grave */
        .coche.alerta {
            background-color: #f44336 !important;
            box-shadow: 0 0 15px #f44336;
            animation: parpadeo 0.6s infinite alternate;
        }

        @keyframes parpadeo {
            from { transform: translateX(-50%) scale(1); }
            to { transform: translateX(-50%) scale(1.3); }
        }

        .escala {
            display: flex;
            justify-content: space-between;
            color: #888;
            font-size: 12px;
            margin-top: 5px;
        }

        .panel-avisos {
            margin-top: 20px;
            padding: 15px;
            background: #3b2d1d;
            border: 1px solid #ff9800;
            border-radius: 8px;
            display: none;
        }

        .panel-avisos h3 { margin-top: 0; color: #ff9800; }

        table { width: 100%; margin-top: 20px; border-collapse: collapse; }
        th, td { padding: 10px; text-align: left; border-bottom: 1px solid #444; }
        th { background: #333; }
    </style>
</head>
<body>

    <h1>🛣️ Simulación V2X en Tiempo Real (Carretera 5 km)</h1>

    <div id="panel-avisos" class="panel-avisos">
        <h3>⚠️ AVISOS DE PROXIMIDAD DETECTADOS (&lt; 100 m)</h3>
        <ul id="lista-avisos"></ul>
    </div>

    <div class="carretera-container">
        <div class="carril-label">Sentido IDA (0 km ➔ 5 km)</div>
        <div class="carril" id="carril-ida">
            <div class="linea-discontinua"></div>
        </div>

        <div class="carril-label">Sentido VUELTA (5 km ➔ 0 km)</div>
        <div class="carril" id="carril-vuelta">
            <div class="linea-discontinua"></div>
        </div>

        <div class="escala">
            <span>0 km (0m)</span>
            <span>1.25 km</span>
            <span>2.5 km</span>
            <span>3.75 km</span>
            <span>5 km (5.000m)</span>
        </div>
    </div>

    <h2>📊 Estado de la Flota</h2>
    <table>
        <thead>
            <tr>
                <th>Vehículo</th>
                <th>Posición (X)</th>
                <th>Sentido</th>
                <th>Velocidad</th>
                <th>Estado</th>
            </tr>
        </thead>
        <tbody id="tabla-coches"></tbody>
    </table>

    <script>
        const LONGITUD_CARRETERA_M = 5000.0;

        async function actualizarSimulacion() {
            try {
                const res = await fetch('/api/data');
                const data = await res.json();
                
                const coches = data.coches;
                const alertasProximidad = data.alertas_proximidad;

                const carrilIda = document.getElementById('carril-ida');
                const carrilVuelta = document.getElementById('carril-vuelta');
                const tabla = document.getElementById('tabla-coches');
                const panelAvisos = document.getElementById('panel-avisos');
                const listaAvisos = document.getElementById('lista-avisos');

                // Renderizar avisos de proximidad
                if (alertasProximidad.length > 0) {
                    panelAvisos.style.display = 'block';
                    listaAvisos.innerHTML = alertasProximidad.map(a => 
                        `<li><b>${a.coche1}</b> y <b>${a.coche2}</b> están a solo <b>${a.distancia} metros</b> (${a.mismo_sentido ? 'Mismo sentido' : 'Sentidos opuestos'}).</li>`
                    ).join('');
                } else {
                    panelAvisos.style.display = 'none';
                }

                // Limpiar visualización previa
                carrilIda.querySelectorAll('.coche').forEach(e => e.remove());
                carrilVuelta.querySelectorAll('.coche').forEach(e => e.remove());
                tabla.innerHTML = '';

                Object.values(coches).forEach(coche => {
                    const porcentaje = Math.min(100, Math.max(0, (coche.x / LONGITUD_CARRETERA_M) * 100));

                    const cocheEl = document.createElement('div');
                    
                    // Clases CSS según estado: 'alerta' (incidencia/frenada) > 'proximidad' (<100m)
                    let claseEstado = '';
                    if (coche.hazard) {
                        claseEstado = 'alerta';
                    } else if (coche.alerta_proximidad) {
                        claseEstado = 'proximidad';
                    }

                    cocheEl.className = `coche ${claseEstado}`;
                    cocheEl.style.left = `${porcentaje}%`;
                    cocheEl.innerText = coche.source_id.replace('veh-', '');

                    if (coche.direction === 'ida') {
                        carrilIda.appendChild(cocheEl);
                    } else {
                        carrilVuelta.appendChild(cocheEl);
                    }

                    let textoEstado = coche.event_type;
                    if (coche.alerta_proximidad) {
                        textoEstado += ' ⚠️ (&lt;100m)';
                    }

                    const fila = `
                        <tr>
                            <td><b>${coche.source_id}</b></td>
                            <td>${coche.x} m</td>
                            <td>${coche.direction.toUpperCase()}</td>
                            <td>${coche.speed} km/h</td>
                            <td><span style="color: ${coche.hazard ? '#f44336' : (coche.alerta_proximidad ? '#ff9800' : '#4caf50')}">${textoEstado}</span></td>
                        </tr>
                    `;
                    tabla.innerHTML += fila;
                });
            } catch (err) {
                console.error("Error consultando la API:", err);
            }
        }

        setInterval(actualizarSimulacion, 500);
    </script>
</body>
</html>
"""


class ServidorHTTPNativo(BaseHTTPRequestHandler):

  def do_GET(self):
    if self.path in ("/api/data", "/api/coches"):
      self.send_response(200)
      self.send_header("Content-Type", "application/json")
      self.end_headers()

      respuesta = {
          "coches": estado_coches,
          "alertas_proximidad": alertas_proximidad_activas,
      }
      self.wfile.write(json.dumps(respuesta).encode("utf-8"))

    elif self.path in ("/", "/index.html"):
      self.send_response(200)
      self.send_header("Content-Type", "text/html; charset=utf-8")
      self.end_headers()
      self.wfile.write(HTML_DASHBOARD.encode("utf-8"))

    else:
      self.send_response(404)
      self.end_headers()

  def log_message(self, format, *args):
    return


if __name__ == "__main__":
  hilo_sqs = threading.Thread(target=consumidor_sqs, daemon=True)
  hilo_sqs.start()

  puerto = 5000
  httpd = HTTPServer(("", puerto), ServidorHTTPNativo)

  print(
      f"🚀 Servidor V2X con control de proximidad iniciado en:"
      f" http://localhost:{puerto}\n"
  )

  try:
    httpd.serve_forever()
  except KeyboardInterrupt:
    print("\nServidor detenido.")
