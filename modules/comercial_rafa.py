import streamlit as st
from folium.plugins import MarkerCluster
import pandas as pd
import os, re, time, folium, sqlitecloud
from streamlit_folium import st_folium
from datetime import datetime
from modules import login
from folium.plugins import Geocoder
from modules.cloudinary import upload_image_to_cloudinary
from modules.notificaciones import correo_oferta_comercial, correo_viabilidad_comercial, correo_respuesta_comercial
from streamlit_option_menu import option_menu
from streamlit_cookies_controller import CookieController
from streamlit_javascript import st_javascript

import warnings
warnings.filterwarnings("ignore", category=UserWarning)

cookie_name = "my_app"

# Función para obtener conexión a la base de datos (SQLite Cloud)
def get_db_connection():
    return sqlitecloud.connect(
        "sqlitecloud://ceafu04onz.g6.sqlite.cloud:8860/usuarios.db?apikey=Qo9m18B9ONpfEGYngUKm99QB5bgzUTGtK7iAcThmwvY"
    )

# Añade esto al principio de tu script (si no lo tienes ya)
@st.cache_data(ttl=3600)  # Cache por 1 hora
def load_comercial_data(comercial):
    conn = get_db_connection()

    if comercial in ["nestor", "roberto"]:
        query = """
            SELECT apartment_id, latitud, longitud, comercial, serviciable, municipio, poblacion 
            FROM comercial_rafa 
            WHERE LOWER(comercial) IN ('nestor', 'roberto')
        """
        df = pd.read_sql(query, conn)
    else:
        query = """
            SELECT apartment_id, latitud, longitud, comercial, serviciable, municipio, poblacion 
            FROM comercial_rafa 
            WHERE LOWER(comercial) = LOWER(?)
        """
        df = pd.read_sql(query, conn, params=(comercial,))

        query_ofertas = "SELECT apartment_id, Contrato, municipio, poblacion FROM comercial_rafa"
    ofertas_df = pd.read_sql(query_ofertas, conn)

    query_ams = "SELECT apartment_id FROM datos_uis WHERE LOWER(serviciable) = 'sí'"
    ams_df = pd.read_sql(query_ams, conn)
    conn.close()

    return df, ofertas_df, ams_df

def log_trazabilidad(usuario, accion, detalles):
    conn = get_db_connection()
    cursor = conn.cursor()
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        """
        INSERT INTO trazabilidad (usuario_id, accion, detalles, fecha)
        VALUES (?, ?, ?, ?)
        """,
        (usuario, accion, detalles, fecha)
    )
    conn.commit()
    conn.close()


def guardar_en_base_de_datos(oferta_data, imagen_incidencia, apartment_id):
    """Guarda o actualiza la oferta en SQLite y almacena la imagen en Cloudinary si es necesario."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Verificar si el apartment_id existe
        cursor.execute("SELECT COUNT(*) FROM comercial_rafa WHERE apartment_id = ?", (apartment_id,))
        if cursor.fetchone()[0] == 0:
            st.toast("❌ El Apartment ID no existe en la base de datos. No se puede guardar ni actualizar la oferta.")
            conn.close()
            return

        st.toast(f"⚠️ El Apartment ID {apartment_id} está asignado, se actualizarán los datos.")

        # Subir imagen si hay incidencia
        imagen_url = None
        if oferta_data["incidencia"] == "Sí" and imagen_incidencia:
            extension = os.path.splitext(imagen_incidencia.name)[1]
            filename = f"{apartment_id}{extension}"
            imagen_url = upload_image_to_cloudinary(imagen_incidencia, filename)

        comercial_logueado = st.session_state.get("username", None)

        # ✅ Actualizamos también ocupado_por_tercero
        cursor.execute('''
            UPDATE comercial_rafa SET 
                provincia = ?, municipio = ?, poblacion = ?, vial = ?, numero = ?, letra = ?, 
                cp = ?, latitud = ?, longitud = ?, nombre_cliente = ?, telefono = ?, 
                direccion_alternativa = ?, observaciones = ?, serviciable = ?, motivo_serviciable = ?, 
                incidencia = ?, motivo_incidencia = ?, ocupado_por_tercero = ?, fichero_imagen = ?, 
                fecha = ?, Tipo_Vivienda = ?, Contrato = ?, comercial = ?
            WHERE apartment_id = ?
        ''', (
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
            "Sí" if oferta_data.get("ocupado_por_tercero") else "No",  # 👈 Campo correcto
            imagen_url,
            oferta_data["fecha"].strftime('%Y-%m-%d %H:%M:%S'),
            oferta_data["Tipo_Vivienda"],
            oferta_data["Contrato"],
            comercial_logueado,
            apartment_id
        ))

        conn.commit()
        conn.close()
        st.toast("✅ ¡Oferta actualizada con éxito en la base de datos!")

        # Notificación a administradores
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT email FROM usuarios WHERE role IN ('admin', 'comercial_jefe')")
        destinatario_admin = [fila[0] for fila in cursor.fetchall()]
        conn.close()

        descripcion_oferta = (
            f"Se ha actualizado una oferta para el apartamento con ID {apartment_id}.\n\n"
            f"🏠 Ocupado por un tercero: {'Sí' if oferta_data.get('ocupado_por_tercero') else 'No'}\n\n"
            f"Detalles: {oferta_data}"
        )

        for correo in destinatario_admin:
            correo_oferta_comercial(correo, apartment_id, descripcion_oferta)

        st.toast(f"📧 Se ha notificado a {len(destinatario_admin)} administrador(es).")

        # Registrar trazabilidad
        log_trazabilidad(st.session_state["username"], "Actualizar Oferta",
                         f"Oferta actualizada para Apartment ID: {apartment_id}")

    except Exception as e:
        st.toast(f"❌ Error al guardar o actualizar la oferta en la base de datos: {e}")

def mostrar_ultimo_anuncio():
    """Muestra el anuncio más reciente a los usuarios normales."""
    try:
        conn = get_db_connection()
        query = "SELECT titulo, descripcion, fecha FROM anuncios ORDER BY id DESC LIMIT 1"
        anuncio = pd.read_sql_query(query, conn)
        conn.close()

        # Si hay algún anuncio publicado
        if not anuncio.empty:
            ultimo = anuncio.iloc[0]
            st.info(
                f"📰 **{ultimo['titulo']}**  \n"
                f"{ultimo['descripcion']}  \n"
                f"📅 *Publicado el {ultimo['fecha']}*"
            )
        else:
            # Si aún no hay anuncios, no mostrar nada
            pass

    except Exception as e:
        st.warning(f"⚠️ No se pudo cargar el último anuncio: {e}")



def comercial_dashboard():
    """Muestra el mapa y formulario de Ofertas Comerciales para el comercial logueado."""
    controller = CookieController(key="cookies")
    st.markdown(
        """
        <style>
        .footer {
            position: fixed;
            left: 0;
            bottom: 0;
            width: 100%;
            background-color: #F7FBF9;
            color: black;
            text-align: center;
            padding: 8px 0;
            font-size: 14px;
            font-family: 'Segoe UI', sans-serif;
            z-index: 999;
        }
        </style>
        <div class="footer">
            <p>© 2025 Verde tu operador · Desarrollado para uso interno</p>
        </div>
        """,
        unsafe_allow_html=True
    )

    with st.sidebar:
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
                    margin: 0 auto 10px auto;
                    text-align: center;
                }
                .user-info {
                    text-align: center;
                    font-size: 16px;
                    color: #333;
                    margin-bottom: 10px;
                }
                .welcome-msg {
                    text-align: center;
                    font-weight: bold;
                    font-size: 18px;
                    margin-top: 0;
                }
            </style>

            <div class="user-circle">👤</div>
            <div class="user-info">Rol: Comercial</div>
            <div class="welcome-msg">Bienvenido, <strong>{username}</strong></div>
            <hr>
            """.replace("{username}", st.session_state['username']), unsafe_allow_html=True)

        menu_opcion = option_menu(
            menu_title=None,  # Título oculto
            options=["Ofertas Comerciales", "Viabilidades", "Visualización de Datos"],
            icons=["bar-chart", "check-circle", "graph-up"],
            menu_icon="list",
            default_index=0,
            styles={
                "container": {
                    "padding": "0px",
                    "background-color": "#F0F7F2"  # Fondo claro corporativo
                },
                "icon": {
                    "color": "#2C5A2E",  # Verde oscuro
                    "font-size": "18px"
                },
                "nav-link": {
                    "color": "#2C5A2E",
                    "font-size": "16px",
                    "text-align": "left",
                    "margin": "0px",
                    "--hover-color": "#66B032",
                    "border-radius": "0px",
                },
                "nav-link-selected": {
                    "background-color": "#66B032",  # Verde principal
                    "color": "white",
                    "font-weight": "bold"
                }
            }
        )

    detalles = f"El usuario seleccionó la vista '{menu_opcion}'."
    log_trazabilidad(st.session_state["username"], "Selección de vista", detalles)

    if "username" not in st.session_state:
        st.warning("⚠️ No has iniciado sesión. Por favor, inicia sesión para continuar.")
        time.sleep(2)
        login.login()
        return

    comercial = st.session_state.get("username")

    # Botón de Cerrar Sesión
    with st.sidebar:
        if st.button("Cerrar sesión"):
            detalles = f"El comercial {st.session_state.get('username', 'N/A')} cerró sesión."
            log_trazabilidad(st.session_state.get("username", "N/A"), "Cierre sesión", detalles)

            # Eliminar las cookies del session_id, username y role para esta sesión
            if controller.get(f'{cookie_name}_session_id'):
                controller.set(f'{cookie_name}_session_id', '', max_age=0, path='/')
            if controller.get(f'{cookie_name}_username'):
                controller.set(f'{cookie_name}_username', '', max_age=0, path='/')
            if controller.get(f'{cookie_name}_role'):
                controller.set(f'{cookie_name}_role', '', max_age=0, path='/')

            # Reiniciar el estado de sesión
            # Reiniciar el estado de sesión
            st.session_state["login_ok"] = False
            st.session_state["username"] = ""
            st.session_state["role"] = ""
            st.session_state["session_id"] = ""

            st.toast("✅ Has cerrado sesión correctamente. Redirigiendo al login...")
            st.rerun()

    # Se utiliza un ícono de marcador por defecto (sin comprobación de tipo_olt_rental)
    marker_icon_type = 'info-sign'

    if menu_opcion == "Ofertas Comerciales":

        log_trazabilidad(comercial, "Visualización de Dashboard", "El comercial visualizó la sección de Ofertas Comerciales.")
        mostrar_ultimo_anuncio()

        def create_optimized_map(df, lat, lon, ofertas_df, ams_df):
            """Función optimizada para crear el mapa"""

            # Pre-calcular datos fuera del bucle
            serviciable_set = set(ams_df["apartment_id"])
            contrato_dict = dict(zip(ofertas_df["apartment_id"], ofertas_df["Contrato"]))

            def get_icon_for_olt(tipo_olt):
                if pd.isna(tipo_olt):
                    return "info-sign"  # icono por defecto
                tipo = str(tipo_olt).strip()
                if "CTO VERDE" in tipo:
                    return "cloud"
                else:
                    return "info-sign"

            # Función para determinar color del marcador
            def get_marker_color(row, contrato_dict, serviciable_set):
                apartment_id = row['apartment_id']
                serviciable_val = str(row.get("serviciable", "")).strip().lower()

                if serviciable_val == "no":
                    return 'red'
                elif serviciable_val == "si":
                    return 'green'
                elif apartment_id in contrato_dict:
                    contrato_val = contrato_dict[apartment_id].strip().lower()
                    if contrato_val == "sí":
                        return 'orange'
                    elif contrato_val == "no interesado":
                        return 'black'
                return 'blue'

            # Pre-calcular colores en lote
            df['marker_color'] = df.apply(
                lambda row: get_marker_color(row, contrato_dict, serviciable_set),
                axis=1
            )

            # Agrupar coordenadas duplicadas para desplazamiento
            df['offset_index'] = df.groupby(['latitud', 'longitud']).cumcount()

            # Crear mapa
            m = folium.Map(
                location=[lat, lon],
                zoom_start=12,
                max_zoom=21,
                tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
                attr="Google"
            )

            Geocoder().add_to(m)

            # MarkerCluster optimizado
            cluster_layer = MarkerCluster(
                maxClusterRadius=40,
                disableClusteringAtZoom=17,
                chunkedLoading=True,
                chunkInterval=100
            ).add_to(m)

            # Crear marcadores de forma eficiente
            for _, row in df.iterrows():
                lat_offset = row['offset_index'] * 0.00003
                lon_offset = row['offset_index'] * -0.00003

                icon_type = get_icon_for_olt(row.get("tipo_olt_rental", None))

                folium.Marker(
                    location=[row['latitud'] + lat_offset, row['longitud'] + lon_offset],
                    popup=(
                        f"<b>🏠 {row['apartment_id']}</b><br>"
                        f"📍 {row['latitud']}, {row['longitud']}<br>"
                        f"🛰️ OLT: {row.get('tipo_olt_rental', '—')}"
                    ),
                    icon=folium.Icon(color=row['marker_color'], icon=icon_type)
                ).add_to(cluster_layer)

            # Leyenda optimizada
            legend_html = '''
            <div style="
                position: fixed; 
                bottom: 10px; 
                left: 10px; 
                width: 190px; 
                z-index: 1000; 
                font-size: 14px;
                background-color: white;
                color: black;
                border: 2px solid grey;
                border-radius: 8px;
                padding: 10px;
                box-shadow: 2px 2px 6px rgba(0,0,0,0.3);
            ">
            <b>Leyenda</b><br>
            <i style="color:green;">●</i> Serviciable y Finalizado<br>
            <i style="color:red;">●</i> No serviciable<br>
            <i style="color:orange;">●</i> Contrato Sí<br>
            <i style="color:black;">●</i> No interesado<br>
            <i style="color:purple;">●</i> Incidencia<br>
            <i style="color:blue;">●</i> No Visitado<br>
            <i class="fa fa-cloud"></i> CTO VERDE<br>
            <i class="fa fa-info-circle"></i> CTO COMPARTIDA<br>
            </div>
            '''

            m.get_root().html.add_child(folium.Element(legend_html))

            return m

        # --- CÓDIGO PRINCIPAL OPTIMIZADO ---
        with st.spinner("⏳ Cargando datos optimizados..."):
            try:
                comercial = st.session_state.get("username", "").lower()

                # Verificar si la tabla existe primero
                conn = get_db_connection()
                query_tables = "SELECT name FROM sqlite_master WHERE type='table';"
                tables = pd.read_sql(query_tables, conn)
                conn.close()

                if 'comercial_rafa' not in tables['name'].values:
                    st.toast("❌ La tabla 'comercial_rafa' no se encuentra en la base de datos.")
                    st.stop()

                # Cargar datos con caché
                df, ofertas_df, ams_df = load_comercial_data(comercial)
                # 🔹 Cargar datos de OLT (si existe la tabla datos_uis)
                try:
                    conn = get_db_connection()
                    datos_uis_df = pd.read_sql("SELECT apartment_id, tipo_olt_rental FROM datos_uis", conn)
                    conn.close()

                    # Merge con df principal
                    df = df.merge(datos_uis_df, on="apartment_id", how="left")
                except Exception as e:
                    st.warning(f"⚠️ No se pudo cargar 'datos_uis': {e}")
                    df["tipo_olt_rental"] = None

                if df.empty:
                    st.warning("⚠️ No hay datos asignados a este comercial.")
                    st.stop()

                # Validar columnas esenciales
                essential_cols = ['latitud', 'longitud', 'apartment_id']
                missing_cols = [col for col in essential_cols if col not in df.columns]
                if missing_cols:
                    st.toast(f"❌ Faltan columnas: {missing_cols}")
                    st.stop()

            except Exception as e:
                st.toast(f"❌ Error al cargar los datos: {e}")
                st.stop()

        # Inicializar clicks si no existe
        if "clicks" not in st.session_state:
            st.session_state.clicks = []

        # Obtener ubicación
        with st.spinner("📡 Obteniendo tu ubicación..."):
            location = get_user_location()

        if location:
            lat, lon = location
            st.toast(f"✅ Ubicación obtenida: {lat:.6f}, {lon:.6f}")
        else:
            st.warning("⚠️ No se pudo obtener la ubicación automática.")
            # Usar última ubicación o ubicación por defecto
            if "ultima_lat" in st.session_state and "ultima_lon" in st.session_state:
                lat, lon = st.session_state["ultima_lat"], st.session_state["ultima_lon"]
            else:
                lat, lon = 43.463444, -3.790476

        # Crear y mostrar mapa optimizado
        with st.spinner("🗺️ Generando mapa optimizado..."):
            # Extraer lista de municipios
            municipios = sorted(df["municipio"].dropna().unique().tolist())

            # --- Filtro de municipio ---
            municipio_filtro = st.selectbox(
                "🏙️ Municipio",
                ["Selecciona un municipio"] + municipios,
                key="filtro_municipio"
            )

            # --- Filtro dependiente de población ---
            if municipio_filtro != "Selecciona un municipio":
                poblaciones_filtradas = sorted(
                    df.loc[df["municipio"] == municipio_filtro, "poblacion"].dropna().unique().tolist()
                )
            else:
                poblaciones_filtradas = sorted(df["poblacion"].dropna().unique().tolist())

            poblacion_filtro = st.selectbox(
                "👥 Población",
                ["Selecciona una población"] + poblaciones_filtradas,
                key="filtro_poblacion"
            )

            # --- Comprobar si ambos filtros están seleccionados ---
            if municipio_filtro == "Selecciona un municipio" or poblacion_filtro == "Selecciona una población":
                st.warning("⚠️ Selecciona un municipio y una población para mostrar el mapa. SI NO SE SELECCIONA NINGUN FILTRO, EL MAPA NO SE MOSTRARÁ NUNCA. El marcador rojo es tu ubicación actual.")
                st.stop()

            # --- Aplicar filtros finales ---
            df_filtrado = df.copy()
            df_filtrado = df_filtrado[df_filtrado["municipio"] == municipio_filtro]
            df_filtrado = df_filtrado[df_filtrado["poblacion"] == poblacion_filtro]

            # 🔹 NUEVO FILTRO CTO
            opcion_cto = st.radio(
                "Selecciona el tipo de CTO a mostrar:",
                ["Todas", "CTO VERDE", "CTO COMPARTIDA"],
                horizontal=True,
                key="filtro_cto"
            )

            if opcion_cto == "CTO VERDE":
                df_filtrado = df_filtrado[df_filtrado["tipo_olt_rental"].str.contains("CTO VERDE", case=False, na=False)]
            elif opcion_cto == "CTO COMPARTIDA":
                df_filtrado = df_filtrado[
                    df_filtrado["tipo_olt_rental"].str.contains("CTO COMPARTIDA", case=False, na=False)]

            # 🔹 Fin nuevo filtro CTO

            if df_filtrado.empty:
                st.warning("⚠️ No hay registros para los filtros seleccionados.")
                st.stop()

            # --- Centrar mapa según datos filtrados ---
            lat_centro = df_filtrado["latitud"].mean()
            lon_centro = df_filtrado["longitud"].mean()

            # --- Crear mapa ---
            m = create_optimized_map(df_filtrado, lat_centro, lon_centro, ofertas_df, ams_df)

            # --- Añadir marcador para la ubicación actual ---
            if location is not None and len(location) == 2:
                folium.Marker(
                    location=location,
                    popup="📍 Tu ubicación actual",
                    icon=folium.Icon(color="red", icon="user")
                ).add_to(m)
            else:
                st.warning("⚠️ No se pudo determinar tu ubicación. Mostrando el mapa sin marcador de usuario.")

            st.info(f"📦 Mostrando {len(df_filtrado)} ubicaciones (de {len(df)} puntos que tienes asignados)")
            map_data = st_folium(m, height=680, width="100%", key="optimized_map")

        # Manejar clicks en el mapa
        if map_data and "last_object_clicked" in map_data and map_data["last_object_clicked"]:
            st.session_state.clicks.append(map_data["last_object_clicked"])

        # Mostrar enlace de Google Maps para el último click
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

            # Mostrar formulario
            with st.spinner("⏳ Cargando formulario..."):
                mostrar_formulario(last_click)

        # Limpiar clicks antiguos para evitar acumulación excesiva
        if len(st.session_state.clicks) > 50:
            st.session_state.clicks = st.session_state.clicks[-20:]

    # Sección de Viabilidades
    elif menu_opcion == "Viabilidades":
        viabilidades_section()

    # Y en la función principal, reemplazar la sección con:
    elif menu_opcion == "Visualización de Datos":
        seccion_visualizacion_datos()


def seccion_visualizacion_datos():
    """Sección optimizada de visualización de datos"""
    st.subheader("📊 Visualización de Datos")

    # Verificar autenticación
    if "username" not in st.session_state:
        st.error("❌ No has iniciado sesión")
        st.stop()

    comercial_usuario = st.session_state.get("username")

    try:
        # Cargar datos optimizados
        df_ofertas, df_viabilidades = cargar_datos_visualizacion(comercial_usuario)

        # Mostrar secciones
        mostrar_tabla_ofertas(df_ofertas, comercial_usuario)
        mostrar_tabla_viabilidades(df_viabilidades, comercial_usuario)

    except Exception as e:
        st.error(f"❌ Error al cargar los datos: {e}")


@st.cache_data(ttl=300)  # Cache de 5 minutos
def cargar_datos_visualizacion(comercial_usuario):
    """Carga optimizada de datos para visualización"""
    conn = get_db_connection()
    try:
        # Cargar ofertas del comercial
        query_ofertas = "SELECT * FROM comercial_rafa WHERE LOWER(comercial) = LOWER(?)"
        df_ofertas = pd.read_sql(query_ofertas, conn, params=(comercial_usuario,))

        # Enriquecer con estado de contrato
        if not df_ofertas.empty:
            query_seguimiento = "SELECT apartment_id, estado FROM seguimiento_contratos WHERE LOWER(estado) = 'finalizado'"
            df_seguimiento = pd.read_sql(query_seguimiento, conn)
            df_ofertas['Contrato_Activo'] = df_ofertas['apartment_id'].isin(
                df_seguimiento['apartment_id']
            ).map({True: '✅ Activo', False: '❌ No Activo'})

        # Cargar viabilidades del comercial
        query_viabilidades = """
            SELECT ticket, latitud, longitud, provincia, municipio, poblacion, vial, numero, 
                   letra, cp, serviciable, coste, comentarios_comercial, justificacion, 
                   resultado, respuesta_comercial
            FROM viabilidades 
            WHERE LOWER(usuario) = LOWER(?)
        """
        df_viabilidades = pd.read_sql(query_viabilidades, conn, params=(comercial_usuario,))

        return df_ofertas, df_viabilidades

    finally:
        conn.close()


def mostrar_tabla_ofertas(df_ofertas, comercial_usuario):
    """Muestra tabla de ofertas optimizada"""
    if df_ofertas.empty:
        st.warning(f"⚠️ No hay ofertas para el comercial '{comercial_usuario}'")
        return

    st.subheader("📋 Tabla de Visitas/Ofertas")

    # Filtros rápidos para la tabla
    col1, col2 = st.columns(2)
    with col1:
        filtro_contrato = st.selectbox(
            "Filtrar por estado de contrato:",
            ["Todos", "✅ Activo", "❌ No Activo"]
        )

    with col2:
        filtro_serviciable = st.selectbox(
            "Filtrar por serviciable:",
            ["Todos", "Sí", "No"]
        )

    # Aplicar filtros
    df_filtrado = df_ofertas.copy()
    if filtro_contrato != "Todos":
        df_filtrado = df_filtrado[df_filtrado['Contrato_Activo'] == filtro_contrato]
    if filtro_serviciable != "Todos":
        df_filtrado = df_filtrado[df_filtrado['serviciable'] == filtro_serviciable]

    # Mostrar métricas rápidas
    mostrar_metricas_ofertas(df_filtrado)

    # Mostrar tabla
    st.dataframe(df_filtrado, width='stretch')

    # Botón de exportación
    if st.button("📤 Exportar a CSV", key="export_ofertas"):
        csv = df_filtrado.to_csv(index=False)
        st.download_button(
            label="⬇️ Descargar CSV",
            data=csv,
            file_name=f"ofertas_{comercial_usuario}_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )


def mostrar_metricas_ofertas(df):
    """Muestra métricas rápidas de ofertas"""
    if df.empty:
        return

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Ofertas", len(df))

    with col2:
        activas = len(df[df['Contrato_Activo'] == '✅ Activo'])
        st.metric("Contratos Activos", activas)

    with col3:
        serviciables = len(df[df['serviciable'] == 'Sí'])
        st.metric("Serviciables", serviciables)

    with col4:
        no_serviciables = len(df[df['serviciable'] == 'No'])
        st.metric("No Serviciables", no_serviciables)


def mostrar_tabla_viabilidades(df_viabilidades, comercial_usuario):
    """Muestra tabla de viabilidades optimizada"""
    if df_viabilidades.empty:
        st.warning(f"⚠️ No hay viabilidades para el comercial '{comercial_usuario}'")
        return

    st.subheader("📋 Tabla de Viabilidades")
    st.dataframe(df_viabilidades, width='stretch')

    # Procesar viabilidades pendientes
    procesar_viabilidades_pendientes(df_viabilidades, comercial_usuario)


def procesar_viabilidades_pendientes(df_viabilidades, comercial_usuario):
    """Procesa y muestra viabilidades pendientes de respuesta"""
    # Definir criterios para viabilidades críticas
    JUSTIFICACIONES_CRITICAS = ["MAS PREVENTA", "PDTE. RAFA FIN DE OBRA"]
    RESULTADOS_CRITICOS = ["PDTE INFORMACION RAFA", "OK", "SOBRECOSTE"]

    # Filtrar viabilidades que requieren atención
    df_condiciones = df_viabilidades[
        (df_viabilidades['justificacion'].isin(JUSTIFICACIONES_CRITICAS)) |
        (df_viabilidades['resultado'].isin(RESULTADOS_CRITICOS))
        ]

    # Filtrar las pendientes de respuesta
    df_pendientes = df_condiciones[
        df_condiciones['respuesta_comercial'].isna() |
        (df_condiciones['respuesta_comercial'] == "")
        ]

    if df_pendientes.empty:
        st.success("🎉 No tienes viabilidades pendientes de contestar")
        return

    st.warning(f"🔔 Tienes {len(df_pendientes)} viabilidades pendientes de contestar")
    st.subheader("📝 Gestión de Viabilidades Pendientes")

    # Mostrar formularios para cada viabilidad pendiente
    for _, row in df_pendientes.iterrows():
        mostrar_formulario_viabilidad(row, comercial_usuario)


def mostrar_formulario_viabilidad(viabilidad, comercial_usuario):
    """Muestra formulario individual para viabilidad pendiente"""
    ticket = viabilidad['ticket']

    with st.expander(f"🎫 Ticket {ticket} - {viabilidad['municipio']} {viabilidad['vial']} {viabilidad['numero']}"):
        # Información contextual
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**📌 Justificación:**  \n{viabilidad.get('justificacion', '—')}")
        with col2:
            st.markdown(f"**📊 Resultado:**  \n{viabilidad.get('resultado', '—')}")

        # Instrucciones colapsables
        with st.expander("ℹ️ Instrucciones para completar", expanded=False):
            st.markdown("""
            **Por favor, indica:**
            - ✅ Si estás de acuerdo o no con la resolución
            - 🏠 Información adicional de tu visita (cliente, obra, accesos, etc.)
            - 💰 Si el cliente acepta o no el presupuesto
            - 📝 Cualquier detalle que ayude a la oficina a cerrar la viabilidad
            """)

        # Formulario de comentario
        with st.form(key=f"form_viabilidad_{ticket}"):
            nuevo_comentario = st.text_area(
                "✏️ Tu respuesta:",
                value="",
                placeholder="Ejemplo: El cliente confirma que esperará a fin de obra para contratar...",
                help="Este comentario se enviará a la oficina técnica"
            )

            if st.form_submit_button("💾 Guardar Respuesta", width='stretch'):
                guardar_respuesta_viabilidad(ticket, nuevo_comentario, comercial_usuario)


def guardar_respuesta_viabilidad(ticket, comentario, comercial_usuario):
    """Guarda la respuesta de viabilidad y envía notificaciones"""
    if not comentario.strip():
        st.error("❌ El comentario no puede estar vacío")
        return

    try:
        # Actualizar en base de datos
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE viabilidades SET respuesta_comercial = ? WHERE ticket = ?",
                (comentario, ticket)
            )
            conn.commit()
        finally:
            conn.close()

        # Enviar notificaciones
        enviar_notificaciones_viabilidad(ticket, comercial_usuario, comentario)

        st.success(f"✅ Respuesta guardada para el ticket {ticket}")
        st.rerun()

    except Exception as e:
        st.error(f"❌ Error al guardar la respuesta: {e}")


def enviar_notificaciones_viabilidad(ticket, comercial_usuario, comentario):
    """Envía notificaciones por correo electrónico"""
    try:
        # Obtener destinatarios
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT email FROM usuarios WHERE role IN ('admin','comercial_jefe')")
            destinatarios = [fila[0] for fila in cursor.fetchall()]
        finally:
            conn.close()

        # Enviar notificaciones
        for email in destinatarios:
            try:
                correo_respuesta_comercial(email, ticket, comercial_usuario, comentario)
            except Exception as e:
                st.warning(f"⚠️ No se pudo enviar notificación a {email}: {e}")

        st.toast(f"📧 Notificaciones enviadas a {len(destinatarios)} destinatarios")

    except Exception as e:
        st.warning(f"⚠️ Error al enviar notificaciones: {e}")

def generar_ticket():
    """Genera un ticket único con formato: añomesdia(numero_consecutivo)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y%m%d")

    # Buscar el mayor número consecutivo para la fecha actual
    cursor.execute("SELECT MAX(CAST(SUBSTR(ticket, 9, 3) AS INTEGER)) FROM viabilidades WHERE ticket LIKE ?",
                   (f"{fecha_actual}%",))
    max_consecutivo = cursor.fetchone()[0]

    # Si no hay tickets previos, empezar desde 1
    if max_consecutivo is None:
        max_consecutivo = 0

    # Generar el nuevo ticket con el siguiente consecutivo
    ticket = f"{fecha_actual}{max_consecutivo + 1:03d}"
    conn.close()
    return ticket

def guardar_viabilidad(datos):
    """
    Inserta los datos en la tabla Viabilidades.
    Se espera que 'datos' sea una tupla con el siguiente orden:
    (latitud, longitud, provincia, municipio, poblacion, vial, numero, letra, cp, comentario, ticket, nombre_cliente, telefono, usuario)
    """
    # Guardar los datos en la base de datos
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO viabilidades (
            latitud, 
            longitud, 
            provincia, 
            municipio, 
            poblacion, 
            vial, 
            numero, 
            letra, 
            cp, 
            comentario, 
            fecha_viabilidad, 
            ticket, 
            nombre_cliente, 
            telefono, 
            usuario,
            olt,
            apartment_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?)
    """, datos)
    conn.commit()

    # Obtener los emails de todos los administradores
    cursor.execute("SELECT email FROM usuarios WHERE role = 'admin'")
    resultados = cursor.fetchall()
    emails_admin = [fila[0] for fila in resultados]

    # Determinar el comercial_jefe según la provincia
    provincia_viabilidad = datos[2].upper().strip()
    if provincia_viabilidad == "CANTABRIA":
        cursor.execute("SELECT email FROM usuarios WHERE username = 'rafa sanz'")
    else:
        cursor.execute("SELECT email FROM usuarios WHERE username = 'juan'")
    resultado_jefe = cursor.fetchone()
    email_comercial_jefe = resultado_jefe[0] if resultado_jefe else None

    conn.close()

    # Información de la viabilidad
    ticket_id = datos[10]  # 'ticket'
    nombre_comercial = st.session_state.get("username")
    descripcion_viabilidad = (
        f"📝 Viabilidad para el ticket {ticket_id}:<br><br>"
        f"🧑‍💼 Comercial: {nombre_comercial}<br><br>"
        f"📍 Latitud: {datos[0]}<br>"
        f"📍 Longitud: {datos[1]}<br>"
        f"🏞️ Provincia: {datos[2]}<br>"
        f"🏙️ Municipio: {datos[3]}<br>"
        f"🏘️ Población: {datos[4]}<br>"
        f"🛣️ Vial: {datos[5]}<br>"
        f"🔢 Número: {datos[6]}<br>"
        f"🔤 Letra: {datos[7]}<br>"
        f"🏷️ Código Postal (CP): {datos[8]}<br>"
        f"💬 Comentario: {datos[9]}<br>"
        f"👥 Nombre Cliente: {datos[11]}<br>"
        f"📞 Teléfono: {datos[12]}<br><br>"
        f"🏢 OLT: {datos[14]}<br>"
        f"🏘️ Apartment ID: {datos[15]}<br><br>"
        f"ℹ️ Por favor, revise todos los detalles de la viabilidad para asegurar que toda la información esté correcta. "
        f"Si tiene alguna pregunta o necesita más detalles, no dude en ponerse en contacto con el comercial {nombre_comercial} o con el equipo responsable."
    )

    # Enviar la notificación por correo a cada administrador
    if emails_admin:
        for email in emails_admin:
            correo_viabilidad_comercial(email, ticket_id, descripcion_viabilidad)
        st.toast(
            f"📧 Se ha enviado una notificación a los administradores: {', '.join(emails_admin)} sobre la viabilidad completada."
        )
    else:
        st.warning("⚠️ No se encontró ningún email de administrador, no se pudo enviar la notificación.")

    # Notificar al comercial jefe específico
    if email_comercial_jefe:
        correo_viabilidad_comercial(email_comercial_jefe, ticket_id, descripcion_viabilidad)
        st.toast(f"📧 Notificación enviada al comercial jefe: {email_comercial_jefe}")
    else:
        st.warning("⚠️ No se encontró email del comercial jefe, no se pudo enviar la notificación.")

    # Mostrar mensaje de éxito en Streamlit
    st.toast("✅ Los cambios para la viabilidad han sido guardados correctamente")



# Función para obtener viabilidades guardadas en la base de datos
def obtener_viabilidades():
    """Recupera las viabilidades asociadas al usuario logueado."""
    conn = get_db_connection()
    cursor = conn.cursor()
    # Se asume que el usuario logueado está guardado en st.session_state["username"]
    cursor.execute("SELECT latitud, longitud, ticket, serviciable, apartment_id FROM viabilidades WHERE usuario = ?", (st.session_state["username"],))
    viabilidades = cursor.fetchall()
    conn.close()
    return viabilidades


def viabilidades_section():
    st.title("Viabilidades")
    mostrar_leyenda()
    mostrar_instrucciones()

    inicializar_estado_sesion()

    # Obtener viabilidades con caché
    viabilidades = obtener_viabilidades_cache()

    # Crear y mostrar mapa
    map_data = crear_y_mostrar_mapa(viabilidades)

    # Manejar interacción con el mapa
    manejar_interaccion_mapa(map_data)

    # Mostrar formulario si hay marcador nuevo
    mostrar_formulario_si_aplica()


def mostrar_leyenda():
    """Muestra la leyenda de colores de los marcadores"""
    st.markdown("""**Leyenda:**
                 ⚫ Viabilidad ya existente
                 🔵 Viabilidad nueva aún sin estudio
                 🟢 Viabilidad serviciable y con Apartment ID ya asociado
                 🔴 Viabilidad no serviciable
                """)


def mostrar_instrucciones():
    """Muestra instrucciones para el usuario"""
    st.info("ℹ️ Haz click en el mapa para agregar un marcador que represente el punto de viabilidad.")


def inicializar_estado_sesion():
    """Inicializa las variables de estado en session_state si no existen"""
    defaults = {
        "viabilidad_marker": None,
        "map_center": (43.463444, -3.790476),
        "map_zoom": 12
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


@st.cache_data(ttl=300)  # Cache por 5 minutos
def obtener_viabilidades_cache():
    """Obtiene viabilidades con caché para mejorar rendimiento"""
    return obtener_viabilidades()


def determinar_color_marcador(serviciable, apartment_id):
    """Determina el color del marcador basado en los datos"""
    if serviciable is None or str(serviciable).strip() == "":
        return "black"

    serv = str(serviciable).strip()
    apt = str(apartment_id).strip() if apartment_id is not None else ""

    if serv == "No":
        return "red"
    elif serv == "Sí" and apt not in ["", "N/D"]:
        return "green"
    else:
        return "black"


def agregar_marcadores_existentes(mapa, viabilidades):
    """Agrega los marcadores de viabilidades existentes al mapa"""
    for v in viabilidades:
        lat, lon, ticket, serviciable, apartment_id = v
        marker_color = determinar_color_marcador(serviciable, apartment_id)

        folium.Marker(
            [lat, lon],
            icon=folium.Icon(color=marker_color),
            popup=f"Ticket: {ticket}"
        ).add_to(mapa)


def crear_y_mostrar_mapa(viabilidades):
    """Crea y muestra el mapa con todos los marcadores"""
    # Crear mapa
    m = folium.Map(
        location=st.session_state.map_center,
        zoom_start=st.session_state.map_zoom,
        tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
        attr="Google"
    )

    # Agregar marcadores existentes
    agregar_marcadores_existentes(m, viabilidades)

    # Agregar marcador nuevo si existe
    if st.session_state.viabilidad_marker:
        lat = st.session_state.viabilidad_marker["lat"]
        lon = st.session_state.viabilidad_marker["lon"]
        folium.Marker(
            [lat, lon],
            icon=folium.Icon(color="blue")
        ).add_to(m)

    # Agregar geocoder y mostrar mapa
    Geocoder().add_to(m)
    return st_folium(m, height=680, width="100%")


def manejar_interaccion_mapa(map_data):
    """Maneja la interacción con el mapa (clics, etc.)"""
    # Detectar clic para agregar nuevo marcador
    if map_data and "last_clicked" in map_data and map_data["last_clicked"]:
        click = map_data["last_clicked"]
        st.session_state.viabilidad_marker = {"lat": click["lat"], "lon": click["lng"]}
        st.session_state.map_center = (click["lat"], click["lng"])
        st.session_state.map_zoom = map_data["zoom"]
        st.rerun()

    # Botón para eliminar marcador
    if st.session_state.viabilidad_marker:
        if st.button("Eliminar marcador y crear uno nuevo"):
            resetear_marcador()
            st.rerun()


def resetear_marcador():
    """Resetea el marcador y centra el mapa en la ubicación inicial"""
    st.session_state.viabilidad_marker = None
    st.session_state.map_center = (43.463444, -3.790476)


def mostrar_formulario_si_aplica():
    """Muestra el formulario si hay un marcador nuevo"""
    if not st.session_state.viabilidad_marker:
        return

    lat = st.session_state.viabilidad_marker["lat"]
    lon = st.session_state.viabilidad_marker["lon"]

    st.subheader("Completa los datos del punto de viabilidad")
    procesar_formulario(lat, lon)


def procesar_formulario(lat, lon):
    """Procesa el formulario de viabilidad"""
    with st.form("viabilidad_form"):
        # Campos del formulario
        datos = mostrar_campos_formulario(lat, lon)

        if st.form_submit_button("Enviar Formulario"):
            guardar_viabilidad_completa(datos, lat, lon)


def mostrar_campos_formulario(lat, lon):
    """Muestra todos los campos del formulario y retorna los datos"""
    col1, col2 = st.columns(2)
    with col1:
        st.text_input("📍 Latitud", value=str(lat), disabled=True)
    with col2:
        st.text_input("📍 Longitud", value=str(lon), disabled=True)

    col3, col4, col5 = st.columns(3)
    with col3:
        provincia = st.text_input("🏞️ Provincia")
    with col4:
        municipio = st.text_input("🏘️ Municipio")
    with col5:
        poblacion = st.text_input("👥 Población")

    col6, col7, col8, col9 = st.columns([3, 1, 1, 2])
    with col6:
        vial = st.text_input("🛣️ Vial")
    with col7:
        numero = st.text_input("🔢 Número")
    with col8:
        letra = st.text_input("🔤 Letra")
    with col9:
        cp = st.text_input("📮 Código Postal")

    col10, col11 = st.columns(2)
    with col10:
        nombre_cliente = st.text_input("👤 Nombre Cliente")
    with col11:
        telefono = st.text_input("📞 Teléfono")

    # OLT con caché
    col12, col13 = st.columns(2)
    with col12:
        olt = st.selectbox("🏢 OLT", options=obtener_lista_olt_cache())
    with col13:
        apartment_id = st.text_input("🏘️ Apartment ID")

    comentario = st.text_area("📝 Comentario")

    # Subida de imágenes
    imagenes_viabilidad = st.file_uploader(
        "Adjunta fotos (PNG, JPG, JPEG). Puedes seleccionar varias.",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True,
        key=f"imagenes_viabilidad_{lat}_{lon}"
    )

    return {
        "lat": lat,
        "lon": lon,
        "provincia": provincia,
        "municipio": municipio,
        "poblacion": poblacion,
        "vial": vial,
        "numero": numero,
        "letra": letra,
        "cp": cp,
        "nombre_cliente": nombre_cliente,
        "telefono": telefono,
        "olt": olt,
        "apartment_id": apartment_id,
        "comentario": comentario,
        "imagenes": imagenes_viabilidad
    }


@st.cache_data(ttl=3600)  # Cache por 1 hora
def obtener_lista_olt_cache():
    """Obtiene lista de OLTs con caché"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id_olt, nombre_olt FROM olt ORDER BY nombre_olt")
    lista_olt = [f"{fila[0]}. {fila[1]}" for fila in cursor.fetchall()]
    conn.close()
    return lista_olt


def guardar_viabilidad_completa(datos, lat, lon):
    """Guarda la viabilidad completa con imágenes"""
    # Generar ticket
    ticket = generar_ticket()

    # Guardar datos principales
    guardar_viabilidad((
        datos["lat"],
        datos["lon"],
        datos["provincia"],
        datos["municipio"],
        datos["poblacion"],
        datos["vial"],
        datos["numero"],
        datos["letra"],
        datos["cp"],
        datos["comentario"],
        ticket,
        datos["nombre_cliente"],
        datos["telefono"],
        st.session_state["username"],
        datos["olt"],
        datos["apartment_id"]
    ))

    # Guardar imágenes si existen
    if datos["imagenes"]:
        guardar_imagenes_viabilidad(datos["imagenes"], ticket)

    # Mostrar mensaje de éxito
    st.toast(f"✅ Viabilidad guardada correctamente.\n\n📌 **Ticket:** `{ticket}`")

    # Resetear estado
    resetear_marcador()
    st.rerun()


def guardar_imagenes_viabilidad(imagenes, ticket):
    """Guarda las imágenes asociadas a una viabilidad"""
    st.toast("📤 Subiendo imágenes...")

    for imagen in imagenes:
        try:
            archivo_bytes = imagen.getvalue()
            nombre_archivo = imagen.name

            # Subir a Cloudinary
            url = upload_image_to_cloudinary(
                archivo_bytes,
                nombre_archivo,
                folder="viabilidades"
            )

            # Guardar en base de datos
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO imagenes_viabilidad (ticket, archivo_nombre, archivo_url)
                VALUES (?, ?, ?)
            """, (ticket, nombre_archivo, url))
            conn.commit()
            conn.close()

        except Exception as e:
            st.warning(f"⚠️ No se pudo subir la imagen {nombre_archivo}: {e}")

    st.toast("✅ Imágenes guardadas correctamente.")

def get_user_location():
    result = st_javascript(
        "await new Promise((resolve, reject) => "
        "navigator.geolocation.getCurrentPosition(p => resolve({lat: p.coords.latitude, lon: p.coords.longitude}), "
        "err => resolve(null)));"
    )
    if result and "lat" in result and "lon" in result:
        return result["lat"], result["lon"]
    return None

def validar_email(email):
    return re.match(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)


def mostrar_formulario(click_data):
    """Muestra un formulario con los datos correspondientes a las coordenadas seleccionadas."""
    st.subheader("📄 Enviar Oferta")

    # Extraer datos del click
    popup_text = click_data.get("popup", "")
    apartment_id_from_popup = popup_text.split(" - ")[0] if " - " in popup_text else "N/D"

    # Extraer coordenadas y convertir a float
    try:
        lat_value = float(click_data.get("lat"))
        lng_value = float(click_data.get("lng"))
    except (TypeError, ValueError):
        st.toast("❌ Coordenadas inválidas.")
        return

    form_key = f"{lat_value}_{lng_value}"

    # Consultar la base de datos para las coordenadas seleccionadas
    try:
        conn = get_db_connection()
        delta = 0.00001  # tolerancia para floats
        query = """
            SELECT * FROM datos_uis 
            WHERE latitud BETWEEN ? AND ? AND longitud BETWEEN ? AND ?
        """
        params = (lat_value - delta, lat_value + delta, lng_value - delta, lng_value + delta)
        df = pd.read_sql(query, conn, params=params)
        conn.close()
    except Exception as e:
        st.toast(f"❌ Error al obtener datos de la base de datos: {e}")
        return

    # Si no se encontraron registros, avisar y salir
    if df.empty:
        st.warning("⚠️ No se encontraron datos para estas coordenadas.")
        return

    # Si hay más de un registro, pedir al usuario que seleccione uno
    if len(df) > 1:
        opciones = [
            f"{row['apartment_id']}  –  Vial: {row['vial']}  –  Nº: {row['numero']}  –  Letra: {row['letra']}"
            for _, row in df.iterrows()
        ]
        st.warning(
            "⚠️ Hay varias ofertas en estas coordenadas. Elige un Apartment ID de la lista del desplegable. "
            "¡NO TE OLVIDES DE GUARDAR CADA OFERTA POR SEPARADO!"
        )
        seleccion = st.selectbox(
            "Elige un Apartment ID:",
            options=opciones,
            key=f"select_apartment_{form_key}"
        )
        apartment_id = seleccion.split()[0]
        df = df[df["apartment_id"] == apartment_id]
    else:
        apartment_id = df.iloc[0]["apartment_id"]

    # Cargar los datos de la fila elegida
    row = df.iloc[0]
    provincia = row["provincia"]
    municipio = row["municipio"]
    poblacion = row["poblacion"]
    vial = row["vial"]
    numero = row["numero"]
    letra = row["letra"]
    cp = row["cp"]
    cto = row["cto"]
    tipo_olt_rental = row.get("tipo_olt_rental", "")

    # Crear formulario para agrupar todos los campos
    with st.form(key=f"oferta_form_{form_key}"):
        # Mostrar datos no editables
        if str(tipo_olt_rental).strip().upper() == "CTO VERDE":
            st.badge("CTO VERDE", color="green")
        else:
            st.badge("CTO COMPARTIDA")

        st.text_input("🏢 Apartment ID", value=apartment_id, disabled=True)
        col1, col2, col3 = st.columns(3)
        with col1:
            st.text_input("📍 Provincia", value=provincia, disabled=True)
        with col2:
            st.text_input("🏙️ Municipio", value=municipio, disabled=True)
        with col3:
            st.text_input("👥 Población", value=poblacion, disabled=True)

        col4, col5, col6, col7 = st.columns([2, 1, 2, 1])
        with col4:
            st.text_input("🚦 Vial", value=vial, disabled=True)
        with col5:
            st.text_input("🔢 Número", value=numero, disabled=True)
        with col6:
            st.text_input("🔠 Letra", value=letra, disabled=True)
        with col7:
            st.text_input("📮 Código Postal", value=cp, disabled=True)

        col8, col9, col10 = st.columns(3)
        with col8:
            st.text_input("📌 Latitud", value=lat_value, disabled=True)
        with col9:
            st.text_input("📌 Longitud", value=lng_value, disabled=True)
        with col10:
            st.text_input("📌 CTO", value=cto, disabled=True)

        # Selección de tipo de oferta
        es_serviciable = st.radio(
            "🛠️ ¿Es serviciable?",
            ["Sí", "No"],
            index=0,
            horizontal=True,
            key=f"es_serviciable_{form_key}"
        )

        # Campo de motivo de no servicio justo después del radio
        if es_serviciable == "No":
            motivo_serviciable = st.text_area(
                "❌ Motivo de No Servicio",
                key=f"motivo_serviciable_{form_key}",
                placeholder="Explicar por qué no es serviciable...",
                help="Este campo es obligatorio cuando la oferta no es serviciable"
            )
        else:
            motivo_serviciable = ""

        # ACORDEÓN para Datos de la Vivienda y Cliente (solo relevante si es serviciable)
        with st.expander("🏠 Datos de la Vivienda y Cliente", expanded=es_serviciable == "Sí"):
            if es_serviciable == "Sí":
                col1, col2 = st.columns(2)
                with col1:
                    tipo_vivienda = st.selectbox(
                        "🏠 Tipo de Ui",
                        ["Piso", "Casa", "Dúplex", "Negocio", "Ático", "Otro"],
                        index=0,
                        key=f"tipo_vivienda_{form_key}"
                    )

                    # Campo para especificar si se selecciona "Otro"
                    if tipo_vivienda == "Otro":
                        tipo_vivienda_otro = st.text_input(
                            "📝 Especificar Tipo de Ui",
                            key=f"tipo_vivienda_otro_{form_key}",
                            placeholder="Describe el tipo de vivienda"
                        )
                    else:
                        tipo_vivienda_otro = ""

                    contrato = st.radio(
                        "📑 ¿Cliente interesado en contrato?",
                        ["Sí", "No Interesado"],
                        index=0,
                        horizontal=True,
                        key=f"contrato_{form_key}"
                    )

                with col2:
                    client_name = st.text_input(
                        "👤 Nombre del Cliente",
                        max_chars=100,
                        key=f"client_name_{form_key}",
                        placeholder="Nombre completo del cliente"
                    )
                    phone = st.text_input(
                        "📞 Teléfono",
                        max_chars=15,
                        key=f"phone_{form_key}",
                        placeholder="Número de teléfono"
                    )
            else:
                st.info("ℹ️ Esta sección solo es relevante para ofertas serviciables")
                tipo_vivienda = ""
                tipo_vivienda_otro = ""
                contrato = ""
                client_name = ""
                phone = ""

        # ACORDEÓN para Información Adicional
        with st.expander("📍 Información Adicional", expanded=False):
            alt_address = st.text_input(
                "📌 Dirección Alternativa (Rellenar solo si difiere de la original)",
                key=f"alt_address_{form_key}",
                placeholder="Dejar vacío si coincide con la dirección principal"
            )

            observations = st.text_area(
                "📝 Observaciones Generales",
                key=f"observations_{form_key}",
                placeholder="Cualquier observación adicional relevante..."
            )

        # ACORDEÓN para Gestión de Incidencias (solo relevante si es serviciable)
        with st.expander("⚠️ Gestión de Incidencias", expanded=False):
            if es_serviciable == "Sí":
                contiene_incidencias = st.radio(
                    "¿Contiene incidencias?",
                    ["Sí", "No"],
                    index=1,
                    horizontal=True,
                    key=f"contiene_incidencias_{form_key}"
                )

                # Estos campos ahora están siempre habilitados, no dependen del estado del radio button
                motivo_incidencia = st.text_area(
                    "📄 Motivo de la Incidencia",
                    key=f"motivo_incidencia_{form_key}",
                    placeholder="Describir la incidencia encontrada..."
                )

                col_inc1, col_inc2 = st.columns(2)
                with col_inc1:
                    ocupado_tercero = st.checkbox(
                        "🏠 Ocupado por un tercero",
                        key=f"ocupado_tercero_{form_key}"
                    )

                with col_inc2:
                    imagen_incidencia = st.file_uploader(
                        "📷 Adjuntar Imagen de Incidencia (PNG, JPG, JPEG)",
                        type=["png", "jpg", "jpeg"],
                        key=f"imagen_incidencia_{form_key}",
                        help="Opcional: adjuntar imagen relacionada con la incidencia"
                    )
            else:
                st.info("ℹ️ Esta sección solo es relevante para ofertas serviciables")
                contiene_incidencias = ""
                motivo_incidencia = ""
                ocupado_tercero = False
                imagen_incidencia = None

        # Información para el usuario
        st.info(
            "💡 **Nota:** Complete todos los campos relevantes según el tipo de oferta. Los campos se procesarán según su selección en '¿Es serviciable?'")

        # Botón de envío dentro del formulario
        submit = st.form_submit_button("🚀 Enviar Oferta")

    # Procesar envío (fuera del formulario)
    if submit:
        # Validaciones
        if es_serviciable == "No" and not motivo_serviciable:
            st.toast("❌ Debe proporcionar el motivo de no servicio cuando la oferta no es serviciable.")
            return

        if es_serviciable == "Sí" and phone and not phone.isdigit():
            st.toast("❌ El teléfono debe contener solo números.")
            return

        if es_serviciable == "Sí" and (not client_name or not phone):
            st.toast("❌ El nombre y teléfono del cliente son obligatorios para ofertas serviciables.")
            return

        # Determinar el tipo de vivienda final
        tipo_vivienda_final = ""
        if es_serviciable == "Sí":
            tipo_vivienda_final = tipo_vivienda_otro if tipo_vivienda == "Otro" else tipo_vivienda

        # Construir el diccionario de datos de la oferta
        oferta_data = {
            "Provincia": provincia,
            "Municipio": municipio,
            "Población": poblacion,
            "Vial": vial,
            "Número": numero,
            "Letra": letra,
            "Código Postal": cp,
            "Latitud": lat_value,
            "Longitud": lng_value,
            "cto": cto,
            "Nombre Cliente": client_name if es_serviciable == "Sí" else "",
            "Teléfono": phone if es_serviciable == "Sí" else "",
            "Dirección Alternativa": alt_address,
            "Observaciones": observations,
            "serviciable": es_serviciable,
            "motivo_serviciable": motivo_serviciable if es_serviciable == "No" else "",
            "incidencia": contiene_incidencias if es_serviciable == "Sí" else "",
            "motivo_incidencia": motivo_incidencia if (es_serviciable == "Sí" and contiene_incidencias == "Sí") else "",
            "ocupado_tercero": ocupado_tercero if (es_serviciable == "Sí" and contiene_incidencias == "Sí") else False,
            "Tipo_Vivienda": tipo_vivienda_final if es_serviciable == "Sí" else "",
            "Contrato": contrato if es_serviciable == "Sí" else "",
            "fecha": pd.Timestamp.now(tz="Europe/Madrid")
        }

        # Guardar en base de datos y enviar notificaciones
        with st.spinner("⏳ Guardando la oferta en la base de datos..."):
            guardar_en_base_de_datos(oferta_data, imagen_incidencia, apartment_id)

            # Obtener emails de administradores
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT email FROM usuarios WHERE role IN ('admin', 'comercial_jefe')")
            emails_admin = [fila[0] for fila in cursor.fetchall()]

            nombre_comercial = st.session_state.get("username", "N/D")
            email_comercial = st.session_state.get("email", None)

            conn.close()

            # Construir descripción para el email
            descripcion_oferta = (
                f"🆕 Se ha añadido una nueva oferta para el apartamento con ID {apartment_id}.<br><br>"
                f"📑 <strong>Detalles de la oferta realizada por el comercial {nombre_comercial}:</strong><br>"
                f"🌍 <strong>Provincia:</strong> {provincia}<br>"
                f"📌 <strong>Municipio:</strong> {municipio}<br>"
                f"🏡 <strong>Población:</strong> {poblacion}<br>"
                f"🛣️ <strong>Vial:</strong> {vial}<br>"
                f"🔢 <strong>Número:</strong> {numero}<br>"
                f"🔠 <strong>Letra:</strong> {letra}<br>"
                f"📮 <strong>Código Postal:</strong> {cp}<br>"
                f"📅 <strong>Fecha:</strong> {oferta_data['fecha']}<br>"
                f"🔧 <strong>Serviciable:</strong> {es_serviciable}<br>"
            )

            # Agregar campos condicionales al email
            if es_serviciable == "Sí":
                descripcion_oferta += (
                    f"📱 <strong>Teléfono:</strong> {phone}<br>"
                    f"👤 <strong>Nombre Cliente:</strong> {client_name}<br>"
                    f"🏘️ <strong>Tipo Vivienda:</strong> {tipo_vivienda_final}<br>"
                    f"✅ <strong>Contratado:</strong> {contrato}<br>"
                    f"⚠️ <strong>Incidencia:</strong> {contiene_incidencias}<br>"
                )
                if contiene_incidencias == "Sí":
                    descripcion_oferta += f"📄 <strong>Motivo Incidencia:</strong> {motivo_incidencia}<br>"
                    descripcion_oferta += f"🏠 <strong>Ocupado por tercero:</strong> {'Sí' if ocupado_tercero else 'No'}<br>"
            else:
                descripcion_oferta += f"❌ <strong>Motivo No Servicio:</strong> {motivo_serviciable}<br>"

            if alt_address:
                descripcion_oferta += f"📍 <strong>Dirección Alternativa:</strong> {alt_address}<br>"
            if observations:
                descripcion_oferta += f"💬 <strong>Observaciones:</strong> {observations}<br>"

            descripcion_oferta += "<br>ℹ️ Por favor, revise los detalles de la oferta y asegúrese de que toda la información sea correcta."

            # Enviar notificaciones por email
            if emails_admin:
                for email in emails_admin:
                    correo_oferta_comercial(email, apartment_id, descripcion_oferta)

                if email_comercial:
                    correo_oferta_comercial(email_comercial, apartment_id, descripcion_oferta)

                st.toast("✅ Oferta enviada con éxito")
                st.toast(
                    f"📧 Se ha enviado una notificación a: {', '.join(emails_admin + ([email_comercial] if email_comercial else []))}")
            else:
                st.warning("⚠️ No se encontró ningún email de administrador/gestor, no se pudo enviar la notificación.")

        st.toast("✅ Oferta enviada correctamente.")

if __name__ == "__main__":
    comercial_dashboard()