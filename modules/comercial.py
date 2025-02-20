import streamlit as st
import folium
from folium.plugins import MarkerCluster
import pandas as pd
import sqlite3
import os
import re
from streamlit_folium import st_folium
import streamlit.components.v1 as components
import time
from datetime import datetime
from modules import login

def log_trazabilidad(usuario, accion, detalles):
    """Inserta un registro en la tabla de trazabilidad."""
    conn = sqlite3.connect("data/usuarios.db")  # Usamos la misma base de datos de usuarios
    cursor = conn.cursor()
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT INTO trazabilidad (usuario_id, accion, detalles, fecha)
        VALUES (?, ?, ?, ?)
    """, (usuario, accion, detalles, fecha))
    conn.commit()
    conn.close()

def guardar_en_base_de_datos(oferta_data, imagen_incidencia):
    """Guarda la oferta en SQLite y almacena la imagen si es necesario."""
    try:
        conn = sqlite3.connect("data/usuarios.db")
        cursor = conn.cursor()
        # Crear tabla ofertas_comercial si no existe, definiendo apartment_id como PRIMARY KEY
        cursor.execute('''CREATE TABLE IF NOT EXISTS ofertas_comercial (
                            apartment_id TEXT PRIMARY KEY,
                            provincia TEXT,
                            municipio TEXT,
                            poblacion TEXT,
                            vial TEXT,
                            numero TEXT,
                            letra TEXT,
                            cp TEXT,
                            latitud REAL,
                            longitud REAL,
                            nombre_cliente TEXT,
                            telefono TEXT,
                            direccion_alternativa TEXT,
                            observaciones TEXT,
                            serviciable TEXT,
                            motivo_serviciable TEXT,
                            incidencia TEXT,
                            motivo_incidencia TEXT,
                            fichero_imagen TEXT,
                            fecha TEXT
                        )''')

        # Verificar si ya existe un registro con el mismo apartment_id
        cursor.execute("SELECT COUNT(*) FROM ofertas_comercial WHERE apartment_id = ?", (oferta_data["Apartment ID"],))
        if cursor.fetchone()[0] > 0:
            st.error("❌ Ya existe una oferta registrada con este Apartment ID.")
            conn.close()
            return

        # Guardar la imagen si hay incidencia
        imagen_path = None
        if oferta_data["incidencia"] == "Sí" and imagen_incidencia:
            # Extraemos la extensión del archivo subido
            extension = os.path.splitext(imagen_incidencia.name)[1]
            imagen_path = f"data/incidencias/{oferta_data['Apartment ID']}{extension}"
            os.makedirs(os.path.dirname(imagen_path), exist_ok=True)
            with open(imagen_path, "wb") as f:
                f.write(imagen_incidencia.getbuffer())

        # Insertar datos en la base de datos
        cursor.execute('''INSERT INTO ofertas_comercial (
                            apartment_id, provincia, municipio, poblacion, vial, numero, letra, cp, latitud, longitud,
                            nombre_cliente, telefono, direccion_alternativa, observaciones, serviciable,
                            motivo_serviciable, incidencia, motivo_incidencia, fichero_imagen, fecha
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                       (
                           oferta_data["Apartment ID"],
                           oferta_data["Provincia"],
                           oferta_data["Municipio"],
                           oferta_data["Población"],
                           oferta_data["Vial"],
                           oferta_data["Número"],
                           oferta_data["Letra"],
                           oferta_data["Código Postal"],
                           oferta_data["Latitud"],
                           oferta_data["Longitud"],
                           oferta_data["Nombre Cliente"],
                           oferta_data["Teléfono"],
                           oferta_data["Dirección Alternativa"],
                           oferta_data["Observaciones"],
                           oferta_data["serviciable"],
                           oferta_data["motivo_serviciable"],
                           oferta_data["incidencia"],
                           oferta_data["motivo_incidencia"],
                           imagen_path,
                           oferta_data["fecha"].strftime('%Y-%m-%d %H:%M:%S')
                       ))

        conn.commit()
        conn.close()
        st.success("✅ ¡Oferta enviada y guardada en la base de datos con éxito!")
        # Registrar trazabilidad del guardado de la oferta
        log_trazabilidad(st.session_state["username"], "Guardar Oferta",
                         f"Oferta guardada para Apartment ID: {oferta_data['Apartment ID']}")
    except Exception as e:
        st.error(f"❌ Error al guardar la oferta en la base de datos: {e}")

def comercial_dashboard():
    """Muestra el mapa con los puntos asignados al comercial logueado usando folium."""
    st.title("📍 Mapa de Ubicaciones")

    # Mostrar el ícono de usuario centrado y más grande en la barra lateral
    st.sidebar.markdown("""
            <style>
                .user-circle {
                    width: 100px;
                    height: 100px;
                    border-radius: 50%;
                    background-color: #ff7f00;
                    color: white;
                    font-size: 50px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin-bottom: 30px;
                    text-align: center;
                    margin-left: auto;
                    margin-right: auto;
                }
            </style>
            <div class="user-circle">👤</div>
            <div>Rol: Comercial</div>
            """, unsafe_allow_html=True)

    st.sidebar.write(f"Bienvenido, {st.session_state['username']}")

    # Verificar si el usuario está logueado
    if "username" not in st.session_state:
        st.warning("⚠️ No has iniciado sesión. Por favor, inicia sesión para continuar.")
        time.sleep(2)
        login.login()
        return

    comercial = st.session_state.get("username")

    # Registrar trazabilidad de la visualización del dashboard
    log_trazabilidad(comercial, "Visualización de Dashboard",
                     "El comercial visualizó el mapa de ubicaciones.")

    # Botón de Cerrar Sesión en la barra lateral
    if st.sidebar.button("Cerrar Sesión"):
        cerrar_sesion()

    with st.spinner("⏳ Cargando los datos del comercial..."):
        try:
            conn = sqlite3.connect("data/usuarios.db")
            query_tables = "SELECT name FROM sqlite_master WHERE type='table';"
            tables = pd.read_sql(query_tables, conn)
            if 'datos_uis' not in tables['name'].values:
                st.error("❌ La tabla 'datos_uis' no se encuentra en la base de datos.")
                conn.close()
                return

            query = "SELECT * FROM datos_uis WHERE LOWER(COMERCIAL) = LOWER(?)"
            df = pd.read_sql(query, conn, params=(comercial,))
            conn.close()

            if df.empty:
                st.warning("⚠️ No hay datos asignados a este comercial.")
                return
        except Exception as e:
            st.error(f"❌ Error al cargar los datos de la base de datos: {e}")
            return

    if not isinstance(df, pd.DataFrame):
        st.error("❌ Los datos no se cargaron correctamente.")
        return

    for col in ['latitud', 'longitud', 'address_id']:
        if col not in df.columns:
            st.error(f"❌ No se encuentra la columna '{col}'.")
            return

    if "clicks" not in st.session_state:
        st.session_state.clicks = []

    location = get_user_location()
    if location is None:
        st.warning("❌ No se pudo obtener la ubicación. Cargando el mapa en la ubicación predeterminada.")
        lat, lon = 43.463444, -3.790476  # Ubicación predeterminada
    else:
        lat, lon = location

    with st.spinner("⏳ Cargando mapa..."):
        m = folium.Map(location=[lat, lon], zoom_start=12, tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
                       attr="Google")
        marker_cluster = MarkerCluster().add_to(m)
        for _, row in df.iterrows():
            popup_text = f"🏠 {row['address_id']} - 📍 {row['latitud']}, {row['longitud']}"
            folium.Marker(
                location=[row['latitud'], row['longitud']],
                popup=popup_text,
                icon=folium.Icon(color='blue', icon='info-sign')
            ).add_to(marker_cluster)
        map_data = st_folium(m, height=500, width=700)

    if map_data and "last_object_clicked" in map_data and map_data["last_object_clicked"]:
        st.session_state.clicks.append(map_data["last_object_clicked"])

    if st.session_state.clicks:
        last_click = st.session_state.clicks[-1]
        lat = last_click.get("lat", "")
        lon = last_click.get("lng", "")

        if lat and lon:
            google_maps_link = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"

            st.markdown(f"""
                <div style="text-align: center; margin: 5px 0;">
                    <a href="{google_maps_link}" target="_blank" style="
                        background-color: #0078ff;
                        color: white;
                        padding: 6px 12px;
                        font-size: 14px;
                        font-weight: bold;
                        border-radius: 6px;
                        text-decoration: none;
                        display: inline-flex;
                        align-items: center;
                        gap: 6px;
                    ">
                        🗺️ Ver en Google Maps
                    </a>
                </div>
            """, unsafe_allow_html=True)

        with st.spinner("⏳ Cargando formulario..."):
            mostrar_formulario(last_click)
def get_user_location():
    """Obtiene la ubicación del usuario a través de un componente de JavaScript y pasa la ubicación a Python."""
    html_code = """
        <script>
            if (navigator.geolocation) {
                navigator.geolocation.getCurrentPosition(function(position) {
                    var lat = position.coords.latitude;
                    var lon = position.coords.longitude;
                    window.parent.postMessage({lat: lat, lon: lon}, "*");
                }, function() {
                    alert("No se pudo obtener la ubicación del dispositivo.");
                });
            } else {
                alert("Geolocalización no soportada por este navegador.");
            }
        </script>
    """
    components.html(html_code, height=0, width=0)
    if "lat" in st.session_state and "lon" in st.session_state:
        lat = st.session_state["lat"]
        lon = st.session_state["lon"]
        return lat, lon
    return None

def cerrar_sesion():
    """Función para cerrar la sesión y limpiar el estado."""
    log_trazabilidad(st.session_state["username"], "Cierre sesión",
                     f"El comercial {st.session_state['username']} cerró sesión.")
    del st.session_state["username"]
    if "clicks" in st.session_state:
        del st.session_state["clicks"]
    st.success("✅ Has cerrado sesión correctamente.")
    st.warning("👉 Por favor, inicia sesión nuevamente.")
    time.sleep(2)
    login.login()

def validar_email(email):
    return re.match(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)

def mostrar_formulario(click_data):
    """Muestra un formulario con los datos correspondientes a las coordenadas seleccionadas."""
    st.subheader("📄 Enviar Oferta")
    popup_text = click_data.get("popup", "")
    apartment_id = popup_text.split(" - ")[0] if " - " in popup_text else "N/D"
    lat_value = click_data.get("lat", "N/D")
    lng_value = click_data.get("lng", "N/D")

    try:
        conn = sqlite3.connect("data/usuarios.db")
        query = """
            SELECT * FROM datos_uis 
            WHERE latitud = ? AND longitud = ?
        """
        df = pd.read_sql(query, conn, params=(lat_value, lng_value))
        conn.close()
        if df.empty:
            st.warning("⚠️ No se encontraron datos para estas coordenadas.")
            provincia = municipio = poblacion = vial = numero = letra = cp = "No disponible"
        else:
            apartment_id = df.iloc[0]["apartment_id"]
            provincia = df.iloc[0]["provincia"]
            municipio = df.iloc[0]["municipio"]
            poblacion = df.iloc[0]["poblacion"]
            vial = df.iloc[0]["vial"]
            numero = df.iloc[0]["numero"]
            letra = df.iloc[0]["letra"]
            cp = df.iloc[0]["cp"]
    except Exception as e:
        st.error(f"❌ Error al obtener datos de la base de datos: {e}")
        return

    st.text_input("🏢 Apartment ID", value=apartment_id, disabled=True)
    col1, col2, col3 = st.columns(3)
    with col1:
        st.text_input("📍 Provincia", value=provincia, disabled=True)
    with col2:
        st.text_input("🏙️ Municipio", value=municipio, disabled=True)
    with col3:
        st.text_input("👥 Población", value=poblacion, disabled=True)
    col4, col5, col6, col7 = st.columns([2, 1, 1, 1])
    with col4:
        st.text_input("🚦 Vial", value=vial, disabled=True)
    with col5:
        st.text_input("🔢 Número", value=numero, disabled=True)
    with col6:
        st.text_input("🔠 Letra", value=letra, disabled=True)
    with col7:
        st.text_input("📮 Código Postal", value=cp, disabled=True)
    col8, col9 = st.columns(2)
    with col8:
        st.text_input("📌 Latitud", value=lat_value, disabled=True)
    with col9:
        st.text_input("📌 Longitud", value=lng_value, disabled=True)

    es_serviciable = st.radio("🛠️ ¿Es serviciable?", ["Sí", "No"], index=0, horizontal=True)

    if es_serviciable == "No":
        motivo_serviciable = st.text_area("❌ Motivo de No Servicio")
        client_name = ""
        phone = ""
        alt_address = ""
        observations = ""
        contiene_incidencias = ""
        motivo_incidencia = ""
        imagen_incidencia = None
    else:
        client_name = st.text_input("👤 Nombre del Cliente", max_chars=100)
        phone = st.text_input("📞 Teléfono", max_chars=15)
        alt_address = st.text_input("📌 Dirección Alternativa (Rellenar si difiere de la original)")
        observations = st.text_area("📝 Observaciones")
        contiene_incidencias = st.radio("⚠️ ¿Contiene incidencias?", ["Sí", "No"], index=1, horizontal=True)
        if contiene_incidencias == "Sí":
            motivo_incidencia = st.text_area("📄 Motivo de la Incidencia")
            imagen_incidencia = st.file_uploader("📷 Adjuntar Imagen (PNG, JPG, JPEG)", type=["png", "jpg", "jpeg"])
        else:
            motivo_incidencia = ""
            imagen_incidencia = None
        motivo_serviciable = ""

    if st.button("🚀 Enviar Oferta"):
        if phone and not phone.isdigit():
            st.error("❌ El teléfono debe contener solo números.")
            return

        oferta_data = {
            "Apartment ID": apartment_id,
            "Provincia": provincia,
            "Municipio": municipio,
            "Población": poblacion,
            "Vial": vial,
            "Número": numero,
            "Letra": letra,
            "Código Postal": cp,
            "Latitud": lat_value,
            "Longitud": lng_value,
            "Nombre Cliente": client_name,
            "Teléfono": phone,
            "Dirección Alternativa": alt_address,
            "Observaciones": observations,
            "serviciable": es_serviciable,
            "motivo_serviciable": motivo_serviciable,
            "incidencia": contiene_incidencias if es_serviciable == "Sí" else "",
            "motivo_incidencia": motivo_incidencia if es_serviciable == "Sí" else "",
            "fecha": pd.Timestamp.now()
        }

        with st.spinner("⏳ Guardando la oferta en la base de datos..."):
            guardar_en_base_de_datos(oferta_data, imagen_incidencia)

if __name__ == "__main__":
    comercial_dashboard()