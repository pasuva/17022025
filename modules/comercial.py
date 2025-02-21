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
from folium.plugins import Geocoder

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
                            Tipo_Vivienda TEXT,
                            Contrato TEXT
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
                            motivo_serviciable, incidencia, motivo_incidencia, fichero_imagen, fecha, Tipo_Vivienda, Contrato
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
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
                           oferta_data["fecha"].strftime('%Y-%m-%d %H:%M:%S'),
                           oferta_data["Tipo_Vivienda"],
                           oferta_data["Contrato"]
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
    """Muestra el mapa y formulario de Ofertas Comerciales para el comercial logueado."""

    # Mostrar el ícono de usuario y datos en la barra lateral
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

    # Menú lateral para elegir la vista
    menu_opcion = st.sidebar.radio("Selecciona la vista:", ["📊 Ofertas Comerciales", "✔️ Viabilidades"])

    # Registrar trazabilidad de la selección del menú
    detalles = f"El usuario seleccionó la vista '{menu_opcion}'."
    log_trazabilidad(st.session_state["username"], "Selección de vista", detalles)

    # Verificar que el usuario esté logueado
    if "username" not in st.session_state:
        st.warning("⚠️ No has iniciado sesión. Por favor, inicia sesión para continuar.")
        time.sleep(2)
        login.login()
        return

    comercial = st.session_state.get("username")

    # Sección de Ofertas Comerciales
    if menu_opcion == "📊 Ofertas Comerciales":

        st.title("📍 Mapa de Ubicaciones")

        log_trazabilidad(comercial, "Visualización de Dashboard",
                         "El comercial visualizó la sección de Ofertas Comerciales.")

        # Cargar datos del comercial desde la base de datos
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

                # Obtener los apartment_id con ofertas y su estado de contrato
                query_ofertas = "SELECT apartment_id, Contrato FROM ofertas_comercial"
                ofertas_df = pd.read_sql(query_ofertas, conn)

                # Obtener los apartment_id que están en ams con site_operational_state = "serviciable"
                query_ams = "SELECT apartment_id FROM datos_uis WHERE LOWER(site_operational_state) = 'serviciable'"
                ams_df = pd.read_sql(query_ams, conn)

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

        # Verificar que existan las columnas necesarias
        for col in ['latitud', 'longitud', 'address_id', 'apartment_id']:
            if col not in df.columns:
                st.error(f"❌ No se encuentra la columna '{col}'.")
                return

        if "clicks" not in st.session_state:
            st.session_state.clicks = []

        # Obtener la ubicación del usuario
        location = get_user_location()
        if location is None:
            st.warning("❌ No se pudo obtener la ubicación. Cargando el mapa en la ubicación predeterminada.")
            lat, lon = 43.463444, -3.790476  # Ubicación predeterminada
        else:
            lat, lon = location

        # Crear conjuntos para búsqueda rápida
        serviciable_set = set(ams_df["apartment_id"])  # 🟢 Tiene site_operational_state = "serviciable"

        # Crear diccionario de ofertas con su contrato
        contrato_dict = dict(zip(ofertas_df["apartment_id"], ofertas_df["Contrato"]))

        # Crear y mostrar el mapa con folium
        with st.spinner("⏳ Cargando mapa..."):
            m = folium.Map(location=[lat, lon], zoom_start=12,
                           tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
                           attr="Google")
            Geocoder().add_to(m)
            marker_cluster = MarkerCluster().add_to(m)

            for _, row in df.iterrows():
                popup_text = f"🏠 {row['address_id']} - 📍 {row['latitud']}, {row['longitud']}"
                apartment_id = row['apartment_id']

                # Determinar color del marcador
                if apartment_id in serviciable_set:
                    marker_color = 'green'  # 🟢 Tiene site_operational_state = "serviciable"
                elif apartment_id in contrato_dict:
                    if contrato_dict[apartment_id] == "Sí":
                        marker_color = 'orange'  # 🔶 Tiene oferta con Contrato = "Sí"
                    elif contrato_dict[apartment_id] == "No Interesado":
                        marker_color = 'gray'  # ⚪️ Tiene oferta pero "No Interesado"
                    else:
                        marker_color = 'blue'  # 🔵 No cumple ninguna de las condiciones anteriores
                else:
                    marker_color = 'blue'  # 🔵 No tiene oferta ni contrato

                folium.Marker(
                    location=[row['latitud'], row['longitud']],
                    popup=popup_text,
                    icon=folium.Icon(color=marker_color, icon='info-sign')
                ).add_to(marker_cluster)

            map_data = st_folium(m, height=500, width=700)

        # Registrar clics en el mapa
        if map_data and "last_object_clicked" in map_data and map_data["last_object_clicked"]:
            st.session_state.clicks.append(map_data["last_object_clicked"])

        # Mostrar enlace a Google Maps y formulario si hubo clic
        if st.session_state.clicks:
            last_click = st.session_state.clicks[-1]
            lat_click = last_click.get("lat", "")
            lon_click = last_click.get("lng", "")

            if lat_click and lon_click:
                google_maps_link = f"https://www.google.com/maps/search/?api=1&query={lat_click},{lon_click}"
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

    # Sección de Viabilidades (en construcción o con otra funcionalidad)
    elif menu_opcion == "✔️ Viabilidades":
        #st.info("Sección de Viabilidades en construcción.")
        viabilidades_section()

    # Botón de Cerrar Sesión en la barra lateral
    if st.sidebar.button("Cerrar Sesión"):
        cerrar_sesion()


def generar_ticket():
    """Genera un ticket único con formato: añomesdia(numero_consecutivo)"""
    conn = sqlite3.connect("data/usuarios.db")
    cursor = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y%m%d")
    cursor.execute("SELECT COUNT(*) FROM viabilidades WHERE ticket LIKE ?", (f"{fecha_actual}%",))
    count = cursor.fetchone()[0] + 1
    conn.close()
    return f"{fecha_actual}{count:03d}"

def guardar_viabilidad(datos):
    """Inserta los datos en la tabla Viabilidades."""
    conn = sqlite3.connect("data/usuarios.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO viabilidades (latitud, longitud, provincia, municipio, poblacion, vial, numero, letra, cp, comentario, fecha_viabilidad, ticket)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
    """, datos)
    conn.commit()
    conn.close()

# Función para obtener viabilidades guardadas en la base de datos
def obtener_viabilidades():
    conn = sqlite3.connect("data/usuarios.db")  # Asegúrate de que el nombre coincide con tu base de datos
    cursor = conn.cursor()
    cursor.execute("SELECT latitud, longitud, ticket FROM viabilidades")
    viabilidades = cursor.fetchall()
    conn.close()
    return viabilidades

def viabilidades_section():
    st.title("✔️ Viabilidades")
    st.write("Haz click en el mapa para agregar un marcador rojo que represente el punto de viabilidad.")

    # Inicializar estados de sesión si no existen
    if "viabilidad_marker" not in st.session_state:
        st.session_state.viabilidad_marker = None
    if "map_center" not in st.session_state:
        st.session_state.map_center = (43.463444, -3.790476)  # Ubicación inicial predeterminada
    if "map_zoom" not in st.session_state:
        st.session_state.map_zoom = 12  # Zoom inicial

    # Crear el mapa centrado en la última ubicación guardada
    m = folium.Map(
        location=st.session_state.map_center,
        zoom_start=st.session_state.map_zoom,
        tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
        attr="Google"
    )

    # Agregar marcadores de viabilidades guardadas en negro
    viabilidades = obtener_viabilidades()
    for v in viabilidades:
        lat, lon, ticket = v
        folium.Marker(
            [lat, lon],
            icon=folium.Icon(color="black"),
            popup=f"Ticket: {ticket}"
        ).add_to(m)

    # Si hay un marcador, agregarlo al mapa en rojo
    if st.session_state.viabilidad_marker:
        lat = st.session_state.viabilidad_marker["lat"]
        lon = st.session_state.viabilidad_marker["lon"]
        folium.Marker(
            [lat, lon],
            icon=folium.Icon(color="red")
        ).add_to(m)

    # Mostrar el mapa y capturar clics
    map_data = st_folium(m, height=500, width=700)
    Geocoder().add_to(m)

    # Detectar el clic para agregar el marcador
    if map_data and "last_clicked" in map_data and map_data["last_clicked"]:
        click = map_data["last_clicked"]
        st.session_state.viabilidad_marker = {"lat": click["lat"], "lon": click["lng"]}
        st.session_state.map_center = (click["lat"], click["lng"])  # Guardar la nueva vista
        st.session_state.map_zoom = map_data["zoom"]  # Actualizar el zoom también
        st.rerun()  # Usamos rerun para actualizar solo cuando un marcador se haya colocado

    # Botón para eliminar el marcador y crear uno nuevo
    if st.session_state.viabilidad_marker:
        if st.button("Eliminar marcador y crear uno nuevo"):
            st.session_state.viabilidad_marker = None
            st.session_state.map_center = (43.463444, -3.790476)  # Vuelves a la ubicación inicial
            st.rerun()

    # Mostrar el formulario si hay un marcador
    if st.session_state.viabilidad_marker:
        lat = st.session_state.viabilidad_marker["lat"]
        lon = st.session_state.viabilidad_marker["lon"]

        st.subheader("Completa los datos del punto de viabilidad")
        with st.form("viabilidad_form"):
            st.text_input("Latitud", value=str(lat), disabled=True)
            st.text_input("Longitud", value=str(lon), disabled=True)
            provincia = st.text_input("Provincia")
            municipio = st.text_input("Municipio")
            poblacion = st.text_input("Población")
            vial = st.text_input("Vial")
            numero = st.text_input("Número")
            letra = st.text_input("Letra")
            cp = st.text_input("Código Postal")
            comentario = st.text_area("Comentario")
            submit = st.form_submit_button("Enviar Formulario")

            if submit:
                # Generar ticket único
                ticket = generar_ticket()

                # Insertar en la base de datos
                guardar_viabilidad(
                    (lat, lon, provincia, municipio, poblacion, vial, numero, letra, cp, comentario, ticket))

                st.success(f"✅ Viabilidad guardada correctamente.\n\n📌 **Ticket:** `{ticket}`")

                # Resetear marcador para permitir nuevas viabilidades
                st.session_state.viabilidad_marker = None
                st.session_state.map_center = (43.463444, -3.790476)  # Vuelves a la ubicación inicial
                st.rerun()



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

    # Mostrar los nuevos campos solo si es "Sí" en "Es Serviciable"
    if es_serviciable == "Sí":
        tipo_vivienda = st.selectbox("🏠 Tipo de Ui", ["Piso", "Casa", "Dúplex", "Negocio", "Ático", "Otro"], index=0)

        # Si elige "Otro", mostrar campo para que puedan ingresar el tipo de vivienda
        if tipo_vivienda == "Otro":
            tipo_vivienda_otro = st.text_input("📝 Especificar Tipo de Ui")
        else:
            tipo_vivienda_otro = ""  # Si no elige "Otro", el valor es vacío

        contrato = st.radio("📑 Tipo de Contrato", ["Sí", "No Interesado"], index=0, horizontal=True)
    else:
        tipo_vivienda = contrato = tipo_vivienda_otro = None  # Si no es serviciable, los campos no se muestran

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
            "Tipo_Vivienda": tipo_vivienda_otro if tipo_vivienda == "Otro" else tipo_vivienda,
            # Guardar el tipo de vivienda o el valor "Otro"
            "Contrato": contrato,  # Solo se incluye si es "Sí" en serviciable
            "fecha": pd.Timestamp.now()
        }

        with st.spinner("⏳ Guardando la oferta en la base de datos..."):
            guardar_en_base_de_datos(oferta_data, imagen_incidencia)


if __name__ == "__main__":
    comercial_dashboard()