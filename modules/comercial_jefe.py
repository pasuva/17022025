import streamlit as st
import pandas as pd
import folium, io, sqlitecloud
from streamlit_folium import st_folium
from streamlit_option_menu import option_menu

from modules.notificaciones import correo_asignacion_administracion, correo_desasignacion_administracion, \
    correo_asignacion_administracion2, correo_reasignacion_saliente, \
    correo_reasignacion_entrante, correo_confirmacion_viab_admin
from folium.plugins import MarkerCluster
from streamlit_cookies_controller import CookieController  # Se importa localmente
from datetime import datetime

from branca.element import Template, MacroElement


import warnings
warnings.filterwarnings("ignore", category=UserWarning)

cookie_name = "my_app"

# Función para obtener conexión a la base de datos (SQLite Cloud)
def get_db_connection():
    return sqlitecloud.connect(
        "sqlitecloud://ceafu04onz.g6.sqlite.cloud:8860/usuarios.db?apikey=Qo9m18B9ONpfEGYngUKm99QB5bgzUTGtK7iAcThmwvY"
    )

# Función para registrar trazabilidad
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


@st.cache_data
def cargar_datos():
    """Carga los datos de las tablas con caché"""
    conn = get_db_connection()
    query_datos_uis = """
        SELECT apartment_id, latitud, longitud, fecha, provincia, municipio, vial, numero, letra, poblacion, cto_con_proyecto, serviciable 
        FROM datos_uis 
        WHERE comercial = 'RAFA SANZ'
    """
    datos_uis = pd.read_sql(query_datos_uis, conn)

    query_comercial_rafa = """
        SELECT apartment_id, serviciable, Contrato, municipio, poblacion, comercial 
        FROM comercial_rafa
    """
    comercial_rafa = pd.read_sql(query_comercial_rafa, conn)
    conn.close()
    return datos_uis, comercial_rafa

def cargar_total_ofertas():
    conn = get_db_connection()
    # comerciales_excluir es una lista o tupla de strings
    query_total_ofertas = f"""
        SELECT DISTINCT *
        FROM comercial_rafa
    """
    try:
        total_ofertas = pd.read_sql(query_total_ofertas, conn)
        return total_ofertas
    except Exception as e:
        import streamlit as st
        st.error(f"Error cargando total_ofertas: {e}")
        return pd.DataFrame()

def cargar_viabilidades():
    conn = get_db_connection()
    # comerciales_excluir es una lista o tupla de strings
    query_viabilidades = f"""
        SELECT DISTINCT *
        FROM viabilidades
    """
    try:
        viabilidades = pd.read_sql(query_viabilidades, conn)
        return viabilidades
    except Exception as e:
        import streamlit as st
        st.error(f"Error cargando total_ofertas: {e}")
        return pd.DataFrame()

def mapa_dashboard():
    """Panel de mapas optimizado para Rafa Sanz con asignación y desasignación de zonas comerciales"""
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

    # Panel lateral de bienvenida
    st.sidebar.markdown("""
        <style>
            .user-circle {
                width: 100px;
                height: 100px;
                border-radius: 50%;
                background-color: #0073e6;
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
        <div class="user-info">Rol: Gestor Comercial</div>
        <div class="welcome-msg">¡Bienvenido, <strong>{username}</strong>!</div>
        <hr>
    """.replace("{username}", st.session_state['username']), unsafe_allow_html=True)

    with st.sidebar:
        # Datos y menú
        datos_uis, comercial_rafa = cargar_datos()
        total_ofertas = cargar_total_ofertas()
        viabilidades = cargar_viabilidades()

        opcion = option_menu(
            menu_title=None,
            options=["Mapa Asignaciones", "Viabilidades", "Ver Datos", "Descargar Datos"],
            icons=["globe", "check-circle", "bar-chart", "download"],
            menu_icon="list",
            default_index=0,
            styles={
                "container": {
                    "padding": "0px",
                    "background-color": "#F0F7F2"
                },
                "icon": {
                    "color": "#2C5A2E",
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
                    "background-color": "#66B032",
                    "color": "white",
                    "font-weight": "bold"
                }
            }
        )

        # Botón de cerrar sesión debajo del menú
        if st.button("Cerrar sesión"):
            detalles = f"El gestor comercial {st.session_state.get('username', 'N/A')} cerró sesión."
            log_trazabilidad(st.session_state.get("username", "N/A"), "Cierre sesión", detalles)
            for key in [f'{cookie_name}_session_id', f'{cookie_name}_username', f'{cookie_name}_role']:
                if controller.get(key):
                    controller.set(key, '', max_age=0, path='/')
            st.session_state["login_ok"] = False
            st.session_state["username"] = ""
            st.session_state["role"] = ""
            st.session_state["session_id"] = ""
            st.success("✅ Has cerrado sesión correctamente. Redirigiendo al login...")
            st.rerun()

    # Lógica principal según la opción
    if opcion == "Mapa Asignaciones":
        mostrar_mapa_de_asignaciones()
    elif opcion == "Viabilidades":
        mostrar_viabilidades()
    elif opcion == "Ver Datos":
        mostrar_descarga_datos()
    elif opcion == "Descargar Datos":
        download_datos(datos_uis, total_ofertas, viabilidades)


def mostrar_mapa_de_asignaciones():
    st.title("Mapa Asignaciones")

    # Cargar datos con spinner
    with st.spinner("Cargando datos..."):
        datos_uis, comercial_rafa = cargar_datos()

        # 🔒 Filtro especial si el usuario es Juan
        if st.session_state["username"].strip().lower() == "juan":
            # Limpia valores nulos y normaliza
            datos_uis['provincia'] = datos_uis['provincia'].fillna("").str.strip().str.lower()
            datos_uis = datos_uis[datos_uis["provincia"].isin(["asturias", "lugo"])]
            #st.info("🔒 Estás viendo solo datos de Asturias y Lugo.")

            # Filtro por cto_con_proyecto según usuario
        if st.session_state["username"].strip().lower() == "juan":
            datos_uis = datos_uis[datos_uis["cto_con_proyecto"].str.lower() == "si"]
        elif st.session_state["username"].strip().lower() == "rafa sanz":
            datos_uis = datos_uis[
                datos_uis["cto_con_proyecto"].isnull() | (datos_uis["cto_con_proyecto"].str.strip() == "")]

        # Si después del filtro no quedan datos, detenemos
        if datos_uis.empty:
            st.warning("⚠️ No hay datos disponibles para mostrar.")
            st.stop()

    st.info("🔦 Por cuestiones de eficiencia en la carga de de datos, cuando hay una alta concentración de puntos, el mapa solo mostrará los puntos relativos a los filtros elegidos por el usuario. "
            "Usa el filtro de Provincia, Municipio y Población para poder ver los puntos que necesites.")
    # Filtro por provincia
    provincias = datos_uis['provincia'].unique()
    provincia_seleccionada = st.selectbox("Seleccione una provincia:", provincias)
    datos_uis = datos_uis[datos_uis["provincia"] == provincia_seleccionada]

    # Limpiar latitud y longitud
    datos_uis = datos_uis.dropna(subset=['latitud', 'longitud'])
    datos_uis['latitud'] = datos_uis['latitud'].astype(float)
    datos_uis['longitud'] = datos_uis['longitud'].astype(float)

    username = st.session_state.get("username", "").strip().lower()

    # Lista general de comerciales para otros usuarios
    comerciales_generales = ["jose ramon", "rafaela", "nestor", "roberto"]

    # Comerciales disponibles según usuario
    if username == "juan":
        comerciales_disponibles = ["comercial_juan_1"]
    else:
        comerciales_disponibles = comerciales_generales

    col1, col2 = st.columns([3, 3])
    with col2:
        accion = st.radio("Seleccione la acción requerida:", ["Asignar Zona", "Desasignar Zona"], key="accion")

        if accion == "Asignar Zona":
            municipios = sorted(datos_uis['municipio'].dropna().unique())
            municipio_sel = st.selectbox("Seleccione un municipio:", municipios, key="municipio_sel")
            poblacion_sel = None
            if municipio_sel:
                poblaciones = sorted(datos_uis[datos_uis['municipio'] == municipio_sel]['poblacion'].dropna().unique())
                poblacion_sel = st.selectbox("Seleccione una población:", poblaciones, key="poblacion_sel")

            # Mostrar comerciales filtrados según usuario
            comerciales_seleccionados = st.multiselect("Asignar equitativamente a:", comerciales_disponibles,
                                                       key="comerciales_seleccionados")

            if municipio_sel and poblacion_sel:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM comercial_rafa WHERE municipio = ? AND poblacion = ?",
                               (municipio_sel, poblacion_sel))
                count_assigned = cursor.fetchone()[0]
                conn.close()
                if count_assigned > 0:
                    st.warning("🚫 Esta zona ya ha sido asignada.")
                else:
                    if municipio_sel and poblacion_sel and comerciales_seleccionados:
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        cursor.execute("SELECT COUNT(*) FROM comercial_rafa WHERE municipio = ? AND poblacion = ?",
                                       (municipio_sel, poblacion_sel))
                        count_assigned = cursor.fetchone()[0]
                        conn.close()

                        if count_assigned > 0:
                            st.warning("🚫 Esta zona ya ha sido asignada.")
                        else:
                            if st.button("Asignar Zona"):
                                conn = get_db_connection()
                                cursor = conn.cursor()

                                cursor.execute("""
                                    SELECT apartment_id, provincia, municipio, poblacion, vial, numero, letra, cp, latitud, longitud
                                    FROM datos_uis
                                    WHERE municipio = ? AND poblacion = ? AND comercial = 'RAFA SANZ'
                                """, (municipio_sel, poblacion_sel))
                                puntos = cursor.fetchall()

                                if not puntos:
                                    st.warning("⚠️ No se encontraron puntos con comercial RAFA SANZ.")
                                    conn.close()
                                else:
                                    total_puntos = len(puntos)
                                    num_comerciales = len(comerciales_seleccionados)
                                    puntos_por_comercial = total_puntos // num_comerciales
                                    resto = total_puntos % num_comerciales

                                    progress_bar = st.progress(0)
                                    total_asignados = 0
                                    indice = 0

                                    for i, comercial in enumerate(comerciales_seleccionados):
                                        asignar_count = puntos_por_comercial + (1 if i < resto else 0)
                                        for _ in range(asignar_count):
                                            if indice >= total_puntos:
                                                break
                                            punto = puntos[indice]
                                            cursor.execute("""
                                                INSERT INTO comercial_rafa (apartment_id, provincia, municipio, poblacion, vial, numero, letra, cp, latitud, longitud, comercial, Contrato)
                                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Pendiente')
                                            """, (*punto, comercial))
                                            indice += 1
                                            total_asignados += 1
                                            progress_bar.progress(total_asignados / total_puntos)

                                    conn.commit()
                                    progress_bar.empty()

                                    # Enviar notificaciones
                                    for comercial in comerciales_seleccionados:
                                        try:
                                            cursor.execute("SELECT email FROM usuarios WHERE username = ?",
                                                           (comercial,))
                                            email_comercial = cursor.fetchone()
                                            destinatario_comercial = email_comercial[
                                                0] if email_comercial else "patricia@redytelcomputer.com"

                                            descripcion_asignacion = (
                                                f"📍 Se le ha asignado la zona {municipio_sel} - {poblacion_sel}.<br><br>"
                                                "💼 Ya puede comenzar a gestionar las tareas correspondientes.<br>"
                                                "ℹ️ Revise su panel de usuario para más detalles.<br><br>"
                                                "🚨 Si tiene dudas, contacte con administración.<br>¡Gracias!"
                                            )
                                            correo_asignacion_administracion(destinatario_comercial, municipio_sel,
                                                                             poblacion_sel, descripcion_asignacion)
                                        except Exception as e:
                                            st.error(f"❌ Error al notificar a {comercial}: {e}")

                                    # Notificar a admins
                                    cursor.execute("SELECT email FROM usuarios WHERE role = 'admin'")
                                    emails_admins = [fila[0] for fila in cursor.fetchall()]
                                    descripcion_admin = (
                                        f"📢 Nueva asignación de zona.\n\n"
                                        f"📌 Zona Asignada: {municipio_sel} - {poblacion_sel}\n"
                                        f"👥 Asignado a: {', '.join(comerciales_seleccionados)}\n"
                                        f"🕵️ Asignado por: {st.session_state['username']}"
                                    )
                                    for email_admin in emails_admins:
                                        correo_asignacion_administracion2(email_admin, municipio_sel, poblacion_sel,
                                                                          descripcion_admin)

                                    st.success("✅ Zona asignada correctamente y notificaciones enviadas.")
                                    st.info(f"📧 Se notificó a: {', '.join(comerciales_seleccionados)}")
                                    log_trazabilidad(st.session_state["username"], "Asignación múltiple",
                                                     f"Zona {municipio_sel}-{poblacion_sel} repartida entre {', '.join(comerciales_seleccionados)}")
                                    conn.close()

        elif accion == "Desasignar Zona":
            conn = get_db_connection()
            assigned_zones = pd.read_sql("SELECT DISTINCT municipio, poblacion FROM comercial_rafa", conn)
            conn.close()

            if assigned_zones.empty:
                st.warning("No hay zonas asignadas para desasignar.")
            else:
                assigned_zones['municipio'] = assigned_zones['municipio'].fillna('').astype(str)
                assigned_zones['poblacion'] = assigned_zones['poblacion'].fillna('').astype(str)

                assigned_zones = assigned_zones[
                    (assigned_zones['municipio'] != '') & (assigned_zones['poblacion'] != '')]
                assigned_zones['zona'] = assigned_zones['municipio'] + " - " + assigned_zones['poblacion']
                zonas_list = sorted(assigned_zones['zona'].unique())
                zona_seleccionada = st.selectbox("Seleccione la zona asignada a desasignar", zonas_list,
                                                 key="zona_seleccionada")

                if zona_seleccionada:
                    municipio_sel, poblacion_sel = zona_seleccionada.split(" - ")

                    conn = get_db_connection()
                    query = """
                        SELECT DISTINCT comercial FROM comercial_rafa 
                        WHERE municipio = ? AND poblacion = ?
                    """
                    comerciales_asignados = pd.read_sql(query, conn, params=(municipio_sel, poblacion_sel))
                    conn.close()

                    # Filtrar comerciales asignados según usuario
                    if username == "juan":
                        comerciales_asignados = comerciales_asignados[
                            comerciales_asignados['comercial'] == "comercial_juan_1"]
                    # else: otros usuarios ven todos comerciales asignados

                    if comerciales_asignados.empty:
                        st.warning("No hay comerciales asignados a esta zona.")
                    else:
                        comercial_a_eliminar = st.selectbox("Seleccione el comercial a desasignar",
                                                            comerciales_asignados["comercial"].tolist())
                        if st.button("Desasignar Comercial de Zona"):
                            conn = get_db_connection()
                            cursor = conn.cursor()

                            # Verificar si hay registros con Contrato no nulo
                            cursor.execute("""
                                SELECT COUNT(*) FROM comercial_rafa
                                WHERE municipio = ? AND poblacion = ? AND comercial = ? AND Contrato IS NOT NULL
                            """, (municipio_sel, poblacion_sel, comercial_a_eliminar))
                            visitas_existentes = cursor.fetchone()[0]

                            if visitas_existentes > 0:
                                st.error(
                                    "❌ No se puede desasignar esta zona porque ya tiene registros con visita asociada y posible contrato.")
                                conn.close()
                            else:
                                # Si no hay visitas/contratos, proceder al borrado
                                cursor.execute("""
                                    DELETE FROM comercial_rafa 
                                    WHERE municipio = ? AND poblacion = ? AND comercial = ?
                                """, (municipio_sel, poblacion_sel, comercial_a_eliminar))
                                conn.commit()

                                # Continuar con notificaciones, etc.
                                cursor.execute("SELECT email FROM usuarios WHERE username = ?", (comercial_a_eliminar,))
                                email_comercial = cursor.fetchone()
                                destinatario_comercial = email_comercial[
                                    0] if email_comercial else "patricia@redytelcomputer.com"

                                cursor.execute("SELECT email FROM usuarios WHERE role = 'admin'")
                                emails_admins = [fila[0] for fila in cursor.fetchall()]
                                conn.close()

                                descripcion_desasignacion = (
                                    f"📍 Se le ha desasignado la zona {municipio_sel} - {poblacion_sel}.<br>"
                                    "🔄 Este cambio puede deberse a ajustes en las zonas asignadas.<br>"
                                    "⚠️ Ya no estará a cargo de las tareas de esta zona.<br>"
                                    "ℹ️ Revise su panel de usuario para más detalles.<br><br>"
                                    "🚨 Si tiene dudas, contacte con administración.<br>¡Gracias!"
                                )
                                correo_desasignacion_administracion(destinatario_comercial, municipio_sel,
                                                                    poblacion_sel, descripcion_desasignacion)

                                descripcion_admin = (
                                    f"📢 Desasignación de zona.\n\n"
                                    f"📌 Zona Desasignada: {municipio_sel} - {poblacion_sel}\n"
                                    f"👥 Desasignado: {comercial_a_eliminar}\n"
                                    f"🕵️ Realizado por: {st.session_state['username']}"
                                )
                                for email_admin in emails_admins:
                                    correo_asignacion_administracion2(email_admin, municipio_sel, poblacion_sel,
                                                                      descripcion_admin)

                                st.success("✅ Zona desasignada correctamente y notificaciones enviadas.")
                                log_trazabilidad(st.session_state["username"], "Desasignación múltiple",
                                                 f"Zona {municipio_sel}-{poblacion_sel} desasignada de {comercial_a_eliminar}")

        st.info(
            "Para revisar las asignaciones que has realizado y los reportes enviados por los comerciales, dirígete al menú **Ver Datos**. "
            "Ahora encontrarás un submenú con tres secciones: "
            "**Zonas asignadas**: muestra las asignaciones realizadas por el gestor. "
            "**Ofertas realizadas**: detalla las visitas y ofertas gestionadas por los comerciales, junto a su estado actual. "
            "**Viabilidades estudiadas**: presenta el historial completo de viabilidades reportadas por los comerciales."
        )

    # --- Generar el mapa (columna izquierda) ---
    with col1:
        with st.spinner("⏳ Cargando mapa... (Puede tardar según la cantidad de puntos)"):
            center = [datos_uis.iloc[0]['latitud'], datos_uis.iloc[0]['longitud']]
            zoom_start = 12
            if "municipio_sel" in st.session_state and "poblacion_sel" in st.session_state:
                zone_data = datos_uis[(datos_uis["municipio"] == st.session_state["municipio_sel"]) &
                                      (datos_uis["poblacion"] == st.session_state["poblacion_sel"])]
                if not zone_data.empty:
                    center = [zone_data["latitud"].mean(), zone_data["longitud"].mean()]
                    zoom_start = 14

            m = folium.Map(
                location=center,
                zoom_start=zoom_start,
                tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
                attr="Google"
            )
            marker_cluster = MarkerCluster(disableClusteringAtZoom=18, maxClusterRadius=70,
                                           spiderfyOnMaxZoom=True).add_to(m)

            if "municipio_sel" in st.session_state and "poblacion_sel" in st.session_state:
                datos_filtrados = datos_uis[
                    (datos_uis["municipio"] == st.session_state["municipio_sel"]) &
                    (datos_uis["poblacion"] == st.session_state["poblacion_sel"])
                    ]
            else:
                datos_filtrados = datos_uis.head(0)  # No mostrar ningún punto si no hay filtros

            for _, row in datos_filtrados.iterrows():
                lat, lon = row['latitud'], row['longitud']
                apartment_id = row['apartment_id']
                vial = row.get('vial', 'No Disponible')
                numero = row.get('numero', 'No Disponible')
                letra = row.get('letra', 'No Disponible')

                # Valor de serviciable desde datos_uis
                serviciable_val = str(row.get('serviciable', '')).strip().lower()

                oferta = comercial_rafa[comercial_rafa['apartment_id'] == apartment_id]
                color = 'blue'

                # 🔄 Nueva lógica con prioridad para incidencia
                if not oferta.empty:
                    incidencia = str(oferta.iloc[0].get('incidencia', '')).strip().lower()
                    if incidencia == 'Sí':
                        color = 'purple'
                    else:
                        serviciable_val = str(row.get('serviciable', '')).strip().lower()
                        oferta_serviciable = str(oferta.iloc[0].get('serviciable', '')).strip().lower()
                        contrato = str(oferta.iloc[0].get('Contrato', '')).strip().lower()

                        if serviciable_val == "si":
                            color = 'green'
                        elif serviciable_val == "no" or oferta_serviciable == "no":
                            color = 'red'
                        elif contrato == "sí":
                            color = 'orange'
                        elif contrato == "no interesado":
                            color = 'black'

                icon_name = 'home' if str(row.get('cto_con_proyecto', '')).strip().lower() == 'si' else 'info-sign'
                popup_text = f"""
                    <b>Apartment ID:</b> {apartment_id}<br>
                    <b>Vial:</b> {vial}<br>
                    <b>Número:</b> {numero}<br>
                    <b>Letra:</b> {letra}<br>
                """
                folium.Marker(
                    [lat, lon],
                    icon=folium.Icon(icon=icon_name, color=color),
                    popup=folium.Popup(popup_text, max_width=300)
                ).add_to(marker_cluster)
            legend = """
            {% macro html() %}
            <div style="
                position: fixed; 
                bottom: 20px; left: 0px; width: 190px; 
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
            <i style="color:green;">●</i> Serviciable y Finalizado<br>
            <i style="color:red;">●</i> No serviciable<br>
            <i style="color:orange;">●</i> Contrato Sí<br>
            <i style="color:black;">●</i> No interesado<br>
            <i style="color:purple;">●</i> Incidencia<br>
            <i style="color:blue;">●</i> No Visitado<br>
            <i>🏠</i> Con proyecto<br>
            <i>ℹ️</i> Sin proyecto
            </div>
            {% endmacro %}
            """

            macro = MacroElement()
            macro._template = Template(legend)
            m.get_root().add_child(macro)
            st_folium(m, height=500, width=700)

def mostrar_descarga_datos():
    sub_seccion = option_menu(
        menu_title=None,
        options=["Zonas asignadas", "Ofertas realizadas", "Viabilidades estudiadas", "Datos totales"],
        icons = ["geo-alt", "bar-chart-line", "check2-square", "database"],
        default_index=0,
        orientation="horizontal",
        styles={
            "container": {
                "padding": "0!important",
                "margin": "0px",
                "background-color": "#F0F7F2",
                "border-radius": "0px",
                "max-width": "none"
            },
            "icon": {
                "color": "#2C5A2E",
                "font-size": "25px"
            },
            "nav-link": {
                "color": "#2C5A2E",
                "font-size": "18px",
                "text-align": "center",
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

    # Conexión y datos comunes
    conn = get_db_connection()
    username = st.session_state.get("username", "").strip().lower()
    excluir_para_juan = ["nestor", "rafaela", "jose ramon", "roberto"]
    placeholders = ",".join("?" for _ in excluir_para_juan)

    # Cargar datos según el usuario
    if username == "juan":
        assigned_zones = pd.read_sql(
            f"""
            SELECT DISTINCT municipio, poblacion, comercial
            FROM comercial_rafa
            WHERE LOWER(comercial) NOT IN ({placeholders})
            """, conn, params=[c.lower() for c in excluir_para_juan])

        total_ofertas = pd.read_sql(
            f"""
            SELECT DISTINCT *
            FROM comercial_rafa
            WHERE LOWER(comercial) NOT IN ({placeholders})
            """, conn, params=[c.lower() for c in excluir_para_juan])
    else:
        assigned_zones = pd.read_sql(
            "SELECT DISTINCT municipio, poblacion, comercial FROM comercial_rafa", conn)
        total_ofertas = pd.read_sql(
            "SELECT DISTINCT * FROM comercial_rafa", conn)

    # Contratos activos
    df_contratos = pd.read_sql("""
        SELECT apartment_id
        FROM seguimiento_contratos
        WHERE TRIM(LOWER(estado)) = 'finalizado'
    """, conn)

    conn.close()

    # Marcar contratos activos
    total_ofertas['Contrato_Activo'] = total_ofertas['apartment_id'].isin(df_contratos['apartment_id']).map(
        {True: '✅ Activo', False: '❌ No Activo'}
    )

    # Subsección: Zonas asignadas
    if sub_seccion == "Zonas asignadas":
        st.info("ℹ️ Zonas ya asignadas: Visualización del total de asignaciones realizadas por el gestor.")
        st.dataframe(assigned_zones, use_container_width=True)

    # Sub: Ofertas realizadas
    elif sub_seccion == "Ofertas realizadas":
        log_trazabilidad(username, "Visualización de mapa", "Usuario visualizó el mapa de Rafa Sanz.")
        st.info("ℹ️ Ofertas comerciales: Visualización del total de ofertas asignadas a cada comercial y su estado actual")
        st.dataframe(total_ofertas, use_container_width=True)

    # Sub: Viabilidades estudiadas
    elif sub_seccion == "Viabilidades estudiadas":
        conn = get_db_connection()
        viabilidades = pd.read_sql("""
            SELECT *
            FROM viabilidades
            ORDER BY id DESC
        """, conn)
        conn.close()

        viabilidades['fecha_viabilidad'] = pd.to_datetime(viabilidades['fecha_viabilidad'], errors='coerce')
        viabilidades['usuario'] = viabilidades['usuario'].fillna("").str.strip().str.lower()

        if username == "juan":
            comerciales_excluir = ["roberto", "jose ramon", "nestor", "rafaela", "rebe", "marian", "rafa sanz"]
            viabilidades = viabilidades[~viabilidades['usuario'].isin(comerciales_excluir)]

        st.info("ℹ️ Viabilidades: Visualización del total de viabilidades reportadas por cada comercial y su estado actual")
        st.dataframe(viabilidades, use_container_width=True)


    elif sub_seccion == "Datos totales":
        st.info("ℹ️ Visualización total de los datos")
        username = st.session_state.get("username", "").strip().lower()
        # Conectar a la base de datos y leer la tabla
        conn = get_db_connection()
        datos_uis = pd.read_sql("SELECT apartment_id, address_id, provincia, municipio, poblacion, vial numero, parcela_catastral, "
                                "letra, cp, olt, cto, latitud, longitud FROM datos_uis", conn)
        conn.close()
        if username == "juan":
            # Solo Lugo y Asturias
            datos_filtrados = datos_uis[datos_uis['provincia'].str.strip().str.lower().isin(["lugo", "asturias"])]
            st.dataframe(datos_filtrados, use_container_width=True, height=580)

        elif username == "rafa sanz":
            # Solo registros cuyo comercial sea 'rafa sanz'
            datos_filtrados = datos_uis[datos_uis['comercial'].str.strip().str.lower() == "rafa sanz"]
            st.dataframe(datos_filtrados, use_container_width=True, height=580)
        else:
            st.warning("⚠️ No tienes acceso a visualizar estos datos.")

def mostrar_viabilidades():
    sub_seccion = option_menu(
        menu_title=None,  # Sin título encima del menú
        options=["Viabilidades pendientes de confirmación", "Seguimiento de viabilidades"],
        icons = ["exclamation-circle", "clipboard-check"],  # Puedes cambiar iconos
        default_index=0,
        orientation="horizontal",  # horizontal para que quede tipo pestañas arriba
        styles={
            "container": {
                "padding": "0!important",
                "margin": "0px",
                "background-color": "#F0F7F2",
                "border-radius": "0px",
                "max-width": "none"
            },
            "icon": {
                "color": "#2C5A2E",  # Íconos en verde oscuro
                "font-size": "25px"
            },
            "nav-link": {
                "color": "#2C5A2E",
                "font-size": "18px",
                "text-align": "center",
                "margin": "0px",
                "--hover-color": "#66B032",
                "border-radius": "0px",
            },
            "nav-link-selected": {
                "background-color": "#66B032",  # Verde principal corporativo
                "color": "white",
                "font-weight": "bold"
            }
        }
    )
    if sub_seccion == "Viabilidades pendientes de confirmación":
        # 🔗 Conexión única al iniciar la sección
        conn = get_db_connection()

        # 1️⃣  Descargar viabilidades aún sin confirmar (con lat/lon)
        # 🧑 Usuario actual
        username = st.session_state.get("username", "").strip().lower()

        # ❗Lista de comerciales que Juan no debe ver
        excluir_para_juan = ["nestor", "rafaela", "jose ramon", "roberto"]

        # 🧠 Construcción dinámica del SQL
        if username == "juan":
            placeholders = ",".join("?" for _ in excluir_para_juan)
            query = f"""
                SELECT id,
                       provincia, municipio, poblacion,
                       vial, numero, letra,
                       latitud, longitud,
                       serviciable,
                       usuario AS comercial_reporta,
                       confirmacion_rafa
                FROM viabilidades
                WHERE (confirmacion_rafa IS NULL OR confirmacion_rafa = '')
                  AND LOWER(usuario) NOT IN ({placeholders})
                  AND LOWER(usuario) NOT IN ('marian', 'rafa sanz', 'rebe')
            """
            df_viab = pd.read_sql(query, conn, params=[c.lower() for c in excluir_para_juan])
        else:
            df_viab = pd.read_sql("""
                SELECT id,
                       provincia, municipio, poblacion,
                       vial, numero, letra,
                       latitud, longitud,
                       serviciable,
                       usuario AS comercial_reporta,
                       confirmacion_rafa
                FROM viabilidades
                WHERE confirmacion_rafa IS NULL OR confirmacion_rafa = ''
            """, conn)

        # 2️⃣  Listas de usuarios por rol
        comerciales_rafa = pd.read_sql(
            "SELECT username FROM usuarios WHERE role = 'comercial_rafa'", conn
        )["username"].tolist()
        admins = pd.read_sql(
            "SELECT email FROM usuarios WHERE role = 'admin'", conn
        )["email"].tolist()

        st.info("""ℹ️ Desde este panel podrás: Revisar cuáles están pendientes de confirmación y reasignar una viabilidad a otro comercial, si lo consideras necesario.

        🔔 NOTA: Para que una viabilidad sea enviada a la oficina de administración y comience su estudio, es imprescindible que la confirmes.  
        Solo deben ser confirmadas aquellas que, tras tu revisión, consideres aptas para recibir un estudio y presupuesto.
        
        📝 ¿Cómo confirmar una viabilidad? Haz clic sobre cualquier viabilidad del listado: se desplegará su descripción, un enlace directo a Google Maps, 
        la opción de reasignación y un botón para confirmar.
        """)

        if df_viab.empty:
            st.success("🎉No hay viabilidades pendientes de confirmación.")
        else:
            for _, row in df_viab.iterrows():

                # Si esta viabilidad ya fue gestionada en esta sesión, la ocultamos
                if st.session_state.get(f"ocultar_{row.id}"):
                    continue

                with st.expander(
                        f"ID{row.id} — {row.municipio} / {row.vial} "
                        f"{row.numero}{row.letra or ''}",
                        expanded=False
                ):
                    st.markdown(
                        f"**Comercial que la envió:** {row.comercial_reporta}<br>"
                        f"**Serviciable:** {row.serviciable or 'Sin dato'}",
                        unsafe_allow_html=True
                    )

                    # Link GoogleMaps
                    if pd.notna(row.latitud) and pd.notna(row.longitud):
                        maps_url = (
                            f"https://www.google.com/maps/search/?api=1"
                            f"&query={row.latitud},{row.longitud}"
                        )
                        st.markdown(f"[🌍Ver en GoogleMaps]({maps_url})")

                    col_ok, col_rea = st.columns([1, 2], gap="small")

                    # --------------- CONFIRMAR ----------------
                    with col_ok:
                        if st.button("✅Confirmar", key=f"ok_{row.id}"):
                            with st.spinner("Confirmando viabilidad…"):
                                conn.execute(
                                    "UPDATE viabilidades SET confirmacion_rafa = 'OK' WHERE id = ?",
                                    (row.id,)
                                )
                                conn.commit()

                                for email_admin in admins:
                                    correo_confirmacion_viab_admin(
                                        destinatario=email_admin,
                                        id_viab=row.id,
                                        comercial_orig=row.comercial_reporta
                                    )

                            st.success(f"Viabilidad {row.id} confirmada.")
                            st.session_state[f"ocultar_{row.id}"] = True  # Oculta la fila

                    # --------------- REASIGNAR ----------------
                    with col_rea:
                        destinos = [c for c in comerciales_rafa if c != row.comercial_reporta]
                        nuevo_com = st.selectbox(
                            "🔄Reasignar a",
                            options=[""] + destinos,
                            key=f"sel_{row.id}"
                        )

                        if st.button("↪️Reasignar", key=f"reasig_{row.id}"):
                            if not nuevo_com:
                                st.warning("Selecciona un comercial para reasignar.")
                            else:
                                with st.spinner("Reasignando viabilidad…"):
                                    conn.execute("""
                                        UPDATE viabilidades
                                        SET usuario = ?, confirmacion_rafa = 'Reasignada'
                                        WHERE id = ?
                                    """, (nuevo_com, row.id))
                                    conn.commit()

                                    correo_reasignacion_saliente(
                                        destinatario=row.comercial_reporta,
                                        id_viab=row.id,
                                        nuevo_comercial=nuevo_com
                                    )
                                    correo_reasignacion_entrante(
                                        destinatario=nuevo_com,
                                        id_viab=row.id,
                                        comercial_orig=row.comercial_reporta
                                    )

                                st.success(f"Viabilidad {row.id} reasignada a {nuevo_com}.")

        # 🔒 Cerrar la conexión al final
        conn.close()
    if sub_seccion == "Seguimiento de viabilidades":
        # 🔎 Consulta general de TODAS las viabilidades
        conn = get_db_connection()
        viabilidades = pd.read_sql("""
            SELECT *
            FROM viabilidades
            ORDER BY id DESC
        """, conn)
        conn.close()

        # 🔒 Filtro por usuario
        username = st.session_state.get("username", "").strip().lower()

        if username == "juan":
            # Excluir ciertos comerciales
            comerciales_excluir = ["roberto", "jose ramon", "nestor", "rafaela","marian","rebe","rafa sanz"]
            viabilidades['usuario'] = viabilidades['usuario'].fillna("").str.strip().str.lower()
            viabilidades = viabilidades[~viabilidades['usuario'].isin(comerciales_excluir)]

        # 📋 Mostrar tabla resultante
        st.info("ℹ️ Listado completo de viabilidades y su estado actual.")
        st.dataframe(viabilidades, use_container_width=True)

def download_datos(datos_uis, total_ofertas, viabilidades):
    st.info("ℹ️ Dependiendo del tamaño de los datos, la descarga puede tardar algunos segundos.")
    dataset_opcion = st.selectbox("¿Qué deseas descargar?", ["Datos", "Ofertas asignadas", "Viabilidades", "Todo"])
    nombre_base = st.text_input("Nombre base del archivo:", "datos")

    fecha_actual = datetime.now().strftime("%Y-%m-%d")
    nombre_archivo_final = f"{nombre_base}_{fecha_actual}"

    username = st.session_state.get("username", "").strip().lower()

    # Aplicar filtros personalizados si es Juan
    if username == "juan":
        datos_filtrados = datos_uis[
            datos_uis['provincia'].str.strip().str.lower().isin(["lugo", "asturias"])
        ]
        ofertas_filtradas = total_ofertas[
            ~total_ofertas['comercial'].str.strip().str.lower().isin(
                ["roberto", "jose ramon", "nestor", "rafaela", "rebe", "marian", "rafa sanz"]
            )
        ]
        viabilidades_filtradas = viabilidades[
            ~viabilidades['usuario'].str.strip().str.lower().isin(
                ["roberto", "jose ramon", "nestor", "rafaela", "rebe", "marian", "rafa sanz"]
            )
        ].copy()

        viabilidades_filtradas['fecha_viabilidad'] = pd.to_datetime(viabilidades_filtradas['fecha_viabilidad'],
                                                                    errors='coerce')
    else:
        datos_filtrados = datos_uis.copy()
        ofertas_filtradas = total_ofertas.copy()
        viabilidades_filtradas = viabilidades.copy()

    def descargar_excel(dfs_dict, nombre_archivo):
        for sheet_name, df in dfs_dict.items():
            if not isinstance(df, pd.DataFrame):
                st.warning(f"No hay datos válidos para descargar en la hoja '{sheet_name}'.")
                return

        if 'fecha_viabilidad' in viabilidades_filtradas.columns:
            viabilidades_filtradas['fecha_viabilidad'] = pd.to_datetime(
                viabilidades_filtradas['fecha_viabilidad'], errors='coerce'
            )

        with io.BytesIO() as output:
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                for sheet_name, df in dfs_dict.items():
                    df.to_excel(writer, sheet_name=sheet_name[:31], index=False)
            output.seek(0)
            st.download_button(
                label=f"📥 Descargar {nombre_archivo}",
                data=output,
                file_name=f"{nombre_archivo}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    # Lógica de descarga según la selección
    if dataset_opcion == "Datos":
        log_trazabilidad(username, "Descarga de datos", "Usuario descargó los datos.")
        descargar_excel({"Datos Gestor": datos_filtrados}, nombre_archivo_final)

    elif dataset_opcion == "Ofertas asignadas":
        log_trazabilidad(username, "Descarga de datos", "Usuario descargó ofertas asignadas.")
        descargar_excel({"Ofertas Asignadas": ofertas_filtradas}, nombre_archivo_final)

    elif dataset_opcion == "Viabilidades":
        log_trazabilidad(username, "Descarga de datos", "Usuario descargó viabilidades.")
        descargar_excel({"Viabilidades": viabilidades_filtradas}, nombre_archivo_final)

    elif dataset_opcion == "Todo":
        log_trazabilidad(username, "Descarga de datos", "Usuario descargó todos los datos.")
        descargar_excel({
            "Datos Gestor": datos_filtrados,
            "Ofertas Asignadas": ofertas_filtradas,
            "Viabilidades": viabilidades_filtradas
        }, nombre_archivo_final)

if __name__ == "__main__":
    mapa_dashboard()
