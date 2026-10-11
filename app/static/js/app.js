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
