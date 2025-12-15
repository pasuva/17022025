import streamlit as st
from branca.element import Template, MacroElement
from folium.plugins import MarkerCluster
import pandas as pd
import os, re, time, folium, sqlitecloud
from streamlit_folium import st_folium
import streamlit.components.v1 as components
from datetime import datetime, timedelta
from modules import login
from folium.plugins import Geocoder
from modules.cloudinary import upload_image_to_cloudinary
from modules.notificaciones import correo_oferta_comercial, correo_viabilidad_comercial, correo_respuesta_comercial, \
    correo_envio_presupuesto_manual
from streamlit_option_menu import option_menu
from streamlit_cookies_controller import CookieController  # Se importa localmente
import secrets
import urllib.parse
import warnings
warnings.filterwarnings("ignore", category=UserWarning)

cookie_name = "my_app"

# Función para obtener conexión a la base de datos (SQLite Cloud)
def get_db_connection():
    return sqlitecloud.connect(
        "sqlitecloud://ceafu04onz.g6.sqlite.cloud:8860/usuarios.db?apikey=Qo9m18B9ONpfEGYngUKm99QB5bgzUTGtK7iAcThmwvY"
    )

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

def guardar_en_base_de_datos_vip(oferta_data, imagen_incidencia, apartment_id):
    """Guarda o actualiza la oferta en SQLite para comercial VIP."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Subir la imagen a Cloudinary si hay incidencia
        imagen_url = None
        if oferta_data["incidencia"] == "Sí" and imagen_incidencia:
            extension = os.path.splitext(imagen_incidencia.name)[1]
            filename = f"{apartment_id}{extension}"
            imagen_url = upload_image_to_cloudinary(imagen_incidencia, filename)

        comercial_logueado = st.session_state.get("username", None)

        # Verificar si ya existe en comercial_rafa
        cursor.execute("SELECT comercial FROM comercial_rafa WHERE apartment_id = ?", (apartment_id,))
        row = cursor.fetchone()

        if row:
            comercial_asignado = row[0]

            if comercial_asignado and str(comercial_asignado).strip() != "":
                st.toast(f"❌ El Apartment ID {apartment_id} ya está asignado al comercial '{comercial_asignado}'. "
                         f"No se puede modificar desde este panel.")
                conn.close()
                return

            # --- UPDATE si no está asignado ---
            cursor.execute("""
                UPDATE comercial_rafa SET
                    provincia = ?, municipio = ?, poblacion = ?, vial = ?, numero = ?, letra = ?,
                    cp = ?, latitud = ?, longitud = ?, nombre_cliente = ?, telefono = ?,
                    direccion_alternativa = ?, observaciones = ?, serviciable = ?, motivo_serviciable = ?,
                    incidencia = ?, motivo_incidencia = ?, fichero_imagen = ?, fecha = ?, Tipo_Vivienda = ?,
                    Contrato = ?, comercial = ?
                WHERE apartment_id = ?
            """, (
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
                imagen_url,
                oferta_data["fecha"].strftime('%Y-%m-%d %H:%M:%S'),
                oferta_data["Tipo_Vivienda"],
                oferta_data["Contrato"],
                comercial_logueado,
                apartment_id
            ))
            st.toast(f"✅ ¡Oferta actualizada en comercial_rafa para {apartment_id}!")

        else:
            # --- INSERT ---
            cursor.execute("""
                SELECT provincia, municipio, poblacion, vial, numero, letra, cp, latitud, longitud
                FROM datos_uis WHERE apartment_id = ?
            """, (apartment_id,))
            row = cursor.fetchone()
            if not row:
                st.toast(f"❌ El apartment_id {apartment_id} no existe en datos_uis.")
                conn.close()
                return

            provincia, municipio, poblacion, vial, numero, letra, cp, lat, lon = row

            cursor.execute("""
                INSERT INTO comercial_rafa (
                    apartment_id, provincia, municipio, poblacion, vial, numero, letra, cp, latitud, longitud,
                    nombre_cliente, telefono, direccion_alternativa, observaciones, serviciable, motivo_serviciable,
                    incidencia, motivo_incidencia, fichero_imagen, fecha, Tipo_Vivienda, Contrato, comercial
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                apartment_id, provincia, municipio, poblacion, vial, numero, letra, cp, lat, lon,
                oferta_data["Nombre Cliente"],
                oferta_data["Teléfono"],
                oferta_data["Dirección Alternativa"],
                oferta_data["Observaciones"],
                oferta_data["serviciable"],
                oferta_data["motivo_serviciable"],
                oferta_data["incidencia"],
                oferta_data["motivo_incidencia"],
                imagen_url,
                oferta_data["fecha"].strftime('%Y-%m-%d %H:%M:%S'),
                oferta_data["Tipo_Vivienda"],
                oferta_data["Contrato"],
                comercial_logueado
            ))
            st.toast(f"✅ ¡Oferta insertada en comercial_rafa para {apartment_id}!")

        conn.commit()
        conn.close()

        # Registrar trazabilidad
        log_trazabilidad(comercial_logueado, "Guardar/Actualizar Oferta",
                         f"Oferta guardada para Apartment ID: {apartment_id}")

    except Exception as e:
        st.toast(f"❌ Error al guardar/actualizar la oferta: {e}")


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


def comercial_dashboard_vip():
    """Muestra el mapa y formulario de Ofertas Comerciales para el comercial VIP (ve toda la huella con filtros persistentes)."""
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

    # --- SIDEBAR ---
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
            <div class="user-info">Rol: Comercial VIP</div>
            <div class="welcome-msg">Bienvenido, <strong>{username}</strong></div>
            <hr>
            """.replace("{username}", st.session_state.get('username', 'N/A')), unsafe_allow_html=True)

        menu_opcion = option_menu(
            menu_title=None,
            options=["Ofertas Comerciales", "Viabilidades", "Visualización de Datos","Precontratos"],
            icons=["bar-chart", "check-circle", "graph-up","file-text"],
            menu_icon="list",
            default_index=0,
            styles={
                "container": {"padding": "0px", "background-color": "#F0F7F2"},
                "icon": {"color": "#2C5A2E", "font-size": "18px"},
                "nav-link": {
                    "color": "#2C5A2E",
                    "font-size": "16px",
                    "text-align": "left",
                    "margin": "0px",
                    "--hover-color": "#66B032",
                    "border-radius": "0px",
                },
                "nav-link-selected": {
                    "background-color": "#66B032",
                    "color": "white",
                    "font-weight": "bold"
                }
            }
        )

    detalles = f"El usuario seleccionó la vista '{menu_opcion}'."
    log_trazabilidad(st.session_state.get("username", "N/A"), "Selección de vista", detalles)

    if "username" not in st.session_state or not st.session_state.get("username"):
        st.warning("⚠️ No has iniciado sesión. Por favor, inicia sesión para continuar.")
        time.sleep(1.5)
        try:
            login.login()
        except Exception:
            pass
        return

    comercial = st.session_state.get("username")

    # --- CERRAR SESIÓN ---
    with st.sidebar:
        if st.button("Cerrar sesión"):
            detalles = f"El comercial {st.session_state.get('username', 'N/A')} cerró sesión."
            log_trazabilidad(st.session_state.get("username", "N/A"), "Cierre sesión", detalles)
            if controller.get(f'{cookie_name}_session_id'):
                controller.set(f'{cookie_name}_session_id', '', max_age=0, path='/')
            if controller.get(f'{cookie_name}_username'):
                controller.set(f'{cookie_name}_username', '', max_age=0, path='/')
            if controller.get(f'{cookie_name}_role'):
                controller.set(f'{cookie_name}_role', '', max_age=0, path='/')
            st.session_state["login_ok"] = False
            st.session_state["username"] = ""
            st.session_state["role"] = ""
            st.session_state["session_id"] = ""
            st.toast("✅ Has cerrado sesión correctamente. Redirigiendo al login...")
            st.rerun()

    marker_icon_type = 'info-sign'

    # --- DASHBOARD ---
    if menu_opcion == "Ofertas Comerciales":
        log_trazabilidad(comercial, "Visualización de Dashboard VIP",
                         "El comercial VIP visualizó la sección de Ofertas Comerciales.")
        mostrar_ultimo_anuncio()
        # ----- FILTROS -----
        with st.spinner("⏳ Cargando filtros..."):
            try:
                conn = get_db_connection()
                provincias = pd.read_sql("SELECT DISTINCT provincia FROM datos_uis ORDER BY provincia", conn)[
                    "provincia"].dropna().tolist()
                conn.close()
            except Exception as e:
                st.toast(f"❌ Error al cargar filtros: {e}")
                return

        provincia_sel = st.selectbox("🌍 Selecciona provincia", ["Todas"] + provincias, key="vip_provincia")

        municipios = []
        if provincia_sel != "Todas":
            conn = get_db_connection()
            municipios = pd.read_sql(
                "SELECT DISTINCT municipio FROM datos_uis WHERE provincia = ? ORDER BY municipio",
                conn, params=(provincia_sel,)
            )["municipio"].dropna().tolist()
            conn.close()
        municipio_sel = st.selectbox("🏘️ Selecciona municipio", ["Todos"] + municipios,
                                     key="vip_municipio") if municipios else "Todos"

        poblaciones = []
        if municipio_sel != "Todos":
            conn = get_db_connection()
            poblaciones = pd.read_sql(
                "SELECT DISTINCT poblacion FROM datos_uis WHERE provincia = ? AND municipio = ? ORDER BY poblacion",
                conn, params=(provincia_sel, municipio_sel)
            )["poblacion"].dropna().tolist()
            conn.close()
        poblacion_sel = st.selectbox("🏡 Selecciona población", ["Todas"] + poblaciones,
                                     key="vip_poblacion") if poblaciones else "Todas"

        # NUEVO CHECKBOX: sin comercial asignado
        sin_comercial = st.checkbox("Mostrar solo apartamentos sin comercial asignado", key="vip_sin_comercial")
        solo_mios = st.checkbox("Mostrar solo mis puntos asignados", key="vip_solo_mios")

        # Botones: aplicar y limpiar
        colA, colB = st.columns([1, 1])
        with colA:
            aplicar = st.button("🔍 Aplicar filtros", key="vip_apply")
        with colB:
            limpiar = st.button("🧹 Limpiar filtros", key="vip_clear")

        if limpiar:
            st.session_state.pop("vip_filtered_df", None)
            st.session_state.pop("vip_filters", None)
            st.toast("🧹 Filtros limpiados.")
            st.rerun()

        if aplicar:
            with st.spinner("⏳ Cargando puntos filtrados..."):
                try:
                    conn = get_db_connection()
                    query = """
                        SELECT d.apartment_id,
                               d.provincia,
                               d.municipio,
                               d.poblacion,
                               d.vial,
                               d.numero,
                               d.letra,
                               d.cp,
                               d.latitud,
                               d.longitud,
                               d.serviciable,
                               c.comercial,
                               c.Contrato
                        FROM datos_uis d
                        LEFT JOIN comercial_rafa c ON d.apartment_id = c.apartment_id
                        WHERE 1=1
                    """
                    params = []

                    if provincia_sel != "Todas":
                        query += " AND d.provincia = ?"
                        params.append(provincia_sel)
                    if municipio_sel != "Todos":
                        query += " AND d.municipio = ?"
                        params.append(municipio_sel)
                    if poblacion_sel != "Todas":
                        query += " AND d.poblacion = ?"
                        params.append(poblacion_sel)

                    # FILTRO NUEVO: solo sin comercial asignado
                    if sin_comercial:
                        query += " AND (c.comercial IS NULL OR TRIM(c.comercial) = '')"

                    # Filtro: solo mis puntos asignados (ignorando mayúsculas/minúsculas)
                    if solo_mios:
                        query += " AND LOWER(TRIM(c.comercial)) = LOWER(TRIM(?))"
                        params.append(comercial)

                    df = pd.read_sql(query, conn, params=params)
                    conn.close()

                    if df.empty:
                        st.warning("⚠️ No hay datos para los filtros seleccionados.")
                    else:
                        st.session_state["vip_filtered_df"] = df
                        st.session_state["vip_filters"] = {
                            "provincia": provincia_sel,
                            "municipio": municipio_sel,
                            "poblacion": poblacion_sel,
                            "sin_comercial": sin_comercial,
                            "solo_mios": solo_mios
                        }
                        st.toast(f"✅ Se han cargado {len(df)} puntos. (Filtros guardados en sesión)")

                except Exception as e:
                    st.toast(f"❌ Error al cargar los datos filtrados: {e}")

        # ------ RENDER DEL MAPA (si hay df en session_state) ------
        df_to_show = st.session_state.get("vip_filtered_df")
        if df_to_show is not None:
            df = df_to_show  # DataFrame a usar para el mapa

            # --- Preparar y mostrar mapa ---
            if "clicks" not in st.session_state:
                st.session_state.clicks = []

            location = get_user_location()
            if "ultima_lat" in st.session_state and "ultima_lon" in st.session_state:
                lat, lon = st.session_state["ultima_lat"], st.session_state["ultima_lon"]
            elif location is None:
                lat, lon = 43.463444, -3.790476
            else:
                lat, lon = location

            with st.spinner("⏳ Cargando mapa..."):
                try:
                    # Si hay más de un punto, centramos en todos los puntos; si solo uno, zoom cercano
                    if len(df) == 1:
                        lat, lon = df['latitud'].iloc[0], df['longitud'].iloc[0]
                        m = folium.Map(location=[lat, lon], zoom_start=18, max_zoom=21,
                                       tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}", attr="Google")
                    else:
                        # centro aproximado
                        lat, lon = df['latitud'].mean(), df['longitud'].mean()
                        m = folium.Map(location=[lat, lon], zoom_start=12, max_zoom=21,
                                       tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}", attr="Google")
                        # ajustar límites al bounding box de todos los puntos
                        bounds = [[df['latitud'].min(), df['longitud'].min()],
                                  [df['latitud'].max(), df['longitud'].max()]]
                        m.fit_bounds(bounds)

                    Geocoder().add_to(m)

                    # decidir cluster según tamaño
                    if len(df) < 500:
                        cluster_layer = m
                    else:
                        cluster_layer = MarkerCluster(maxClusterRadius=5, minClusterSize=3).add_to(m)

                    coord_counts = {}
                    for _, row in df.iterrows():
                        coord = (row['latitud'], row['longitud'])
                        coord_counts[coord] = coord_counts.get(coord, 0) + 1

                    for _, row in df.iterrows():
                        apartment_id = row['apartment_id']
                        comercial_asignado = row['comercial'] if row['comercial'] else "Sin asignar"
                        contrato_val = row['Contrato'] if row['Contrato'] else "N/A"
                        serviciable_val = str(row.get("serviciable", "")).strip().lower()

                        # Colores
                        if serviciable_val == "no":
                            marker_color = 'red'
                        elif serviciable_val == "si":
                            marker_color = 'green'
                        elif isinstance(contrato_val, str) and contrato_val.strip().lower() == "sí":
                            marker_color = 'orange'
                        elif isinstance(contrato_val, str) and contrato_val.strip().lower() == "no interesado":
                            marker_color = 'black'
                        else:
                            marker_color = 'blue'

                        popup_text = f"""
                        🏠 ID: {apartment_id}<br>
                        📍 {row['latitud']}, {row['longitud']}<br>
                        ✅ Serviciable: {row.get('serviciable', 'N/D')}<br>
                        👤 Comercial: {comercial_asignado}<br>
                        📑 Contrato: {contrato_val}
                        """

                        coord = (row['latitud'], row['longitud'])
                        offset_factor = coord_counts[coord]
                        if offset_factor > 1:
                            lat_offset = offset_factor * 0.00003
                            lon_offset = offset_factor * -0.00003
                        else:
                            lat_offset, lon_offset = 0, 0
                        new_lat = row['latitud'] + lat_offset
                        new_lon = row['longitud'] + lon_offset
                        coord_counts[coord] -= 1

                        folium.Marker(
                            location=[new_lat, new_lon],
                            popup=popup_text,
                            icon=folium.Icon(color=marker_color, icon=marker_icon_type)
                        ).add_to(cluster_layer)

                    # Leyenda
                    legend = """
                                {% macro html(this, kwargs) %}
                                <div style="
                                    position: fixed; 
                                    bottom: 0px; left: 0px; width: 220px; 
                                    z-index:9999; 
                                    font-size:14px;
                                    background-color: white;
                                    color: black;
                                    border:2px solid grey;
                                    border-radius:8px;
                                    padding: 10px;
                                    box-shadow: 2px 2px 6px rgba(0,0,0,0.3);
                                ">
                                <b>Leyenda</b><br>
                                <i style="color:green;">●</i> Serviciable<br>
                                <i style="color:red;">●</i> No serviciable<br>
                                <i style="color:orange;">●</i> Contrato Sí<br>
                                <i style="color:black;">●</i> No interesado<br>
                                <i style="color:blue;">●</i> Sin información/No visitado<br>
                                </div>
                                {% endmacro %}
                                """
                    macro = MacroElement()
                    macro._template = Template(legend)
                    m.get_root().add_child(macro)

                    map_data = st_folium(m, height=680, width="100%")
                except Exception as e:
                    st.toast(f"❌ Error al cargar los datos en el mapa: {e}")

            # Clicks y formulario (igual que antes)
            if map_data and "last_object_clicked" in map_data and map_data["last_object_clicked"]:
                st.session_state.clicks.append(map_data["last_object_clicked"])

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

        else:
            st.info("Selecciona filtros y pulsa 'Aplicar filtros' para cargar los puntos en el mapa.")

    # Sección de Viabilidades
    elif menu_opcion == "Viabilidades":
        viabilidades_section()

    # Sección de Visualización de datos
    elif menu_opcion == "Visualización de Datos":
        st.subheader("Datos de Ofertas con Contrato")

        # Verificar si el usuario ha iniciado sesión
        if "username" not in st.session_state:
            st.toast("❌ No has iniciado sesión. Por favor, vuelve a la pantalla de inicio de sesión.")
            st.stop()

        comercial_usuario = st.session_state.get("username", None)

        try:
            conn = get_db_connection()
            # Consulta SQL con filtro por comercial logueado (primera tabla: comercial_rafa) LOWER(Contrato) = 'sí'
            #             AND
            query_ofertas = """
            SELECT *
            FROM comercial_rafa
            WHERE LOWER(comercial) = LOWER(?)
            """

            df_ofertas = pd.read_sql(query_ofertas, conn, params=(comercial_usuario,))

            # ⬇️ Pega aquí el nuevo bloque
            query_seguimiento = """
                            SELECT apartment_id, estado
                            FROM seguimiento_contratos
                            WHERE LOWER(estado) = 'finalizado'
                        """
            df_seguimiento = pd.read_sql(query_seguimiento, conn)
            df_ofertas['Contrato_Activo'] = df_ofertas['apartment_id'].isin(df_seguimiento['apartment_id']).map(
                {True: '✅ Activo', False: '❌ No Activo'})

            # Consulta SQL para la segunda tabla: viabilidades (filtrando por el nombre del comercial logueado)
            query_viabilidades = """
            SELECT v.ticket, v.latitud, v.longitud, v.provincia, v.municipio, v.poblacion, v.vial, v.numero, v.letra, v.cp, 
                   v.serviciable, v.coste, v.comentarios_comercial, v.comentarios_internos, v.nombre_cliente, v.telefono, v.justificacion, v.Presupuesto_enviado, v.resultado, v.respuesta_comercial
            FROM viabilidades v
            WHERE LOWER(v.usuario) = LOWER(?)
            """

            df_viabilidades = pd.read_sql(query_viabilidades, conn, params=(comercial_usuario,))

            conn.close()

            # Verificar si hay datos para mostrar en la primera tabla (ofertas_comercial)
            if df_ofertas.empty:
                st.warning(f"⚠️ No hay ofertas con contrato activo para el comercial '{comercial_usuario}'.")
            else:
                st.subheader("📋 Tabla de Visitas/Ofertas")
                st.dataframe(df_ofertas, width='stretch')

            # Verificar si hay datos para mostrar en la segunda tabla (viabilidades)
            # Mostrar segunda tabla (viabilidades)
            if df_viabilidades.empty:
                st.warning(f"⚠️ No hay viabilidades disponibles para el comercial '{comercial_usuario}'.")
            else:
                st.subheader("📋 Tabla de Viabilidades")
                st.dataframe(df_viabilidades, width='stretch')

                # Filtrar viabilidades críticas por justificación
                justificaciones_criticas = ["MAS PREVENTA", "PDTE. RAFA FIN DE OBRA"]

                # Filtrar viabilidades críticas por resultado
                resultados_criticos = ["PDTE INFORMACION RAFA", "OK", "SOBRECOSTE"]

                # Filtrar las viabilidades que cumplen la condición
                df_condiciones = df_viabilidades[
                    (df_viabilidades['justificacion'].isin(justificaciones_criticas)) |
                    (df_viabilidades['resultado'].isin(resultados_criticos))
                    ]

                # Filtrar solo las que aún NO tienen respuesta_comercial
                df_pendientes = df_condiciones[
                    df_condiciones['respuesta_comercial'].isna() | (df_condiciones['respuesta_comercial'] == "")
                    ]

                if not df_pendientes.empty:
                    st.warning(f"🔔 Tienes {len(df_pendientes)} viabilidades pendientes de contestar.")

                    st.subheader("📝 Añadir comentarios a Viabilidades pendientes")

                    for _, row in df_pendientes.iterrows():
                        with st.expander(f"Ticket {row['ticket']} - {row['municipio']} {row['vial']} {row['numero']}"):
                            # Mostrar información contextual
                            st.markdown(f"""
                                **👤 Nombre del cliente:**  
                                {row.get('nombre_cliente', '—')}

                                **📌 Justificación oficina:**  
                                {row.get('justificacion', '—')}

                                **📊 Resultado oficina:**  
                                {row.get('resultado', '—')}

                                **💬 Comentarios a comercial:**  
                                {row.get('comentarios_comercial', '—')}

                                **🧩 Comentarios internos:**  
                                {row.get('comentarios_internos', '—')}
                            """)

                            with st.expander("📝 Instrucciones para completar este campo", expanded=False):
                                st.info("""
                                ℹ️ **Por favor, completa este campo indicando:**  
                                - Si estás de acuerdo o no con la resolución.  
                                - Información adicional de tu visita (cliente, obra, accesos, etc.), detalles que ayuden a la oficina a cerrar la viabilidad.  
                                - Si el cliente acepta o no el presupuesto.
                                """)
                            nuevo_comentario = st.text_area(
                                f"✏️ Comentario para ticket {row['ticket']}",
                                value="",
                                placeholder="Ejemplo: El cliente confirma que esperará a fin de obra para contratar...",
                                key=f"comentario_{row['ticket']}"
                            )

                            if st.button(f"💾 Guardar comentario ({row['ticket']})", key=f"guardar_{row['ticket']}"):
                                try:
                                    conn = get_db_connection()
                                    cursor = conn.cursor()

                                    # Guardar la respuesta del comercial
                                    cursor.execute(
                                        "UPDATE viabilidades SET respuesta_comercial = ? WHERE ticket = ?",
                                        (nuevo_comentario, row['ticket'])
                                    )

                                    conn.commit()
                                    conn.close()

                                    # 🔔 Enviar notificación por correo a administradores y comercial_jefe
                                    # Obtener emails de administradores y comercial_jefe
                                    conn = get_db_connection()
                                    cursor = conn.cursor()
                                    cursor.execute(
                                        "SELECT email FROM usuarios WHERE role IN ('admin')")
                                    destinatarios = [fila[0] for fila in cursor.fetchall()]
                                    conn.close()

                                    for email in destinatarios:
                                        correo_respuesta_comercial(email, row['ticket'], comercial_usuario,
                                                                   nuevo_comentario)

                                    st.toast(
                                        f"✅ Comentario guardado y notificación enviada para el ticket {row['ticket']}.")
                                    st.rerun()  # 🔄 Refrescar la página para que desaparezca de pendientes
                                except Exception as e:
                                    st.toast(f"❌ Error al guardar el comentario para el ticket {row['ticket']}: {e}")
                else:
                    st.info("🎉 No tienes viabilidades pendientes de contestar. ✅")

        except Exception as e:
            st.toast(f"❌ Error al cargar los datos: {e}")


    elif menu_opcion == "Precontratos":

        st.title("📑 Gestión de Precontratos")
        # Pestañas para diferentes funcionalidades
        tab1, tab2 = st.tabs(["🆕 Crear Nuevo Precontrato", "📋 Precontratos Existentes"])

        with tab1:
            st.subheader("Crear Nuevo Precontrato")
            st.info("""
            💡 **Información:**
            - En esta sección puedes crear precontratos sin necesidad de tener un Apartment ID asociado
            - El cliente completará los datos faltantes a través del enlace que se generará
            - Solo los campos de tarifa, precio y permanencia son obligatorios
            - Puedes completar otros campos ahora si lo deseas
            """)

            # FORMULARIO INDEPENDIENTE PARA PRECONTRATOS
            with st.expander("📑 Formulario de Precontrato", expanded=True):
                with st.form(key="form_precontrato_standalone"):
                    st.markdown("Completa los datos básicos del precontrato")
                    st.info(
                        "💡 **Nota:** Solo los campos de tarifa, precio y permanencia son obligatorios. El cliente completará el resto en el formulario, pero puedes llenarlos ahora si lo prefieres.")
                    # Cargar tarifas
                    @st.cache_data(ttl=300)
                    def cargar_tarifas():
                        conn = get_db_connection()
                        df = pd.read_sql("SELECT id, nombre, descripcion, precio FROM tarifas", conn)
                        conn.close()
                        return df
                    try:
                        tarifas_df = cargar_tarifas()

                    except Exception as e:
                        st.toast(f"⚠️ No se pudieron cargar las tarifas: {e}")
                        tarifas_df = pd.DataFrame()

                    # Selección de tarifa - OBLIGATORIO
                    if not tarifas_df.empty:
                        opciones_tarifas = [
                            f"{row['nombre']} – {row['descripcion']} ({row['precio']}€)"
                            for _, row in tarifas_df.iterrows()
                        ]

                        tarifa_seleccionada = st.selectbox(
                            "💰 Selecciona una tarifa disponible:*",
                            options=opciones_tarifas,
                            key="tarifa_precontrato_standalone"
                        )
                        tarifa_nombre = tarifa_seleccionada.split(" – ")[0] if tarifa_seleccionada else None

                    else:
                        st.toast("⚠️ No hay tarifas registradas en la base de datos.")
                        tarifa_nombre = None

                    # Campo Apartment ID - opcional
                    apartment_id = st.text_input("🏢 Apartment ID (opcional)",
                                                 key="apartment_id_standalone",
                                                 placeholder="Dejar vacío si no hay Apartment ID asociado")

                    # PRECIO - OBLIGATORIO (puede ser 0)
                    precio = st.text_input(
                        "💵 Precio Total (€ I.V.A Incluido)*",
                        key="precio_standalone",
                        placeholder="Ej: 1200,50 o 0"
                    )

                    # PERMANENCIA - OBLIGATORIO
                    permanencia = st.radio(
                        "📆 Permanencia (meses)*",
                        options=[12, 24],
                        key="permanencia_standalone",
                        horizontal=True
                    )

                    # CAMPOS OPCIONALES ADICIONALES - AÑADIDOS
                    st.subheader("📋 Datos del Cliente (Opcionales)")
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        nombre = st.text_input("👤 Nombre / Razón social", key="nombre_standalone")
                        cif = st.text_input("🏢 CIF", key="cif_standalone")
                        nombre_legal = st.text_input("👥 Nombre Legal (si aplica)", key="nombre_legal_standalone")

                    with col2:
                        nif = st.text_input("🪪 NIF / DNI", key="nif_standalone")
                        telefono1 = st.text_input("📞 Teléfono 1", key="telefono1_standalone")
                        telefono2 = st.text_input("📞 Teléfono 2", key="telefono2_standalone")

                    with col3:

                        mail = st.text_input("✉️ Email", key="mail_standalone", placeholder="usuario@dominio.com")
                        comercial = st.text_input("🧑‍💼 Comercial", value=st.session_state.get("username", ""),
                                                  key="comercial_standalone")
                        fecha = st.date_input("📅 Fecha", datetime.now().date(), key="fecha_standalone")

                    direccion = st.text_input("🏠 Dirección", key="direccion_standalone")
                    col4, col5, col6 = st.columns(3)

                    with col4:
                        cp = st.text_input("📮 Código Postal", key="cp_standalone")

                    with col5:
                        poblacion = st.text_input("🏘️ Población", key="poblacion_standalone")

                    with col6:
                        provincia = st.text_input("🌍 Provincia", key="provincia_standalone")
                    col7, col8 = st.columns(2)

                    with col7:
                        iban = st.text_input(
                            "🏦 IBAN",
                            key="iban_standalone",
                            placeholder="ES00 0000 0000 0000 0000 0000"
                        )

                    with col8:
                        bic = st.text_input(
                            "🏦 BIC",
                            key="bic_standalone",
                            placeholder="AAAAESMMXXX"
                        )

                    # Campos originales opcionales
                    observaciones = st.text_area("📝 Observaciones (opcional)",
                                                 key="observaciones_standalone",
                                                 placeholder="Observaciones adicionales sobre el contrato...")

                    servicio_adicional = st.text_area(
                        "➕ Servicio Adicional (opcional)",
                        key="servicio_adicional_standalone",
                        placeholder="Servicios adicionales contratrados..."
                    )

                    # SECCIONES DE LÍNEAS (OPCIONALES) - AÑADIDAS
                    st.subheader("📞 Líneas de Comunicación (Opcionales)")
                    with st.expander("📞 Línea Fija", expanded=False):
                        colf1, colf2, colf3 = st.columns(3)

                        with colf1:
                            fija_tipo = st.selectbox("Tipo", ["nuevo", "portabilidad"], key="fija_tipo_standalone")
                            fija_numero = st.text_input("Número a portar / nuevo", key="fija_numero_standalone")

                        with colf2:
                            fija_titular = st.text_input("Titular", key="fija_titular_standalone")
                            fija_dni = st.text_input("DNI Titular", key="fija_dni_standalone")

                        with colf3:
                            fija_operador = st.text_input("Operador Donante", key="fija_operador_standalone")
                            fija_icc = st.text_input("ICC (prepago, si aplica)", key="fija_icc_standalone")

                    with st.expander("📱 Línea Móvil Principal", expanded=False):
                        colm1, colm2, colm3 = st.columns(3)

                        with colm1:
                            movil_tipo = st.selectbox("Tipo", ["nuevo", "portabilidad"], key="movil_tipo_standalone")
                            movil_numero = st.text_input("Número a portar / nuevo", key="movil_numero_standalone")

                        with colm2:
                            movil_titular = st.text_input("Titular", key="movil_titular_standalone")
                            movil_dni = st.text_input("DNI Titular", key="movil_dni_standalone")

                        with colm3:
                            movil_operador = st.text_input("Operador Donante", key="movil_operador_standalone")
                            movil_icc = st.text_input("ICC (prepago, si aplica)", key="movil_icc_standalone")

                    # Líneas móviles adicionales
                    with st.expander("📶 Líneas Móviles Adicionales", expanded=False):
                        lineas_adicionales = []
                        for i in range(1, 6):
                            with st.expander(f"Línea móvil adicional #{i}", expanded=False):
                                col1, col2, col3 = st.columns(3)
                                with col1:
                                    tipo = st.selectbox("Tipo", ["nuevo", "portabilidad"],
                                                        key=f"adicional_tipo_{i}_standalone")
                                    numero = st.text_input("Número a portar / nuevo",
                                                           key=f"adicional_numero_{i}_standalone")

                                with col2:
                                    titular = st.text_input("Titular", key=f"adicional_titular_{i}_standalone")
                                    dni = st.text_input("DNI Titular", key=f"adicional_dni_{i}_standalone")

                                with col3:
                                    operador = st.text_input("Operador Donante",
                                                             key=f"adicional_operador_{i}_standalone")
                                    icc = st.text_input("ICC (prepago, si aplica)", key=f"adicional_icc_{i}_standalone")

                                if numero:
                                    lineas_adicionales.append({
                                        "tipo": "movil_adicional",
                                        "numero_nuevo_portabilidad": tipo,
                                        "numero_a_portar": numero,
                                        "titular": titular,
                                        "dni": dni,
                                        "operador_donante": operador,
                                        "icc": icc
                                    })
                    submit_precontrato = st.form_submit_button("💾 Guardar precontrato")

                    if submit_precontrato:
                        # Validaciones antes de guardar - SOLO LOS 3 CAMPOS OBLIGATORIOS
                        errores = []
                        # 1. Validar tarifa - OBLIGATORIO
                        if not tarifa_nombre:
                            errores.append("❌ Debes seleccionar una tarifa")
                        # 2. Validar precio - OBLIGATORIO (puede ser 0)
                        if not precio:
                            errores.append("❌ El campo 'Precio' es obligatorio")
                        else:
                            try:
                                precio_limpio = precio.replace(",", ".").replace(" ", "")
                            except ValueError:
                                errores.append("❌ El precio debe ser un número válido")

                        # Mostrar errores si los hay
                        if errores:
                            for error in errores:
                                st.error(error)
                        else:
                            # Si todas las validaciones pasan, proceder con el guardado
                            try:
                                conn = get_db_connection()
                                cursor = conn.cursor()

                                # 1️⃣ Insertar precontrato
                                cursor.execute("""
                                    INSERT INTO precontratos (
                                        apartment_id, tarifas, observaciones, precio, comercial,
                                        nombre, cif, nombre_legal, nif, telefono1, telefono2, mail, direccion,
                                        cp, poblacion, provincia, iban, bic, fecha, firma, permanencia,
                                        servicio_adicional, precontrato_id
                                    )
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """, (
                                    apartment_id if apartment_id else None,
                                    tarifa_nombre,
                                    observaciones or "",
                                    precio,
                                    comercial,
                                    nombre or "",  # nombre
                                    cif or "",  # cif
                                    nombre_legal or "",  # nombre_legal
                                    nif or "",  # nif
                                    telefono1 or "",  # telefono1
                                    telefono2 or "",  # telefono2
                                    mail or "",  # mail
                                    direccion or "",  # direccion
                                    cp or "",  # cp
                                    poblacion or "",  # poblacion
                                    provincia or "",  # provincia
                                    iban or "",  # iban
                                    bic or "",  # bic
                                    str(fecha),
                                    "",  # firma
                                    permanencia,
                                    servicio_adicional or "",
                                    f"PRE-{int(datetime.now().timestamp())}"  # identificador público
                                ))

                                precontrato_pk = cursor.lastrowid
                                # 2️⃣ Insertar líneas asociadas si existen
                                lineas = [
                                             {"tipo": "fija", "numero_nuevo_portabilidad": fija_tipo,
                                              "numero_a_portar": fija_numero,
                                              "titular": fija_titular, "dni": fija_dni,
                                              "operador_donante": fija_operador, "icc": fija_icc},
                                             {"tipo": "movil", "numero_nuevo_portabilidad": movil_tipo,
                                              "numero_a_portar": movil_numero,
                                              "titular": movil_titular, "dni": movil_dni,
                                              "operador_donante": movil_operador, "icc": movil_icc}
                                         ] + lineas_adicionales

                                for linea in lineas:
                                    if linea["numero_a_portar"]:  # Solo insertar si hay número
                                        cursor.execute("""
                                            INSERT INTO lineas (
                                                precontrato_id, tipo, numero_nuevo_portabilidad, numero_a_portar,
                                                titular, dni, operador_donante, icc
                                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                        """, (
                                            precontrato_pk,
                                            linea["tipo"],
                                            linea["numero_nuevo_portabilidad"],
                                            linea["numero_a_portar"],
                                            linea["titular"],
                                            linea["dni"],
                                            linea["operador_donante"],
                                            linea["icc"]
                                        ))

                                # 3️⃣ Generar token de acceso temporal
                                token_valido = False
                                max_intentos = 5
                                intentos = 0
                                while not token_valido and intentos < max_intentos:
                                    token = secrets.token_urlsafe(16)
                                    cursor.execute("SELECT id FROM precontrato_links WHERE token = ?", (token,))

                                    if cursor.fetchone() is None:
                                        token_valido = True
                                    intentos += 1

                                if not token_valido:
                                    st.error("❌ No se pudo generar un token único, intenta nuevamente.")
                                else:
                                    expiracion = datetime.now() + timedelta(hours=24)
                                    cursor.execute("""
                                        INSERT INTO precontrato_links (precontrato_id, token, expiracion, usado)
                                        VALUES (?, ?, ?, 0)
                                    """, (precontrato_pk, token, expiracion))
                                    conn.commit()
                                    conn.close()

                                    #base_url="http://localhost:8501"

                                    base_url = "https://one7022025.onrender.com"
                                    link_cliente = f"{base_url}?precontrato_id={precontrato_pk}&token={urllib.parse.quote(token)}"
                                    st.success("✅ Precontrato guardado correctamente.")
                                    st.markdown(f"📎 **Enlace para el cliente (válido 24 h):**")
                                    st.code(link_cliente, language="text")

                                    st.info(
                                        "💡 Copia este enlace y envíalo al cliente por WhatsApp. Solo podrá usarse una vez.")

                                    # Guardar en session_state para mostrar el botón de copiar
                                    st.session_state.precontrato_guardado = True
                                    st.session_state.ultimo_enlace = link_cliente

                            except Exception as e:
                                st.error(f"❌ Error al guardar el precontrato: {e}. Detalles del error: {str(e)}")

                # Botón para copiar enlace (fuera del formulario)
                if st.session_state.get('precontrato_guardado', False) and 'ultimo_enlace' in st.session_state:
                        st.toast("🔗 Enlace copiado al portapapeles")

        with tab2:
            st.subheader("Precontratos Existentes")

            # Conexión a la base de datos para mostrar precontratos existentes
            conn = get_db_connection()
            cursor = conn.cursor()

            # Obtener precontratos (los más recientes primero) - CON NUEVOS CAMPOS
            cursor.execute("""
                SELECT p.id, p.precontrato_id, p.apartment_id, p.nombre, p.tarifas, p.precio, 
                       p.fecha, p.comercial, pl.usado, p.mail, p.permanencia, p.telefono1, p.telefono2
                FROM precontratos p
                LEFT JOIN precontrato_links pl ON p.id = pl.precontrato_id
                ORDER BY p.fecha DESC
                LIMIT 50
            """)
            precontratos = cursor.fetchall()
            conn.close()

            if precontratos:
                st.write(f"**Últimos {len(precontratos)} precontratos:**")
                for precontrato in precontratos:
                    with st.expander(f"📄 {precontrato[1]} - {precontrato[3] or 'Sin nombre'} - {precontrato[4]}",
                                     expanded=False):

                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.write(f"**ID:** {precontrato[1]}")
                            st.write(f"**Apartment ID:** {precontrato[2] or 'No asignado'}")
                            st.write(f"**Tarifa:** {precontrato[4]}")
                            st.write(f"**Precio:** {precontrato[5]}€")

                        with col2:
                            st.write(f"**Fecha:** {precontrato[6]}")
                            st.write(f"**Comercial:** {precontrato[7]}")
                            st.write(f"**Permanencia:** {precontrato[10] or 'No especificada'}")

                        with col3:
                            estado = "✅ Usado" if precontrato[8] else "🟢 Activo"
                            st.write(f"**Estado:** {estado}")
                            st.write(f"**Email:** {precontrato[9] or 'No especificado'}")
                            st.write(f"**Teléfono 1:** {precontrato[11] or 'No especificado'}")
                            if precontrato[12]:  # Si hay teléfono 2
                                st.write(f"**Teléfono 2:** {precontrato[12]}")

                        # ==== ELIMINA ESTA LÍNEA: if precontrato[8]: ====
                        # Botón para regenerar enlace (AHORA SIEMPRE VISIBLE)
                        if st.button(f"🔄 Generar/Regenerar enlace para {precontrato[1]}",
                                     key=f"regen_{precontrato[0]}"):
                            try:
                                conn = get_db_connection()
                                cursor = conn.cursor()

                                # Generar nuevo token único
                                token_valido = False
                                max_intentos = 5
                                intentos = 0

                                while not token_valido and intentos < max_intentos:
                                    token = secrets.token_urlsafe(16)
                                    cursor.execute("SELECT id FROM precontrato_links WHERE token = ?", (token,))
                                    if cursor.fetchone() is None:
                                        token_valido = True
                                    intentos += 1

                                if token_valido:
                                    expiracion = datetime.now() + timedelta(hours=24)

                                    # Verificar si ya existe un enlace
                                    cursor.execute("SELECT id FROM precontrato_links WHERE precontrato_id = ?",
                                                   (precontrato[0],))
                                    link_existente = cursor.fetchone()

                                    if link_existente:
                                        # Actualizar el token existente
                                        cursor.execute("""
                                                        UPDATE precontrato_links 
                                                        SET token = ?, expiracion = ?, usado = 0
                                                        WHERE precontrato_id = ?
                                                    """, (token, expiracion, precontrato[0]))
                                        mensaje = "✅ Enlace REGENERADO correctamente."
                                    else:
                                        # Crear nuevo enlace (si no existía)
                                        cursor.execute("""
                                                        INSERT INTO precontrato_links (precontrato_id, token, expiracion, usado)
                                                        VALUES (?, ?, ?, ?)
                                                    """, (precontrato[0], token, expiracion, 0))
                                        mensaje = "✅ Enlace GENERADO por primera vez."

                                    conn.commit()
                                    conn.close()
                                    base_url = "https://one7022025.onrender.com"
                                    #base_url = "http://localhost:8501"
                                    link_cliente = f"{base_url}?precontrato_id={precontrato[0]}&token={urllib.parse.quote(token)}"
                                    st.success(mensaje)
                                    st.code(link_cliente, language="text")
                                    st.info("💡 Copia este nuevo enlace y envíalo al cliente.")
                                else:
                                    st.toast("❌ No se pudo generar un token único.")

                            except Exception as e:
                                st.toast(f"❌ Error al generar enlace: {e}")

            else:
                st.toast(
                    "📝 No hay precontratos registrados aún. Crea el primero en la pestaña 'Crear Nuevo Precontrato'.")

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

    # Mostrar mensaje de éxito en Streamlit
    st.toast("✅ Los cambios para la viabilidad han sido guardados correctamente")



# Función para obtener viabilidades guardadas en la base de datos
def obtener_viabilidades():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT latitud, longitud, ticket, serviciable, apartment_id 
        FROM viabilidades
    """)
    viabilidades = cursor.fetchall()
    conn.close()
    return viabilidades


def formulario_precontrato_section(apartment_id=None):
    """Formulario de precontrato que requiere un Apartment ID válido"""

    # Validar que tenemos un apartment_id
    if not apartment_id or apartment_id in ["", "N/D"]:
        st.toast("""**❌ No se puede generar un precontrato sin un Apartment ID válido.**
        💡 **Solución:**
        - Asegúrate de que la viabilidad tenga un Apartment ID asignado
        - La viabilidad debe estar marcada como "Sí" en serviciable
        """)
        return

    with st.expander("📑 Formulario de Precontrato", expanded=True):
        st.toast(f"🏢 **Generando precontrato para Apartment ID:** `{apartment_id}`")

        @st.cache_data(ttl=300)
        def cargar_tarifas():
            conn = get_db_connection()
            df = pd.read_sql("SELECT id, nombre, descripcion, precio FROM tarifas", conn)
            conn.close()
            return df

        with st.form(key="form_precontrato"):
            st.markdown(f"Completa los datos del precontrato asociados al **Apartment ID: {apartment_id}**")

            st.info(
                "💡 **Nota:** Solo los campos de tarifa, precio y permanencia son obligatorios. El cliente completará el resto en el formulario.")

            # Cargar tarifas
            try:
                tarifas_df = cargar_tarifas()
            except Exception as e:
                st.toast(f"⚠️ No se pudieron cargar las tarifas: {e}")
                tarifas_df = pd.DataFrame()

            # Selección de tarifa - OBLIGATORIO
            if not tarifas_df.empty:
                opciones_tarifas = [
                    f"{row['nombre']} – {row['descripcion']} ({row['precio']}€)"
                    for _, row in tarifas_df.iterrows()
                ]
                tarifa_seleccionada = st.selectbox(
                    "💰 Selecciona una tarifa disponible:*",
                    options=opciones_tarifas,
                    key="tarifa_precontrato"
                )
                tarifa_nombre = tarifa_seleccionada.split(" – ")[0] if tarifa_seleccionada else None
            else:
                st.toast("⚠️ No hay tarifas registradas en la base de datos.")
                tarifa_nombre = None

            # Mostrar Apartment ID bloqueado (no editable)
            st.text_input("🏢 Apartment ID", value=str(apartment_id), disabled=True, key="apartment_id_precontrato")

            # Campos principales del precontrato - OPCIONALES para comercial
            col1, col2, col3 = st.columns(3)
            with col1:
                nombre = st.text_input("👤 Nombre / Razón social", key="nombre_precontrato")
                cif = st.text_input("🏢 CIF", key="cif_precontrato")

                def es_cif_valido(cif):
                    if not cif:  # CIF es opcional
                        return True
                    cif = cif.upper()
                    patron_cif = r'^[ABCDEFGHJNPQRSUVW]\d{7}[0-9A-J]$'
                    return re.match(patron_cif, cif) is not None

                if cif and not es_cif_valido(cif):
                    st.toast("⚠️ Introduce un CIF válido.")

                nombre_legal = st.text_input("👥 Nombre Legal (si aplica)", key="nombre_legal_precontrato")

            with col2:
                nif = st.text_input("🪪 NIF / DNI", key="nif_precontrato")

                def es_nif_valido(nif):
                    if not nif:  # NIF es opcional para comercial
                        return True
                    nif = nif.upper()
                    patron_nif = r'^\d{8}[A-Z]$'
                    patron_nie = r'^[XYZ]\d{7}[A-Z]$'
                    return re.match(patron_nif, nif) or re.match(patron_nie, nif)

                if nif and not es_nif_valido(nif):
                    st.toast("⚠️ Introduce un NIF o NIE válido.")

                telefono1 = st.text_input("📞 Teléfono 1", key="telefono1_precontrato")
                telefono2 = st.text_input("📞 Teléfono 2", key="telefono2_precontrato")

            with col3:
                mail = st.text_input("✉️ Email", key="mail_precontrato", placeholder="usuario@dominio.com")

                def es_email_valido(email):
                    if not email:  # Email es opcional para comercial
                        return True
                    patron = r'^[\w\.-]+@[\w\.-]+\.\w+$'
                    return re.match(patron, email) is not None

                if mail and not es_email_valido(mail):
                    st.toast("⚠️ Introduce un correo electrónico válido.")

                comercial = st.text_input("🧑‍💼 Comercial", value=st.session_state.get("username", ""),
                                          key="comercial_precontrato")
                fecha = st.date_input("📅 Fecha", pd.Timestamp.now(tz="Europe/Madrid"), key="fecha_precontrato")

            # Campos de dirección - OPCIONALES para comercial
            direccion = st.text_input("🏠 Dirección", key="direccion_precontrato")

            col4, col5, col6 = st.columns(3)
            with col4:
                cp = st.text_input("📮 Código Postal", key="cp_precontrato")
            with col5:
                poblacion = st.text_input("🏘️ Población", key="poblacion_precontrato")
            with col6:
                provincia = st.text_input("🌍 Provincia", key="provincia_precontrato")

            # Campos bancarios - OPCIONALES para comercial
            col7, col8 = st.columns(2)
            with col7:
                iban = st.text_input(
                    "🏦 IBAN",
                    key="iban_precontrato",
                    placeholder="ES00 0000 0000 0000 0000 0000"
                )

                # Validación IBAN (solo si se completa)
                if iban:
                    iban_sin_espacios = iban.replace(" ", "").upper()
                    if not iban_sin_espacios.startswith("ES") or len(iban_sin_espacios) != 24:
                        st.warning("El IBAN debe empezar por ES y tener 24 caracteres (sin espacios).")
            with col8:
                bic = st.text_input(
                    "🏦 BIC",
                    key="bic_precontrato",
                    placeholder="AAAAESMMXXX"
                )

                # Validación BIC (solo si se completa)
                if bic:
                    bic_sin_espacios = bic.replace(" ", "").upper()
                    if len(bic_sin_espacios) not in (8, 11):
                        st.warning("El BIC debe tener 8 u 11 caracteres.")

            # Campos adicionales del precontrato
            observaciones = st.text_area("📝 Observaciones", key="observaciones_precontrato",
                                         placeholder="Observaciones adicionales sobre el contrato...")

            # PRECIO - OBLIGATORIO (puede ser 0)
            precio = st.text_input(
                "💵 Precio Total (€ I.V.A Incluido)*",
                key="precio_precontrato",
                placeholder="Ej: 1200,50 o 0"
            )

            # Validación de precio - OBLIGATORIO pero puede ser 0
            if precio:
                try:
                    precio_limpio = precio.replace(",", ".").replace(" ", "")
                    precio_float = float(precio_limpio)
                    # Permitimos que el precio sea 0 o cualquier número
                except ValueError:
                    st.toast("⚠️ El precio debe ser un número válido.")

            # PERMANENCIA - OBLIGATORIO
            permanencia = st.radio(
                "📆 Permanencia (meses)*",
                options=[12, 24],
                key="permanencia_precontrato",
                horizontal=True
            )

            servicio_adicional = st.text_area(
                "➕ Servicio Adicional",
                key="servicio_adicional_precontrato",
                placeholder="Servicios adicionales contratados..."
            )

            # Línea fija - OPCIONAL
            st.markdown("#### 📞 Línea Fija")
            colf1, colf2, colf3 = st.columns(3)
            with colf1:
                fija_tipo = st.selectbox("Tipo", ["nuevo", "portabilidad"], key="fija_tipo_precontrato")
                fija_numero = st.text_input("Número a portar / nuevo", key="fija_numero_precontrato",
                                            placeholder="Número de línea fija")
            with colf2:
                fija_titular = st.text_input("Titular", key="fija_titular_precontrato")
                fija_dni = st.text_input("DNI Titular", key="fija_dni_precontrato")
            with colf3:
                fija_operador = st.text_input("Operador Donante", key="fija_operador_precontrato",
                                              placeholder="Operador actual")
                fija_icc = st.text_input("ICC (prepago, si aplica)", key="fija_icc_precontrato")

            # Línea móvil principal - OPCIONAL
            st.markdown("#### 📱 Línea Móvil Principal")
            colm1, colm2, colm3 = st.columns(3)
            with colm1:
                movil_tipo = st.selectbox("Tipo", ["nuevo", "portabilidad"], key="movil_tipo_precontrato")
                movil_numero = st.text_input("Número a portar / nuevo", key="movil_numero_precontrato",
                                             placeholder="Número móvil")
            with colm2:
                movil_titular = st.text_input("Titular", key="movil_titular_precontrato")
                movil_dni = st.text_input("DNI Titular", key="movil_dni_precontrato")
            with colm3:
                movil_operador = st.text_input("Operador Donante", key="movil_operador_precontrato",
                                               placeholder="Operador actual")
                movil_icc = st.text_input("ICC (prepago, si aplica)", key="movil_icc_precontrato")

            # Líneas móviles adicionales - OPCIONALES
            st.markdown("#### 📶 Líneas Móviles Adicionales")
            lineas_adicionales = []
            for i in range(1, 6):
                with st.expander(f"Línea móvil adicional #{i}", expanded=False):
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        tipo = st.selectbox("Tipo", ["nuevo", "portabilidad"], key=f"adicional_tipo_{i}_precontrato")
                        numero = st.text_input("Número a portar / nuevo", key=f"adicional_numero_{i}_precontrato")
                    with col2:
                        titular = st.text_input("Titular", key=f"adicional_titular_{i}_precontrato")
                        dni = st.text_input("DNI Titular", key=f"adicional_dni_{i}_precontrato")
                    with col3:
                        operador = st.text_input("Operador Donante", key=f"adicional_operador_{i}_precontrato")
                        icc = st.text_input("ICC (prepago, si aplica)", key=f"adicional_icc_{i}_precontrato")

                    # Solo agregar si hay algún dato completado
                    if numero or titular or dni or operador or icc:
                        lineas_adicionales.append({
                            "tipo": "movil_adicional",
                            "numero_nuevo_portabilidad": tipo,
                            "numero_a_portar": numero,
                            "titular": titular,
                            "dni": dni,
                            "operador_donante": operador,
                            "icc": icc
                        })

            submit_precontrato = st.form_submit_button("💾 Guardar precontrato")

            if submit_precontrato:
                # Validaciones antes de guardar - SOLO LOS 3 CAMPOS OBLIGATORIOS
                errores = []

                # 1. Validar tarifa - OBLIGATORIO
                if not tarifa_nombre:
                    st.toast("❌ Debes seleccionar una tarifa")

                # 2. Validar precio - OBLIGATORIO (puede ser 0)
                if not precio:
                    st.toast("❌ El campo 'Precio' es obligatorio")
                else:
                    try:
                        precio_limpio = precio.replace(",", ".").replace(" ", "")
                        precio_float = float(precio_limpio)
                        # Permitimos que el precio sea 0 o cualquier número
                    except ValueError:
                        st.toast("❌ El precio debe ser un número válido")

                # 3. Permanencia siempre tiene valor (12 o 24 por defecto), no necesita validación

                # Mostrar errores si los hay
                if errores:
                    for error in errores:
                        st.error(error)
                    return

                # Si todas las validaciones pasan, proceder con el guardado
                try:
                    conn = get_db_connection()
                    cursor = conn.cursor()

                    # 1️⃣ Insertar precontrato
                    cursor.execute("""
                        INSERT INTO precontratos (
                            apartment_id, tarifas, observaciones, precio, comercial,
                            nombre, cif, nombre_legal, nif, telefono1, telefono2, mail, direccion,
                            cp, poblacion, provincia, iban, bic, fecha, firma, permanencia,
                            servicio_adicional, precontrato_id
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        apartment_id,
                        tarifa_nombre,
                        observaciones or "",
                        precio,
                        comercial or st.session_state.get("username", ""),
                        nombre or "",
                        cif or "",
                        nombre_legal or "",
                        nif or "",
                        telefono1 or "",
                        telefono2 or "",
                        mail or "",
                        direccion or "",
                        cp or "",
                        poblacion or "",
                        provincia or "",
                        iban or "",
                        bic or "",
                        str(fecha),
                        "",  # firma (se completará en el formulario del cliente)
                        permanencia,
                        servicio_adicional or "",
                        f"PRE-{int(pd.Timestamp.now().timestamp())}"  # identificador público
                    ))

                    precontrato_pk = cursor.lastrowid

                    # 2️⃣ Insertar líneas asociadas (solo si tienen datos)
                    lineas = [
                                 {
                                     "tipo": "fija",
                                     "numero_nuevo_portabilidad": fija_tipo,
                                     "numero_a_portar": fija_numero,
                                     "titular": fija_titular,
                                     "dni": fija_dni,
                                     "operador_donante": fija_operador,
                                     "icc": fija_icc
                                 },
                                 {
                                     "tipo": "movil",
                                     "numero_nuevo_portabilidad": movil_tipo,
                                     "numero_a_portar": movil_numero,
                                     "titular": movil_titular,
                                     "dni": movil_dni,
                                     "operador_donante": movil_operador,
                                     "icc": movil_icc
                                 }
                             ] + lineas_adicionales

                    for linea in lineas:
                        # Solo insertar líneas que tengan al menos el número
                        if linea["numero_a_portar"]:
                            cursor.execute("""
                                INSERT INTO lineas (
                                    precontrato_id, tipo, numero_nuevo_portabilidad, numero_a_portar,
                                    titular, dni, operador_donante, icc
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                precontrato_pk,
                                linea["tipo"],
                                linea["numero_nuevo_portabilidad"],
                                linea["numero_a_portar"],
                                linea["titular"] or "",
                                linea["dni"] or "",
                                linea["operador_donante"] or "",
                                linea["icc"] or ""
                            ))

                    # 3️⃣ Generar token de acceso temporal
                    token_valido = False
                    max_intentos = 5
                    intentos = 0
                    while not token_valido and intentos < max_intentos:
                        token = secrets.token_urlsafe(16)
                        cursor.execute("SELECT id FROM precontrato_links WHERE token = ?", (token,))
                        if cursor.fetchone() is None:
                            token_valido = True
                        intentos += 1

                    if not token_valido:
                        st.toast("❌ No se pudo generar un token único, intenta nuevamente.")
                    else:
                        expiracion = datetime.now() + timedelta(hours=24)
                        cursor.execute("""
                            INSERT INTO precontrato_links (precontrato_id, token, expiracion, usado)
                            VALUES (?, ?, ?, 0)
                        """, (precontrato_pk, token, expiracion))

                        conn.commit()
                        conn.close()

                        base_url = "https://one7022025.onrender.com"
                        #base_url = "http://localhost:8501"
                        link_cliente = f"{base_url}?precontrato_id={precontrato_pk}&token={urllib.parse.quote(token)}"

                        st.toast("✅ Precontrato guardado correctamente.")
                        st.markdown(f"📎 **Enlace para el cliente (válido 24 h):**")
                        st.code(link_cliente, language="text")
                        st.info("💡 Copia este enlace y envíalo al cliente por WhatsApp. Solo podrá usarse una vez.")

                except Exception as e:
                    st.toast(f"❌ Error al guardar el precontrato: {e}. Detalles del error: {str(e)}")

        # ✅ MOVER EL BOTÓN DE COPIAR FUERA DEL FORMULARIO
        # Usamos session_state para mostrar el botón solo después de guardar
        if 'precontrato_guardado' not in st.session_state:
            st.session_state.precontrato_guardado = False

        # Este botón está fuera del formulario, por lo que no causa error
        if st.session_state.precontrato_guardado and 'ultimo_enlace' in st.session_state:
                st.toast("🔗 Enlace copiado al portapapeles")

def viabilidades_section():
    st.title("Viabilidades")
    st.markdown("""**Leyenda:**
                 ⚫ Viabilidad ya existente
                 🔵 Viabilidad nueva aún sin estudio
                 🟢 Viabilidad serviciable y con Apartment ID ya asociado
                 🔴 Viabilidad no serviciable
                """)
    st.info("ℹ️ Haz click en el mapa para agregar un marcador que represente el punto de viabilidad.")

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
        tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
        attr="Google"
    )

    # Agregar marcadores de viabilidades guardadas (solo las del usuario logueado)
    # Se asume que obtener_viabilidades() retorna registros con:
    # (latitud, longitud, ticket, serviciable, apartment_id)
    viabilidades = obtener_viabilidades()
    for v in viabilidades:
        lat, lon, ticket, serviciable, apartment_id = v

        # Determinar el color del marcador según las condiciones
        if serviciable is not None and str(serviciable).strip() != "":
            serv = str(serviciable).strip()
            apt = str(apartment_id).strip() if apartment_id is not None else ""
            if serv == "No":
                marker_color = "red"
            elif serv == "Sí" and apt not in ["", "N/D"]:
                marker_color = "green"
            else:
                marker_color = "black"
        else:
            marker_color = "black"

        folium.Marker(
            [lat, lon],
            icon=folium.Icon(color=marker_color),
            popup=f"Ticket: {ticket}"
        ).add_to(m)

    # Si hay un marcador nuevo, agregarlo al mapa en azul
    if st.session_state.viabilidad_marker:
        lat = st.session_state.viabilidad_marker["lat"]
        lon = st.session_state.viabilidad_marker["lon"]
        folium.Marker(
            [lat, lon],
            icon=folium.Icon(color="blue")
        ).add_to(m)

    # Mostrar el mapa y capturar clics
    Geocoder().add_to(m)
    map_data = st_folium(m, height=680, width="100%")

    # Detectar el clic para agregar el marcador nuevo
    if map_data and "last_clicked" in map_data and map_data["last_clicked"]:
        click = map_data["last_clicked"]
        st.session_state.viabilidad_marker = {"lat": click["lat"], "lon": click["lng"]}
        st.session_state.map_center = (click["lat"], click["lng"])  # Guardar la nueva vista
        st.session_state.map_zoom = map_data["zoom"]  # Actualizar el zoom también
        st.rerun()  # Actualizamos cuando se coloca un marcador

    # Botón para eliminar el marcador y crear uno nuevo
    if st.session_state.viabilidad_marker:
        if st.button("Eliminar marcador y crear uno nuevo"):
            st.session_state.viabilidad_marker = None
            st.session_state.map_center = (43.463444, -3.790476)  # Vuelve a la ubicación inicial
            st.rerun()

    # Mostrar el formulario si hay un marcador nuevo
    if st.session_state.viabilidad_marker:
        lat = st.session_state.viabilidad_marker["lat"]
        lon = st.session_state.viabilidad_marker["lon"]

        st.subheader("Completa los datos del punto de viabilidad")
        with st.form("viabilidad_form"):
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
            # ✅ NUEVOS CAMPOS
            col12, col13 = st.columns(2)
            # Conexión para cargar los OLT desde la tabla
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id_olt, nombre_olt FROM olt ORDER BY nombre_olt")
            lista_olt = [f"{fila[0]}. {fila[1]}" for fila in cursor.fetchall()]
            conn.close()

            with col12:
                olt = st.selectbox("🏢 OLT", options=lista_olt)
            with col13:
                apartment_id = st.text_input("🏘️ Apartment ID")
            comentario = st.text_area("📝 Comentario")
            # ------------------- SUBIDA DE IMÁGENES -------------------
            imagenes_viabilidad = st.file_uploader(
                "Adjunta fotos (PNG, JPG, JPEG). Puedes seleccionar varias.",
                type=["png", "jpg", "jpeg"],
                accept_multiple_files=True,
                key=f"imagenes_viabilidad_{lat}_{lon}"
            )
            submit = st.form_submit_button("Enviar Formulario")

            if submit:
                # Generar ticket único
                ticket = generar_ticket()

                # Insertar en la base de datos.
                # Se añade el usuario logueado (st.session_state["username"]) al final de la tupla.
                guardar_viabilidad((
                    lat,
                    lon,
                    provincia,
                    municipio,
                    poblacion,
                    vial,
                    numero,
                    letra,
                    cp,
                    comentario,
                    ticket,
                    nombre_cliente,
                    telefono,
                    st.session_state["username"],
                    olt,  # nuevo campo
                    apartment_id  # nuevo campo
                ))

                # ------------------- GUARDAR IMÁGENES -------------------
                if imagenes_viabilidad:
                    st.toast("📤 Subiendo imágenes...")
                    for imagen in imagenes_viabilidad:
                        try:
                            archivo_bytes = imagen.getvalue()
                            nombre_archivo = imagen.name

                            # Aquí puedes subir a Cloudinary o a tu sistema de almacenamiento
                            url = upload_image_to_cloudinary(archivo_bytes,
                                                             nombre_archivo)  # Necesitas implementar esta función

                            # Guardar URL y ticket en base de datos
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

                st.toast(f"✅ Viabilidad guardada correctamente.\n\n📌 **Ticket:** `{ticket}`")

                # Resetear marcador para permitir nuevas viabilidades
                st.session_state.viabilidad_marker = None
                st.session_state.map_center = (43.463444, -3.790476)  # Vuelve a la ubicación inicial
                st.rerun()

    # ✅ NUEVA SECCIÓN: Mostrar formulario de precontrato SOLO para viabilidades con Apartment ID
    st.markdown("---")
    st.subheader("📑 Generar Precontrato para Viabilidad con Apartment ID")

    # Obtener viabilidades que tienen Apartment ID (no vacío y no "N/D")
    conn = get_db_connection()
    cursor = conn.cursor()
    # En la sección donde obtienes las viabilidades para precontrato:
    cursor.execute("""
        SELECT ticket, apartment_id, provincia, municipio, poblacion, vial, numero, letra, nombre_cliente
        FROM viabilidades 
        WHERE apartment_id IS NOT NULL
    """)
    viabilidades_con_apartment = cursor.fetchall()
    conn.close()

    if viabilidades_con_apartment:
        # Crear opciones para el selectbox
        opciones_viabilidades = []
        for v in viabilidades_con_apartment:
            ticket = v[0]
            apartment_ids = v[1]
            provincia = v[2]
            municipio = v[3]
            nombre_cliente = v[8] or "Sin nombre"

            # Verificar si hay múltiples apartment_ids separados por comas
            if ',' in apartment_ids:
                # Contar cuántos apartment_ids hay
                num_apartments = len(apartment_ids.split(','))
                opciones_viabilidades.append(
                    f"{ticket} - {apartment_ids} ({provincia}, {municipio}) - Cliente: {nombre_cliente} [{num_apartments} APTs]"
                )
            else:
                opciones_viabilidades.append(
                    f"{ticket} - {apartment_ids} ({provincia}, {municipio}) - Cliente: {nombre_cliente}"
                )

        viabilidad_seleccionada = st.selectbox(
            "Selecciona una viabilidad con Apartment ID para generar precontrato:",
            options=opciones_viabilidades,
            key="select_viabilidad_precontrato"
        )

        if viabilidad_seleccionada:
            # Extraer el ticket de la selección
            ticket_seleccionado = viabilidad_seleccionada.split(" - ")[0]

            # Encontrar los datos completos de la viabilidad seleccionada
            viabilidad_data = [
                v for v in viabilidades_con_apartment
                if v[0] == ticket_seleccionado
            ][0]

            ticket = viabilidad_data[0]
            apartment_ids_completo = viabilidad_data[1]  # Puede contener múltiples IDs separados por comas
            provincia = viabilidad_data[2]
            municipio = viabilidad_data[3]
            poblacion = viabilidad_data[4]
            vial = viabilidad_data[5]
            numero = viabilidad_data[6]
            letra = viabilidad_data[7]
            nombre_cliente = viabilidad_data[8]

            # Formatear la dirección
            direccion_completa = f"{vial} {numero}{f' {letra}' if letra else ''}, {poblacion}"

            # Verificar si hay múltiples apartment_ids
            if ',' in apartment_ids_completo:
                # Separar los apartment_ids y limpiar espacios
                apartment_ids_lista = [apt.strip() for apt in apartment_ids_completo.split(',')]

                st.info(f"""
                **Viabilidad seleccionada:**
                - **Ticket:** {ticket}
                - **Apartment IDs disponibles:** {apartment_ids_completo}
                - **Cliente:** {nombre_cliente if nombre_cliente else 'No especificado'}
                - **Dirección:** {direccion_completa}
                - **Municipio:** {municipio}
                - **Provincia:** {provincia}
                """)

                # Mostrar selector para elegir un apartment_id específico
                apartment_id_seleccionado = st.selectbox(
                    "Selecciona el Apartment ID específico para el precontrato:",
                    options=apartment_ids_lista,
                    key=f"select_apartment_{ticket}"
                )

                st.toast(f"🏢 **Generando precontrato para:** `{apartment_id_seleccionado}`")

            else:
                # Solo hay un apartment_id
                apartment_id_seleccionado = apartment_ids_completo

                # Mostrar información de la viabilidad seleccionada
                st.info(f"""
                **Viabilidad seleccionada:**
                - **Ticket:** {ticket}
                - **Apartment ID:** {apartment_id_seleccionado}
                - **Cliente:** {nombre_cliente if nombre_cliente else 'No especificado'}
                - **Dirección:** {direccion_completa}
                - **Municipio:** {municipio}
                - **Provincia:** {provincia}
                """)

            # Llamar al formulario de precontrato con el apartment_id seleccionado
            formulario_precontrato_section(apartment_id_seleccionado)
    else:
        st.toast("""
        ℹ️ **No hay viabilidades disponibles para generar precontratos**

        Para generar un precontrato necesitas:
        1. Una viabilidad marcada como **"Sí"** en serviciable
        2. Un **Apartment ID** asignado (no vacío y no "N/D")

        Crea una viabilidad primero y asegúrate de completar estos campos.
        """)


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

    # Crear formulario para agrupar todos los campos
    with st.form(key=f"oferta_form_{form_key}"):
        # Mostrar datos no editables
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
                        "📑 Tipo de Contrato",
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
                "📌 Dirección Alternativa (Rellenar si difiere de la original)",
                key=f"alt_address_{form_key}",
                placeholder="Dejar vacío si coincide con la dirección principal"
            )

            observations = st.text_area(
                "📝 Observaciones",
                key=f"observations_{form_key}",
                placeholder="Cualquier observación adicional relevante..."
            )

        # ACORDEÓN para Gestión de Incidencias (solo relevante si es serviciable)
        with st.expander("⚠️ Gestión de Incidencias", expanded=False):
            if es_serviciable == "Sí":
                contiene_incidencias = st.radio(
                    "⚠️ ¿Contiene incidencias?",
                    ["Sí", "No"],
                    index=1,
                    horizontal=True,
                    key=f"contiene_incidencias_{form_key}"
                )

                # Estos campos están siempre habilitados
                motivo_incidencia = st.text_area(
                    "📄 Motivo de la Incidencia",
                    key=f"motivo_incidencia_{form_key}",
                    placeholder="Describir la incidencia encontrada..."
                )

                imagen_incidencia = st.file_uploader(
                    "📷 Adjuntar Imagen (PNG, JPG, JPEG)",
                    type=["png", "jpg", "jpeg"],
                    key=f"imagen_incidencia_{form_key}",
                    help="Opcional: adjuntar imagen relacionada con la incidencia"
                )
            else:
                st.info("ℹ️ Esta sección solo es relevante para ofertas serviciables")
                contiene_incidencias = ""
                motivo_incidencia = ""
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
            "Nombre Cliente": client_name if es_serviciable == "Sí" else "",
            "Teléfono": phone if es_serviciable == "Sí" else "",
            "Dirección Alternativa": alt_address,
            "Observaciones": observations,
            "serviciable": es_serviciable,
            "motivo_serviciable": motivo_serviciable if es_serviciable == "No" else "",
            "incidencia": contiene_incidencias if es_serviciable == "Sí" else "",
            "motivo_incidencia": motivo_incidencia if (es_serviciable == "Sí" and contiene_incidencias == "Sí") else "",
            "Tipo_Vivienda": tipo_vivienda_final if es_serviciable == "Sí" else "",
            "Contrato": contrato if es_serviciable == "Sí" else "",
            "fecha": pd.Timestamp.now(tz="Europe/Madrid")
        }

        st.toast("✅ Oferta enviada correctamente.")

        with st.spinner("⏳ Guardando la oferta en la base de datos..."):
            guardar_en_base_de_datos_vip(oferta_data, imagen_incidencia, apartment_id)

            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT email FROM usuarios WHERE role IN ('admin')")
            emails_admin = [fila[0] for fila in cursor.fetchall()]

            # Obtener email del comercial desde sesión o base de datos
            nombre_comercial = st.session_state.get("username", "N/D")
            email_comercial = st.session_state.get("email", None)

            conn.close()

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
            else:
                descripcion_oferta += f"❌ <strong>Motivo No Servicio:</strong> {motivo_serviciable}<br>"

            if alt_address:
                descripcion_oferta += f"📍 <strong>Dirección Alternativa:</strong> {alt_address}<br>"
            if observations:
                descripcion_oferta += f"💬 <strong>Observaciones:</strong> {observations}<br>"

            descripcion_oferta += "<br>ℹ️ Por favor, revise los detalles de la oferta y asegúrese de que toda la información sea correcta."

            if emails_admin:
                for email in emails_admin:
                    correo_oferta_comercial(email, apartment_id, descripcion_oferta)

                # Enviar copia al comercial
                if email_comercial:
                    correo_oferta_comercial(email_comercial, apartment_id, descripcion_oferta)

                st.toast("✅ Oferta enviada con éxito")
                st.toast(
                    f"📧 Se ha enviado una notificación a: {', '.join(emails_admin + ([email_comercial] if email_comercial else []))}")
            else:
                st.warning("⚠️ No se encontró ningún email de administrador/gestor, no se pudo enviar la notificación.")

    # ---------------------- FORMULARIO DE PRECONTRATO ----------------------
    with st.expander("📑 Formulario de Precontrato", expanded=False):

        # --- Función cacheada para cargar tarifas ---
        @st.cache_data(ttl=300)
        def cargar_tarifas():
            conn = get_db_connection()
            df = pd.read_sql("SELECT id, nombre, descripcion, precio FROM tarifas", conn)
            conn.close()
            return df

        # --- Formulario de precontrato ---
        with st.form(key="form_precontrato"):
            st.markdown(
                f"Completa los datos del precontrato asociados al **Apartment ID: {apartment_id}** seleccionado."
            )

            # Cargar tarifas disponibles desde la BD (solo una vez gracias al cache)
            try:
                tarifas_df = cargar_tarifas()
            except Exception as e:
                st.warning(f"⚠️ No se pudieron cargar las tarifas: {e}")
                tarifas_df = pd.DataFrame()

            # Selección de tarifa
            if not tarifas_df.empty:
                opciones_tarifas = [
                    f"{row['nombre']} – {row['descripcion']} ({row['precio']}€)"
                    for _, row in tarifas_df.iterrows()
                ]
                tarifa_seleccionada = st.selectbox(
                    "💰 Selecciona una tarifa disponible:*",
                    options=opciones_tarifas,
                    key=f"tarifa_{form_key}"
                )

                # Validación obligatoria
                if not tarifa_seleccionada:
                    st.warning("⚠️ Debes seleccionar una tarifa.")
                tarifa_nombre = tarifa_seleccionada.split(" – ")[0]
            else:
                st.warning(
                    "⚠️ No hay tarifas registradas en la base de datos. Añade alguna antes de crear un precontrato."
                )
                tarifa_nombre = None

            # Mostrar Apartment ID bloqueado
            st.text_input("🏢 Apartment ID", value=str(apartment_id), disabled=True, key=f"apartment_id_{form_key}")

            # Campos principales del precontrato
            col1, col2, col3 = st.columns(3)
            with col1:
                nombre = st.text_input("👤 Nombre / Razón social", key=f"nombre_{form_key}")
                cif = st.text_input("🏢 CIF", key=f"cif_{form_key}")

                def es_cif_valido(cif):
                    """
                    Valida CIF español: letra inicial + 7 dígitos + dígito/control final (letra o número)
                    """
                    cif = cif.upper()
                    patron_cif = r'^[ABCDEFGHJNPQRSUVW]\d{7}[0-9A-J]$'
                    return re.match(patron_cif, cif) is not None

                if cif and not es_cif_valido(cif):
                    st.warning("⚠️ Introduce un CIF válido.")
                nombre_legal = st.text_input("👥 Nombre Legal (si aplica)", key=f"nombre_legal_{form_key}")
            with col2:
                nif = st.text_input("🪪 NIF / DNI", key=f"nif_{form_key}")

                def es_nif_valido(nif):
                    nif = nif.upper()
                    patron_nif = r'^\d{8}[A-Z]$'
                    patron_nie = r'^[XYZ]\d{7}[A-Z]$'
                    return re.match(patron_nif, nif) or re.match(patron_nie, nif)

                if nif and not es_nif_valido(nif):
                    st.warning("⚠️ Introduce un NIF o NIE válido.")
                telefono1 = st.text_input("📞 Teléfono 1", key=f"telefono1_{form_key}")
                telefono2 = st.text_input("📞 Teléfono 2", key=f"telefono2_{form_key}")
            with col3:
                mail = st.text_input("✉️ Email", key=f"mail_{form_key}", placeholder="usuario@dominio.com")

                # Validación básica de email
                def es_email_valido(email):
                    patron = r'^[\w\.-]+@[\w\.-]+\.\w+$'
                    return re.match(patron, email)

                if mail and not es_email_valido(mail):
                    st.warning("⚠️ Introduce un correo electrónico válido.")
                comercial = st.text_input("🧑‍💼 Comercial", value=st.session_state.get("username", ""),
                                          key=f"comercial_{form_key}")
                fecha = st.date_input("📅 Fecha", pd.Timestamp.now(tz="Europe/Madrid"), key=f"fecha_{form_key}")

            direccion = st.text_input("🏠 Dirección", key=f"direccion_{form_key}")
            col4, col5, col6 = st.columns(3)
            with col4:
                cp = st.text_input("📮 Código Postal", key=f"cp_{form_key}")
            with col5:
                poblacion = st.text_input("🏘️ Población", key=f"poblacion_{form_key}")
            with col6:
                provincia = st.text_input("🌍 Provincia", key=f"provincia_{form_key}")

            col7, col8 = st.columns(2)
            with col7:
                iban = st.text_input(
                    "🏦 IBAN",
                    key=f"iban_{form_key}",
                    placeholder="ES00 0000 0000 0000 0000 0000"  # Ejemplo de formato
                )

                # Validación simple: longitud y prefijo
                if iban:
                    iban_sin_espacios = iban.replace(" ", "")
                    if not iban_sin_espacios.startswith("ES") or len(iban_sin_espacios) != 24:
                        st.warning("El IBAN debe empezar por ES y tener 24 caracteres (sin espacios).")
            with col8:
                bic = st.text_input(
                    "🏦 BIC",
                    key=f"bic_{form_key}",
                    placeholder="AAAAESMMXXX"  # Ejemplo de formato
                )

                # Validación simple: longitud y caracteres válidos
                if bic:
                    bic_sin_espacios = bic.replace(" ", "").upper()
                    if len(bic_sin_espacios) not in (8, 11):
                        st.warning("El BIC debe tener 8 u 11 caracteres.")

            observaciones = st.text_area("📝 Observaciones", key=f"observaciones_precontrato_{form_key}")
            precio = st.text_input(
                "💵 Precio Total (€ I.V.A Incluido)*",
                key=f"precio_{form_key}",
                placeholder="Ej: 1200,50"
            )

            # Validación obligatoria y formato
            if not precio:
                st.warning("⚠️ Debes introducir el precio.")
            else:
                # Reemplazar coma por punto para convertir a float si necesitas hacer cálculos
                precio_formateado = precio.replace(",", ".")
                try:
                    precio_float = float(precio_formateado)
                except ValueError:
                    st.warning("⚠️ El precio debe ser un número válido, con coma si tiene decimales (Ej: 1200,50).")

            # Validación y formateo
            if precio:
                try:
                    precio_limpio = precio.replace(",", ".").replace(" ", "")
                    precio_float = float(precio_limpio)
                    # Quitamos la validación de que sea mayor que 0, permitimos cualquier número
                except ValueError:
                    st.toast("❌ El precio debe ser un número válido")

            permanencia = st.radio(
                "📆 Permanencia (meses)",
                options=[12, 24],
                key=f"permanencia_{form_key}"
            )
            servicio_adicional = st.text_area("➕ Servicio Adicional", key=f"servicio_adicional_{form_key}")

            # Línea fija
            st.markdown("#### 📞 Línea Fija")
            colf1, colf2, colf3 = st.columns(3)
            with colf1:
                fija_tipo = st.selectbox("Tipo", ["nuevo", "portabilidad"], key=f"fija_tipo_{form_key}")
                fija_numero = st.text_input("Número a portar / nuevo", key=f"fija_numero_{form_key}")
            with colf2:
                fija_titular = st.text_input("Titular", key=f"fija_titular_{form_key}")
                fija_dni = st.text_input("DNI Titular", key=f"fija_dni_{form_key}")
            with colf3:
                fija_operador = st.text_input("Operador Donante", key=f"fija_operador_{form_key}")
                fija_icc = st.text_input("ICC (prepago, si aplica)", key=f"fija_icc_{form_key}")

            # Línea móvil principal
            st.markdown("#### 📱 Línea Móvil Principal")
            colm1, colm2, colm3 = st.columns(3)
            with colm1:
                movil_tipo = st.selectbox("Tipo", ["nuevo", "portabilidad"], key=f"movil_tipo_{form_key}")
                movil_numero = st.text_input("Número a portar / nuevo", key=f"movil_numero_{form_key}")
            with colm2:
                movil_titular = st.text_input("Titular", key=f"movil_titular_{form_key}")
                movil_dni = st.text_input("DNI Titular", key=f"movil_dni_{form_key}")
            with colm3:
                movil_operador = st.text_input("Operador Donante", key=f"movil_operador_{form_key}")
                movil_icc = st.text_input("ICC (prepago, si aplica)", key=f"movil_icc_{form_key}")

            # Líneas móviles adicionales
            st.markdown("#### 📶 Líneas Móviles Adicionales")
            lineas_adicionales = []
            for i in range(1, 6):
                with st.expander(f"Línea móvil adicional #{i}", expanded=False):
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        tipo = st.selectbox("Tipo", ["nuevo", "portabilidad"], key=f"adicional_tipo_{i}_{form_key}")
                        numero = st.text_input("Número a portar / nuevo", key=f"adicional_numero_{i}_{form_key}")
                    with col2:
                        titular = st.text_input("Titular", key=f"adicional_titular_{i}_{form_key}")
                        dni = st.text_input("DNI Titular", key=f"adicional_dni_{i}_{form_key}")
                    with col3:
                        operador = st.text_input("Operador Donante", key=f"adicional_operador_{i}_{form_key}")
                        icc = st.text_input("ICC (prepago, si aplica)", key=f"adicional_icc_{i}_{form_key}")
                    if numero:
                        lineas_adicionales.append({
                            "tipo": "movil_adicional",
                            "numero_nuevo_portabilidad": tipo,
                            "numero_a_portar": numero,
                            "titular": titular,
                            "dni": dni,
                            "operador_donante": operador,
                            "icc": icc
                        })

            submit_precontrato = st.form_submit_button("💾 Guardar precontrato")

            if submit_precontrato:
                try:
                    conn = get_db_connection()
                    cursor = conn.cursor()

                    # 1️⃣ Insertar precontrato
                    cursor.execute("""
                        INSERT INTO precontratos (
                            apartment_id, tarifas, observaciones, precio, comercial,
                            nombre, cif, nombre_legal, nif, telefono1, telefono2, mail, direccion,
                            cp, poblacion, provincia, iban, bic, fecha, firma, permanencia,
                            servicio_adicional, precontrato_id
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        apartment_id,
                        tarifa_nombre,
                        observaciones,
                        precio,
                        comercial,
                        nombre,
                        cif,
                        nombre_legal,
                        nif,
                        telefono1,
                        telefono2,
                        mail,
                        direccion,
                        cp,
                        poblacion,
                        provincia,
                        iban,
                        bic,
                        str(fecha),
                        "",  # firma
                        permanencia,
                        servicio_adicional,
                        f"PRE-{int(pd.Timestamp.now().timestamp())}"  # identificador público
                    ))

                    precontrato_pk = cursor.lastrowid

                    # 2️⃣ Insertar líneas asociadas
                    lineas = [
                                 {"tipo": "fija", "numero_nuevo_portabilidad": fija_tipo,
                                  "numero_a_portar": fija_numero,
                                  "titular": fija_titular, "dni": fija_dni, "operador_donante": fija_operador,
                                  "icc": fija_icc},
                                 {"tipo": "movil", "numero_nuevo_portabilidad": movil_tipo,
                                  "numero_a_portar": movil_numero,
                                  "titular": movil_titular, "dni": movil_dni, "operador_donante": movil_operador,
                                  "icc": movil_icc}
                             ] + lineas_adicionales

                    for linea in lineas:
                        if linea["numero_a_portar"]:
                            cursor.execute("""
                                INSERT INTO lineas (
                                    precontrato_id, tipo, numero_nuevo_portabilidad, numero_a_portar,
                                    titular, dni, operador_donante, icc
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                precontrato_pk,
                                linea["tipo"],
                                linea["numero_nuevo_portabilidad"],
                                linea["numero_a_portar"],
                                linea["titular"],
                                linea["dni"],
                                linea["operador_donante"],
                                linea["icc"]
                            ))

                    # 3️⃣ Generar token de acceso temporal
                    token_valido = False
                    max_intentos = 5
                    intentos = 0
                    while not token_valido and intentos < max_intentos:
                        token = secrets.token_urlsafe(16)
                        cursor.execute("SELECT id FROM precontrato_links WHERE token = ?", (token,))
                        if cursor.fetchone() is None:
                            token_valido = True
                        intentos += 1

                    if not token_valido:
                        st.error("❌ No se pudo generar un token único, intenta nuevamente.")
                    else:
                        expiracion = datetime.now() + timedelta(hours=24)
                        cursor.execute("""
                            INSERT INTO precontrato_links (precontrato_id, token, expiracion, usado)
                            VALUES (?, ?, ?, 0)
                        """, (precontrato_pk, token, expiracion))

                        conn.commit()
                        conn.close()

                        base_url = "https://one7022025.onrender.com"  # puerto de Streamlit
                        #base_url = "http://localhost:8501"
                        link_cliente = f"{base_url}?precontrato_id={precontrato_pk}&token={urllib.parse.quote(token)}"

                        st.toast("✅ Precontrato guardado correctamente.")
                        st.markdown(f"📎 **Enlace para el cliente (válido 24 h):**\n\n[{link_cliente}]({link_cliente})")
                        st.info("Copia este enlace y envíalo al cliente por WhatsApp. Solo podrá usarse una vez.")

                except Exception as e:
                    st.error(f"❌ Error al guardar el precontrato: {e}")


if __name__ == "__main__":
    comercial_dashboard_vip()