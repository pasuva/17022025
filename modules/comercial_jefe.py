import streamlit as st
import pandas as pd
import folium, io, sqlitecloud
from streamlit_folium import st_folium
from streamlit_option_menu import option_menu

from modules.notificaciones import correo_asignacion_administracion, correo_desasignacion_administracion, \
    correo_asignacion_administracion2, correo_reasignacion_saliente, \
    correo_reasignacion_entrante, correo_confirmacion_viab_admin, correo_viabilidad_comercial
from folium.plugins import MarkerCluster, Geocoder
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
        SELECT apartment_id, latitud, longitud, fecha, provincia, municipio, vial, numero, letra, poblacion, tipo_olt_rental, serviciable 
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
            # st.info("🔒 Estás viendo solo datos de Asturias y Lugo.")

            # Filtro por tipo_olt_rental según usuario
        #if st.session_state["username"].strip().lower() == "juan":
        #    datos_uis = datos_uis[datos_uis["tipo_olt_rental"].str.lower() == "CTO COMPARTIDA"]
        #elif st.session_state["username"].strip().lower() == "rafa sanz":
        #    datos_uis = datos_uis[
        #        datos_uis["tipo_olt_rental"].isnull() | (datos_uis["tipo_olt_rental"].str.strip() == "")]

        # Si después del filtro no quedan datos, detenemos
        if datos_uis.empty:
            st.warning("⚠️ No hay datos disponibles para mostrar.")
            st.stop()

    st.info(
        "🔦 Por cuestiones de eficiencia en la carga de de datos, cuando hay una alta concentración de puntos, el mapa solo mostrará los puntos relativos a los filtros elegidos por el usuario. "
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
            comerciales_seleccionados = st.multiselect(
                "Asignar equitativamente a:", comerciales_disponibles,
                key="comerciales_seleccionados"
            )

            if municipio_sel and poblacion_sel:
                conn = get_db_connection()
                cursor = conn.cursor()

                # Total de puntos de esa zona en datos_uis
                cursor.execute("""
                    SELECT COUNT(*) 
                    FROM datos_uis
                    WHERE municipio = ? AND poblacion = ? AND comercial = 'RAFA SANZ'
                """, (municipio_sel, poblacion_sel))
                row = cursor.fetchone()
                total_puntos = row[0] if row else 0

                # Total de puntos ya asignados
                cursor.execute("""
                    SELECT COUNT(*)
                    FROM comercial_rafa
                    WHERE municipio = ? AND poblacion = ?
                """, (municipio_sel, poblacion_sel))
                row = cursor.fetchone()
                asignados = row[0] if row else 0

                pendientes = total_puntos - asignados

                conn.close()

                if asignados >= total_puntos and total_puntos > 0:
                    st.warning("🚫 Esta zona ya ha sido asignada completamente.")
                else:
                    if municipio_sel and poblacion_sel and comerciales_seleccionados:
                        if st.button("Asignar Zona"):
                            conn = get_db_connection()
                            cursor = conn.cursor()

                            # Seleccionar solo los puntos no asignados todavía
                            cursor.execute("""
                                SELECT apartment_id, provincia, municipio, poblacion, vial, numero, letra, cp, latitud, longitud
                                FROM datos_uis
                                WHERE municipio = ? AND poblacion = ? 
                                  AND comercial = 'RAFA SANZ'
                                  AND apartment_id NOT IN (
                                      SELECT apartment_id FROM comercial_rafa
                                      WHERE municipio = ? AND poblacion = ?
                                  )
                            """, (municipio_sel, poblacion_sel, municipio_sel, poblacion_sel))
                            puntos = cursor.fetchall()

                            nuevos_asignados = len(puntos)

                            if not puntos:
                                st.warning("⚠️ No se encontraron puntos pendientes de asignar en esta zona.")
                                conn.close()
                            else:
                                total_puntos = len(puntos)
                                num_comerciales = len(comerciales_seleccionados)
                                puntos_por_comercial = total_puntos // num_comerciales
                                resto = total_puntos % num_comerciales

                                progress_bar = st.progress(0)
                                total_asignados = 0
                                indice = 0

                                # 🔹 Mensaje dinámico
                                if asignados + nuevos_asignados >= total_puntos:
                                    estado = "✅ La zona ha quedado COMPLETAMENTE asignada."
                                else:
                                    estado = f"ℹ️ Solo se asignaron {nuevos_asignados} puntos que quedaban pendientes."

                                for i, comercial in enumerate(comerciales_seleccionados):
                                    asignar_count = puntos_por_comercial + (1 if i < resto else 0)
                                    for _ in range(asignar_count):
                                        if indice >= total_puntos:
                                            break
                                        punto = puntos[indice]
                                        cursor.execute("""
                                            INSERT INTO comercial_rafa 
                                            (apartment_id, provincia, municipio, poblacion, vial, numero, letra, cp, latitud, longitud, comercial, Contrato)
                                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Pendiente')
                                        """, (*punto, comercial))
                                        indice += 1
                                        total_asignados += 1
                                        progress_bar.progress(total_asignados / total_puntos)

                                conn.commit()
                                progress_bar.empty()

                                # Enviar notificaciones a comerciales
                                for comercial in comerciales_seleccionados:
                                    try:
                                        cursor.execute("SELECT email FROM usuarios WHERE username = ?", (comercial,))
                                        email_comercial = cursor.fetchone()
                                        destinatario_comercial = email_comercial[
                                            0] if email_comercial else "patricia@verdetuoperador.com"

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

                                # Notificar a administradores
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
                                st.info(
                                    f"📊 Total puntos: {total_puntos} | Ya asignados: {asignados} | Nuevos: {nuevos_asignados} | Pendientes tras asignación: {total_puntos - (asignados + nuevos_asignados)}")
                                log_trazabilidad(
                                    st.session_state["username"], "Asignación múltiple",
                                    f"Zona {municipio_sel}-{poblacion_sel} repartida entre {', '.join(comerciales_seleccionados)}"
                                )
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

                            # Verificar cuántos registros NO se pueden borrar
                            cursor.execute("""
                                SELECT COUNT(*) FROM comercial_rafa
                                WHERE municipio = ? AND poblacion = ? AND comercial = ? AND Contrato != 'Pendiente'
                            """, (municipio_sel, poblacion_sel, comercial_a_eliminar))
                            registros_bloqueados = cursor.fetchone()[0]

                            # Guardar TODOS los puntos liberados en la tabla temporal
                            cursor.execute("""
                                INSERT INTO puntos_liberados_temp
                                (apartment_id, provincia, municipio, poblacion, vial, numero, letra, cp, latitud, longitud, comercial, Contrato)
                                SELECT apartment_id, provincia, municipio, poblacion, vial, numero, letra, cp, latitud, longitud, comercial, Contrato
                                FROM comercial_rafa
                                WHERE municipio = ? AND poblacion = ? AND comercial = ?
                            """, (municipio_sel, poblacion_sel, comercial_a_eliminar))

                            # Eliminar TODOS los registros de esa zona para ese comercial
                            cursor.execute("""
                                DELETE FROM comercial_rafa 
                                WHERE municipio = ? AND poblacion = ? AND comercial = ?
                            """, (municipio_sel, poblacion_sel, comercial_a_eliminar))
                            registros_eliminados = cursor.rowcount
                            conn.commit()

                            if registros_eliminados > 0:
                                # Calcular total de registros de la zona para ese comercial
                                total_registros = registros_eliminados

                                # Notificar
                                cursor.execute("SELECT email FROM usuarios WHERE username = ?", (comercial_a_eliminar,))
                                email_comercial = cursor.fetchone()
                                destinatario_comercial = email_comercial[
                                    0] if email_comercial else "patricia@verdetuoperador.com"

                                cursor.execute("SELECT email FROM usuarios WHERE role = 'admin'")
                                emails_admins = [fila[0] for fila in cursor.fetchall()]
                                conn.close()

                                descripcion_desasignacion = (
                                    f"📍 Se le ha desasignado la zona {municipio_sel} - {poblacion_sel}.<br>"
                                    f"📊 Total puntos eliminados: {total_registros}<br><br>"
                                    "ℹ️ Revise su panel de usuario para más detalles.<br>"
                                    "🚨 Si tiene dudas, contacte con administración.<br>¡Gracias!"
                                )
                                correo_desasignacion_administracion(destinatario_comercial, municipio_sel,
                                                                    poblacion_sel, descripcion_desasignacion)

                                descripcion_admin = (
                                    f"📢 Desasignación de zona.\n\n"
                                    f"📌 Zona: {municipio_sel} - {poblacion_sel}\n"
                                    f"👥 Comercial afectado: {comercial_a_eliminar}\n"
                                    f"📊 Total puntos eliminados: {total_registros}\n"
                                    f"🕵️ Realizado por: {st.session_state['username']}"
                                )
                                for email_admin in emails_admins:
                                    correo_asignacion_administracion2(email_admin, municipio_sel, poblacion_sel,
                                                                      descripcion_admin)

                                # Mensajes claros en la interfaz
                                st.success(
                                    f"✅ Se ha desasignado completamente la zona {municipio_sel} - {poblacion_sel} "
                                    f"para el comercial **{comercial_a_eliminar}**.\n\n"
                                    f"📊 Total puntos eliminados: {total_registros}"
                                )

                                # Log
                                accion_log = "Desasignación total"
                                detalle_log = (
                                    f"Zona {municipio_sel}-{poblacion_sel} desasignada de {comercial_a_eliminar} - "
                                    f"{registros_eliminados} eliminados"
                                )
                                log_trazabilidad(st.session_state["username"], accion_log, detalle_log)

                            else:
                                conn.close()
                                st.info(
                                    f"ℹ️ No había puntos para desasignar en la zona {municipio_sel} - {poblacion_sel} "
                                    f"para el comercial **{comercial_a_eliminar}**."
                                )

        # --- REASIGNAR PUNTOS ---
        # FORMULARIO DE REASIGNACIÓN (FUERA DEL BLOQUE DE DESASIGNACIÓN)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM puntos_liberados_temp")
        count = cursor.fetchone()[0]
        conn.close()

        if count > 0:
            st.subheader("Reasignar Puntos Liberados")

            # Obtener comerciales activos
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT username FROM usuarios WHERE role = 'comercial_rafa'")
            lista_comerciales = [fila[0] for fila in cursor.fetchall()]
            conn.close()

            with st.form("reasignar_puntos_form"):
                nuevos_comerciales = st.multiselect("Selecciona comerciales para reasignar los puntos liberados", options=lista_comerciales)
                reasignar_btn = st.form_submit_button("Confirmar reasignación")

                if reasignar_btn:
                    if not nuevos_comerciales:
                        st.warning("⚠️ No se ha seleccionado ningún comercial")
                    else:
                        try:
                            # Conectar a la base de datos
                            conn = get_db_connection()
                            cursor = conn.cursor()

                            # 1. Obtener los puntos de la tabla temporal
                            cursor.execute("""
                                                    SELECT apartment_id, provincia, municipio, poblacion, vial, numero, letra, cp, latitud, longitud, comercial, Contrato
                                                    FROM puntos_liberados_temp
                                                """)
                            puntos_liberados = cursor.fetchall()

                            if not puntos_liberados:
                                st.warning("⚠️ No hay puntos liberados para reasignar.")
                            else:
                                total_puntos = len(puntos_liberados)
                                n_comerciales = len(nuevos_comerciales)

                                # 2. Reparto round-robin
                                reparto = {com: [] for com in nuevos_comerciales}
                                for i, p in enumerate(puntos_liberados):
                                    reparto[nuevos_comerciales[i % n_comerciales]].append(p)

                                # 3. Insertar en la tabla principal
                                # 3. Insertar en la tabla principal con control de duplicados y trazabilidad
                                for comercial, puntos in reparto.items():
                                    for p in puntos:
                                        apartment_id = p[0]

                                        # Verificar si ya existe en la tabla comercial_rafa
                                        cursor.execute("SELECT comercial FROM comercial_rafa WHERE apartment_id = ?",
                                                       (apartment_id,))
                                        anterior = cursor.fetchone()

                                        if anterior:
                                            comercial_anterior = anterior[0]
                                            # Registrar en el log que se reasigna desde comercial_anterior hacia comercial
                                            detalle_log = (
                                                f"Reasignación de punto {apartment_id}: "
                                                f"{comercial_anterior} ➝ {comercial} "
                                                f"(zona {p[2]} - {p[3]})"
                                            )
                                            log_trazabilidad(st.session_state["username"], "Reasignación", detalle_log)

                                        # Insertar o reemplazar (sobrescribe si ya existe el apartment_id)
                                        cursor.execute("""
                                            INSERT OR REPLACE INTO comercial_rafa
                                            (apartment_id, provincia, municipio, poblacion, vial, numero, letra, cp, latitud, longitud, comercial, Contrato)
                                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                        """, (p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7], p[8], p[9], comercial,
                                              'Pendiente'))

                                # 4. Limpiar la tabla temporal
                                cursor.execute("DELETE FROM puntos_liberados_temp")

                                # Confirmar todas las operaciones
                                conn.commit()

                                resumen = "\n".join([f"👤 {com}: {len(puntos)} puntos" for com, puntos in reparto.items()])
                                # -------------------
                                # 🔔 Notificaciones
                                # -------------------
                                resumen = "\n".join(
                                    [f"👤 {com}: {len(puntos)} puntos" for com, puntos in reparto.items()])
                                total_puntos = sum(len(puntos) for puntos in reparto.values())

                                # Notificar a comerciales
                                for comercial, puntos in reparto.items():
                                    if puntos:
                                        cursor.execute("SELECT email FROM usuarios WHERE username = ?", (comercial,))
                                        resultado = cursor.fetchone()
                                        email_comercial = resultado[0] if resultado else None
                                        if email_comercial:
                                            descripcion = (
                                                f"📍 Ha recibido una nueva asignación.\n\n"
                                                f"📌 Zona: {puntos[0][2]} - {puntos[0][3]}\n"
                                                f"📊 Total puntos asignados: {len(puntos)}\n\n"
                                                "ℹ️ Los puntos ya están disponibles en su panel."
                                            )
                                            correo_asignacion_administracion2(email_comercial, puntos[0][2],
                                                                              puntos[0][3], descripcion)

                                # Notificar a administradores
                                cursor.execute("SELECT email FROM usuarios WHERE role = 'admin'")
                                emails_admins = [fila[0] for fila in cursor.fetchall()]

                                descripcion_admin = (
                                    f"📢 Reasignación de zona.\n\n"
                                    f"📌 Zona: {puntos[0][2]} - {puntos[0][3]}\n"
                                    f"📊 Total puntos reasignados: {total_puntos}\n"
                                    f"{resumen}\n\n"
                                    f"🕵️ Realizado por: {st.session_state['username']}"
                                )
                                for email_admin in emails_admins:
                                    correo_asignacion_administracion2(email_admin, puntos[0][2], puntos[0][3],
                                                                      descripcion_admin)
                                st.success(f"✅ Puntos liberados reasignados correctamente.\nTotal puntos: {total_puntos}\n{resumen}")

                                # Recargar la página para ver los cambios
                                st.rerun()

                        except Exception as e:
                            # En caso de error, revertir los cambios
                            if 'conn' in locals():
                                conn.rollback()
                                st.error(f"❌ Error al reasignar: {str(e)}")
                        finally:
                            # Cerrar la conexión
                            if 'conn' in locals():
                                conn.close()
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

                icon_name = 'home' if str(row.get('tipo_olt_rental', '')).strip().lower() == 'si' else 'info-sign'
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
            {% macro html(this, kwargs) %}
            <div style="
                position: fixed; 
                bottom: 00px; left: 0px; width: 190px; 
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
        icons=["geo-alt", "bar-chart-line", "check2-square", "database"],
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
    excluir_para_juan = ["nestor", "rafaela", "jose ramon", "roberto", "marian", "juan pablo"]
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
    elif username == "rafa sanz":
        # Rafa Sanz no ve a Juan Pablo
        assigned_zones = pd.read_sql(
            """
            SELECT DISTINCT municipio, poblacion, comercial
            FROM comercial_rafa
            WHERE LOWER(comercial) != 'juan pablo'
            """, conn)

        total_ofertas = pd.read_sql(
            """
            SELECT DISTINCT *
            FROM comercial_rafa
            WHERE LOWER(comercial) != 'juan pablo'
            """, conn)
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
        st.info(
            "ℹ️ Ofertas comerciales: Visualización del total de ofertas asignadas a cada comercial y su estado actual")
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
            comerciales_excluir = ["roberto", "jose ramon", "nestor", "rafaela", "rebe", "marian", "rafa sanz", "marian", "juan pablo"]
            viabilidades = viabilidades[~viabilidades['usuario'].isin(comerciales_excluir)]
        elif username.lower() == "rafa sanz":
            # Rafa Sanz no ve a Juan Pablo
            viabilidades = viabilidades[viabilidades['usuario'] != "juan pablo"]

        st.info(
            "ℹ️ Viabilidades: Visualización del total de viabilidades reportadas por cada comercial y su estado actual")
        st.dataframe(viabilidades, use_container_width=True)


    elif sub_seccion == "Datos totales":
        st.info("ℹ️ Visualización total de los datos")
        username = st.session_state.get("username", "").strip().lower()
        # Conectar a la base de datos y leer la tabla
        conn = get_db_connection()
        datos_uis = pd.read_sql(
            "SELECT apartment_id, address_id, provincia, municipio, poblacion, vial, numero, parcela_catastral, "
            "letra, cp, olt, cto, latitud, longitud, comercial FROM datos_uis", conn)
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
        options=["Viabilidades pendientes de confirmación", "Seguimiento de viabilidades", "Crear viabilidades"],
        icons=["exclamation-circle", "clipboard-check", "plus-circle"],  # Puedes cambiar iconos
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
        excluir_para_juan = ["nestor", "rafaela", "jose ramon", "roberto", "marian", "juan pablo"]

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
        elif username == "rafa sanz":
            # Rafa Sanz no ve a Juan Pablo
            query = """
                    SELECT id,
                           provincia, municipio, poblacion,
                           vial, numero, letra,
                           latitud, longitud,
                           serviciable,
                           usuario AS comercial_reporta,
                           confirmacion_rafa
                    FROM viabilidades
                    WHERE (confirmacion_rafa IS NULL OR confirmacion_rafa = '')
                      AND LOWER(usuario) != 'juan pablo'
                """
            df_viab = pd.read_sql(query, conn)
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
            comerciales_excluir = ["roberto", "jose ramon", "nestor", "rafaela", "marian", "rebe", "rafa sanz", "juan pablo"]
            viabilidades['usuario'] = viabilidades['usuario'].fillna("").str.strip().str.lower()
            viabilidades = viabilidades[~viabilidades['usuario'].isin(comerciales_excluir)]
        elif username == "rafa sanz":
            # Rafa Sanz no ve a Juan Pablo
            viabilidades = viabilidades[viabilidades['usuario'] != "juan pablo"]

        # 📋 Mostrar tabla resultante
        st.info("ℹ️ Listado completo de viabilidades y su estado actual.")
        st.dataframe(viabilidades, use_container_width=True)

    if sub_seccion == "Crear viabilidades":
        st.info("🆕 Aquí podrás crear nuevas viabilidades manualmente (en desarrollo).")
        st.markdown("""**Leyenda:**
                                 ⚫ Viabilidad ya existente
                                 🔵 Viabilidad nueva aún sin estudio
                                 🟢 Viabilidad serviciable y con Apartment ID ya asociado
                                 🔴 Viabilidad no serviciable
                                """)

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

                # ✅ Campo para seleccionar el comercial con lógica por usuario
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT username FROM usuarios ORDER BY username")
                todos_los_usuarios = [fila[0] for fila in cursor.fetchall()]
                conn.close()

                usuario_actual = st.session_state.get("username", "")
                rol_actual = st.session_state.get("role", "")

                # Lógica de filtrado personalizada
                if usuario_actual == "rafa sanz":  # comercial_jefe
                    lista_usuarios = ["roberto", "nestor", "rafaela", "jose ramon", "rafa sanz"]
                elif usuario_actual == "juan":  # otro gestor comercial
                    lista_usuarios = ["juan", "Comercial2", "Comercial3"]
                else:
                    # Comerciales normales solo se ven a sí mismos
                    lista_usuarios = [usuario_actual]

                # Verificar que existan en la tabla usuarios (por si algún nombre falta)
                lista_usuarios = [u for u in lista_usuarios if u in todos_los_usuarios]

                comercial = st.selectbox("🧑‍💼 Comercial responsable", options=lista_usuarios)
                submit = st.form_submit_button("Enviar Formulario")

                if submit:
                    # Generar ticket único
                    ticket = generar_ticket()

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
                        # st.session_state["username"],
                        comercial,
                        olt,  # nuevo campo
                        apartment_id  # nuevo campo
                    ))

                    st.success(f"✅ Viabilidad guardada correctamente.\n\n📌 **Ticket:** `{ticket}`")

                    # Resetear marcador para permitir nuevas viabilidades
                    st.session_state.viabilidad_marker = None
                    st.session_state.map_center = (43.463444, -3.790476)  # Vuelve a la ubicación inicial
                    st.rerun()

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

    conn.close()

    # Información de la viabilidad
    ticket_id = datos[10]  # 'ticket'
    #nombre_comercial = st.session_state.get("username")
    nombre_comercial = datos[13]  # 👈 el comercial elegido en el formulario
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

    # Mostrar mensaje de éxito en Streamlit
    st.success("✅ Los cambios para la viabilidad han sido guardados correctamente")

def obtener_viabilidades():
    conn = get_db_connection()
    cursor = conn.cursor()

    usuario_actual = st.session_state.get("username", "")
    rol_actual = st.session_state.get("role", "")

    if rol_actual == "admin":
        # Admin ve todas
        cursor.execute("""
            SELECT latitud, longitud, ticket, serviciable, apartment_id 
            FROM viabilidades
        """)

    elif usuario_actual == "rafa sanz":
        # Gestor comercial Rafa ve sus comerciales
        comerciales_permitidos = ("roberto", "nestor", "rafaela", "jose ramon", "rafa sanz")
        cursor.execute(f"""
            SELECT latitud, longitud, ticket, serviciable, apartment_id 
            FROM viabilidades
            WHERE usuario IN ({','.join(['?'] * len(comerciales_permitidos))})
        """, comerciales_permitidos)

    elif usuario_actual == "juan":
        # Gestor comercial Juan ve sus comerciales
        comerciales_permitidos = ("juan", "Comercial2", "Comercial3")
        cursor.execute(f"""
            SELECT latitud, longitud, ticket, serviciable, apartment_id 
            FROM viabilidades
            WHERE usuario IN ({','.join(['?'] * len(comerciales_permitidos))})
        """, comerciales_permitidos)

    else:
        # Comerciales normales solo sus propias viabilidades
        cursor.execute("""
            SELECT latitud, longitud, ticket, serviciable, apartment_id 
            FROM viabilidades
            WHERE usuario = ?
        """, (usuario_actual,))

    viabilidades = cursor.fetchall()
    conn.close()
    return viabilidades

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