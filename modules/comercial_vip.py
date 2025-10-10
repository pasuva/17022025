import streamlit as st
from branca.element import Template, MacroElement
from folium.plugins import MarkerCluster
import pandas as pd
import os, re, time, folium, sqlitecloud
from streamlit_folium import st_folium
import streamlit.components.v1 as components
from datetime import datetime
from modules import login
from folium.plugins import Geocoder
from modules.cloudinary import upload_image_to_cloudinary
from modules.notificaciones import correo_oferta_comercial, correo_viabilidad_comercial, correo_respuesta_comercial
from streamlit_option_menu import option_menu
from streamlit_cookies_controller import CookieController  # Se importa localmente

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
                st.error(f"❌ El Apartment ID {apartment_id} ya está asignado al comercial '{comercial_asignado}'. "
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
            st.success(f"✅ ¡Oferta actualizada en comercial_rafa para {apartment_id}!")

        else:
            # --- INSERT ---
            cursor.execute("""
                SELECT provincia, municipio, poblacion, vial, numero, letra, cp, latitud, longitud
                FROM datos_uis WHERE apartment_id = ?
            """, (apartment_id,))
            row = cursor.fetchone()
            if not row:
                st.error(f"❌ El apartment_id {apartment_id} no existe en datos_uis.")
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
            st.success(f"✅ ¡Oferta insertada en comercial_rafa para {apartment_id}!")

        conn.commit()
        conn.close()

        # Registrar trazabilidad
        log_trazabilidad(comercial_logueado, "Guardar/Actualizar Oferta",
                         f"Oferta guardada para Apartment ID: {apartment_id}")

    except Exception as e:
        st.error(f"❌ Error al guardar/actualizar la oferta: {e}")



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
            options=["Ofertas Comerciales", "Viabilidades", "Visualización de Datos"],
            icons=["bar-chart", "check-circle", "graph-up"],
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
            st.success("✅ Has cerrado sesión correctamente. Redirigiendo al login...")
            st.rerun()

    marker_icon_type = 'info-sign'

    # --- DASHBOARD ---
    if menu_opcion == "Ofertas Comerciales":
        log_trazabilidad(comercial, "Visualización de Dashboard VIP",
                         "El comercial VIP visualizó la sección de Ofertas Comerciales.")

        # ----- FILTROS -----
        with st.spinner("⏳ Cargando filtros..."):
            try:
                conn = get_db_connection()
                provincias = pd.read_sql("SELECT DISTINCT provincia FROM datos_uis ORDER BY provincia", conn)[
                    "provincia"].dropna().tolist()
                conn.close()
            except Exception as e:
                st.error(f"❌ Error al cargar filtros: {e}")
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

        # Botones: aplicar y limpiar
        colA, colB = st.columns([1, 1])
        with colA:
            aplicar = st.button("🔍 Aplicar filtros", key="vip_apply")
        with colB:
            limpiar = st.button("🧹 Limpiar filtros", key="vip_clear")

        if limpiar:
            st.session_state.pop("vip_filtered_df", None)
            st.session_state.pop("vip_filters", None)
            st.success("🧹 Filtros limpiados.")
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
                            "sin_comercial": sin_comercial
                        }
                        st.success(f"✅ Se han cargado {len(df)} puntos. (Filtros guardados en sesión)")

                except Exception as e:
                    st.error(f"❌ Error al cargar los datos filtrados: {e}")

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
                    st.error(f"❌ Error al cargar los datos en el mapa: {e}")

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
            st.error("❌ No has iniciado sesión. Por favor, vuelve a la pantalla de inicio de sesión.")
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
                   v.serviciable, v.coste, v.comentarios_comercial, v.justificacion, v.resultado, v.respuesta_comercial
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
                st.dataframe(df_ofertas, use_container_width=True)

            # Verificar si hay datos para mostrar en la segunda tabla (viabilidades)
            # Mostrar segunda tabla (viabilidades)
            if df_viabilidades.empty:
                st.warning(f"⚠️ No hay viabilidades disponibles para el comercial '{comercial_usuario}'.")
            else:
                st.subheader("📋 Tabla de Viabilidades")
                st.dataframe(df_viabilidades, use_container_width=True)

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
                                    **📌 Justificación oficina:**  
                                    {row.get('justificacion', '—')}

                                    **📊 Resultado oficina:**  
                                    {row.get('resultado', '—')}
                                    """)

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

                                    st.success(
                                        f"✅ Comentario guardado y notificación enviada para el ticket {row['ticket']}.")
                                    st.rerun()  # 🔄 Refrescar la página para que desaparezca de pendientes
                                except Exception as e:
                                    st.error(f"❌ Error al guardar el comentario para el ticket {row['ticket']}: {e}")
                else:
                    st.info("🎉 No tienes viabilidades pendientes de contestar. ✅")

        except Exception as e:
            st.error(f"❌ Error al cargar los datos: {e}")

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
    #email_comercial_jefe = resultado_jefe[0] if resultado_jefe else None

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
        st.info(
            f"📧 Se ha enviado una notificación a los administradores: {', '.join(emails_admin)} sobre la viabilidad completada."
        )
    else:
        st.warning("⚠️ No se encontró ningún email de administrador, no se pudo enviar la notificación.")

    # Notificar al comercial jefe específico
    #if email_comercial_jefe:
    #    correo_viabilidad_comercial(email_comercial_jefe, ticket_id, descripcion_viabilidad)
    #    st.info(f"📧 Notificación enviada al comercial jefe: {email_comercial_jefe}")
    #else:
    #    st.warning("⚠️ No se encontró email del comercial jefe, no se pudo enviar la notificación.")

    # Mostrar mensaje de éxito en Streamlit
    st.success("✅ Los cambios para la viabilidad han sido guardados correctamente")



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

                st.success(f"✅ Viabilidad guardada correctamente.\n\n📌 **Ticket:** `{ticket}`")

                # Resetear marcador para permitir nuevas viabilidades
                st.session_state.viabilidad_marker = None
                st.session_state.map_center = (43.463444, -3.790476)  # Vuelve a la ubicación inicial
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
        st.error("❌ Coordenadas inválidas.")
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
        st.error(f"❌ Error al obtener datos de la base de datos: {e}")
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
        # Extraemos solo el apartment_id de la opción seleccionada
        apartment_id = seleccion.split()[0]
        # Filtramos el DataFrame por ese apartment_id
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

    # Selector reactivo para "¿Es serviciable?" (por defecto lo deja en "Sí")
    es_serviciable = st.radio(
        "🛠️ ¿Es serviciable?",
        ["Sí", "No"],
        index=0,
        horizontal=True,
        key=f"es_serviciable_{form_key}"
    )

    # Variables comunes
    tipo_vivienda = tipo_vivienda_otro = contrato = client_name = phone = alt_address = observations = ""
    contiene_incidencias = motivo_incidencia = motivo_serviciable = ""
    imagen_incidencia = None

    # Campos si es serviciable
    if es_serviciable == "Sí":
        col1, col2 = st.columns(2)
        with col1:
            tipo_vivienda = st.selectbox(
                "🏠 Tipo de Ui",
                ["Piso", "Casa", "Dúplex", "Negocio", "Ático", "Otro"],
                index=0,
                key=f"tipo_vivienda_{form_key}"
            )
            contrato = st.radio(
                "📑 Tipo de Contrato",
                ["Sí", "No Interesado"],
                index=0,
                horizontal=True,
                key=f"contrato_{form_key}"
            )
            client_name = st.text_input(
                "👤 Nombre del Cliente",
                max_chars=100,
                key=f"client_name_{form_key}"
            )
            phone = st.text_input(
                "📞 Teléfono",
                max_chars=15,
                key=f"phone_{form_key}"
            )
        with col2:
            tipo_vivienda_otro = (
                st.text_input("📝 Especificar Tipo de Ui", key=f"tipo_vivienda_otro_{form_key}")
                if tipo_vivienda == "Otro" else ""
            )
            alt_address = st.text_input(
                "📌 Dirección Alternativa (Rellenar si difiere de la original)",
                key=f"alt_address_{form_key}"
            )
            observations = st.text_area(
                "📝 Observaciones",
                key=f"observations_{form_key}"
            )
        contiene_incidencias = st.radio(
            "⚠️ ¿Contiene incidencias?",
            ["Sí", "No"],
            index=1,
            horizontal=True,
            key=f"contiene_incidencias_{form_key}"
        )
        if contiene_incidencias == "Sí":
            motivo_incidencia = st.text_area(
                "📄 Motivo de la Incidencia",
                key=f"motivo_incidencia_{form_key}"
            )
            imagen_incidencia = st.file_uploader(
                "📷 Adjuntar Imagen (PNG, JPG, JPEG)",
                type=["png", "jpg", "jpeg"],
                key=f"imagen_incidencia_{form_key}"
            )
    else:
        motivo_serviciable = st.text_area(
            "❌ Motivo de No Servicio",
            key=f"motivo_serviciable_{form_key}"
        )

    # Botón de envío
    submit = st.button("🚀 Enviar Oferta", key=f"submit_oferta_{form_key}")

    # Procesar envío
    if submit:
        if es_serviciable == "Sí" and phone and not phone.isdigit():
            st.error("❌ El teléfono debe contener solo números.")
            return

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
            "Nombre Cliente": client_name,
            "Teléfono": phone,
            "Dirección Alternativa": alt_address,
            "Observaciones": observations,
            "serviciable": es_serviciable,
            "motivo_serviciable": motivo_serviciable,
            "incidencia": contiene_incidencias if es_serviciable == "Sí" else "",
            "motivo_incidencia": motivo_incidencia if es_serviciable == "Sí" else "",
            "Tipo_Vivienda": tipo_vivienda_otro if tipo_vivienda == "Otro" else tipo_vivienda,
            "Contrato": contrato,
            "fecha": pd.Timestamp.now(tz="Europe/Madrid")
        }

        st.success("✅ Oferta enviada correctamente.")

        with st.spinner("⏳ Guardando la oferta en la base de datos..."):
            guardar_en_base_de_datos_vip(oferta_data, imagen_incidencia, apartment_id)

            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT email FROM usuarios WHERE role IN ('admin')")
            emails_admin = [fila[0] for fila in cursor.fetchall()]

            # Obtener email del comercial desde sesión o base de datos
            nombre_comercial = st.session_state.get("username", "N/D")
            email_comercial = st.session_state.get("email", None)  # <- Asegúrate que esto esté definido al hacer login

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
                f"📱 <strong>Teléfono:</strong> {phone}<br>"
                f"🏘️ <strong>Tipo Vivienda:</strong> {oferta_data['Tipo_Vivienda']}<br>"
                f"✅ <strong>Contratado:</strong> {contrato}<br>"
                f"🔧 <strong>Servicio:</strong> {es_serviciable}<br>"
                f"⚠️ <strong>Incidencia:</strong> {contiene_incidencias}<br>"
                f"💬 <strong>Observaciones:</strong> {observations}<br><br>"
                f"ℹ️ Por favor, revise los detalles de la oferta y asegúrese de que toda la información sea correcta."
            )

            if emails_admin:
                for email in emails_admin:
                    correo_oferta_comercial(email, apartment_id, descripcion_oferta)

                # Enviar copia al comercial
                if email_comercial:
                    correo_oferta_comercial(email_comercial, apartment_id, descripcion_oferta)

                st.success("✅ Oferta enviada con éxito")
                st.info(
                    f"📧 Se ha enviado una notificación a: {', '.join(emails_admin + ([email_comercial] if email_comercial else []))}")
            else:
                st.warning("⚠️ No se encontró ningún email de administrador/gestor, no se pudo enviar la notificación.")

if __name__ == "__main__":
    comercial_dashboard_vip()