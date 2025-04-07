import streamlit as st
import pandas as pd
import folium, io, sqlitecloud
from streamlit_folium import st_folium
from datetime import datetime
from modules.notificaciones import correo_asignacion_administracion, correo_desasignacion_administracion, correo_asignacion_administracion2, correo_desasignacion_administracion2
from folium.plugins import MarkerCluster
from streamlit_cookies_controller import CookieController  # Se importa localmente

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


def mapa_dashboard():
    """Panel de mapas optimizado para Rafa Sanz con asignación y desasignación de zonas comerciales"""
    controller = CookieController(key="cookies")
    st.sidebar.title("📍 Mapa de Ubicaciones")

    # Descripción de íconos y colores
    st.markdown("""
        **Iconos:**
        🏠 **Oferta con Proyecto:** Icono de casa azul.
        ℹ️ **Oferta sin Proyecto:** Icono de información azul.
        \n
        **Colores:**
        🟢 **Serviciable (Sí)**
        🔴 **No Serviciable (No)**
        🟠 **Oferta (Contrato: Sí)**
        ⚫ **Oferta (Contrato: No Interesado)**
        🔵 **No Visitado**
    """)

    # Panel lateral de bienvenida y cierre de sesión
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
                margin-bottom: 30px;
                text-align: center;
                margin-left: auto;
                margin-right: auto;
            }
        </style>
        <div class="user-circle">👤</div>
        <div>Rol: Gestor Comercial</div>
    """, unsafe_allow_html=True)
    st.sidebar.markdown(f"¡Bienvenido, **{st.session_state['username']}**!")

    with st.sidebar:
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
    st.sidebar.markdown("---")
    st.sidebar.markdown("Filtros generales UUIIs")

    # Filtros por fecha
    fecha_min = st.sidebar.date_input("Fecha mínima", value=pd.to_datetime("2024-01-01"))
    fecha_max = st.sidebar.date_input("Fecha máxima", value=pd.to_datetime("2030-12-31"))

    # Cargar datos con spinner
    with st.spinner("Cargando datos..."):
        datos_uis, comercial_rafa = cargar_datos()
        if datos_uis.empty:
            st.error("❌ No se encontraron datos para Rafa Sanz.")
            return

    # Convertir 'fecha' y filtrar por rango
    datos_uis['fecha'] = pd.to_datetime(datos_uis['fecha'], errors='coerce')
    fecha_min = pd.to_datetime(fecha_min)
    fecha_max = pd.to_datetime(fecha_max)
    datos_uis = datos_uis[(datos_uis["fecha"] >= fecha_min) & (datos_uis["fecha"] <= fecha_max)]

    # Filtro por provincia
    provincias = datos_uis['provincia'].unique()
    provincia_seleccionada = st.sidebar.selectbox("Selecciona una provincia", provincias)
    datos_uis = datos_uis[datos_uis["provincia"] == provincia_seleccionada]

    # Limpiar latitud y longitud
    datos_uis = datos_uis.dropna(subset=['latitud', 'longitud'])
    datos_uis['latitud'] = datos_uis['latitud'].astype(float)
    datos_uis['longitud'] = datos_uis['longitud'].astype(float)

    # --- Panel de asignación y desasignación (columna derecha) ---
    col1, col2 = st.columns([3, 3])
    with col2:
        st.subheader("Asignación de Zonas para Comerciales")
        accion = st.radio("Seleccione acción", ["Asignar Zona", "Desasignar Zona"], key="accion")

        if accion == "Asignar Zona":
            municipios = sorted(datos_uis['municipio'].dropna().unique())
            municipio_sel = st.selectbox("Seleccione Municipio", municipios, key="municipio_sel")
            poblacion_sel = None
            if municipio_sel:
                poblaciones = sorted(datos_uis[datos_uis['municipio'] == municipio_sel]['poblacion'].dropna().unique())
                poblacion_sel = st.selectbox("Seleccione Población", poblaciones, key="poblacion_sel")
            comercial_elegido = st.radio("Asignar a:", ["jose ramon", "rafaela"], key="comercial_elegido")

            if municipio_sel and poblacion_sel:
                # Verificar asignación previa
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
                            INSERT INTO comercial_rafa (apartment_id, provincia, municipio, poblacion, vial, numero, letra, cp, latitud, longitud, comercial, Contrato)
                            SELECT apartment_id, provincia, municipio, poblacion, vial, numero, letra, cp, latitud, longitud, ?, 'Pendiente'
                            FROM datos_uis
                            WHERE municipio = ? AND poblacion = ?
                        """, (comercial_elegido, municipio_sel, poblacion_sel))
                        conn.commit()

                        try:
                            cursor.execute("SELECT email FROM usuarios WHERE username = ?", (comercial_elegido,))
                            email_comercial = cursor.fetchone()
                            destinatario_comercial = email_comercial[
                                0] if email_comercial else "patricia@redytelcomputer.com"
                            cursor.execute("SELECT email FROM usuarios WHERE role = 'admin'")
                            emails_admins = [fila[0] for fila in cursor.fetchall()]
                            conn.close()

                            descripcion_asignacion = (
                                f"📍 Se le ha asignado la zona {municipio_sel} - {poblacion_sel}.<br><br>"
                                "💼 Ya puede comenzar a gestionar las tareas correspondientes en esta zona.<br>"
                                "🔑 Esté a cargo de todas las actividades y gestiones.<br>"
                                "ℹ️ Revise su panel de usuario para más detalles.<br><br>"
                                "🚨 Si tiene dudas, contacte con administración.<br>¡Gracias!"
                            )

                            descripcion_admin = (
                                f"📢 Nueva asignación de zona.<br><br>"
                                f"📌 Zona Asignada: {municipio_sel} - {poblacion_sel}<br>"
                                f"👤 Asignado a: {comercial_elegido}<br>"
                                f"🕵️ Asignado por: {st.session_state['username']}<br><br>"
                                "ℹ️ Revise los detalles en la plataforma.<br>"
                                "⚡ Realice cambios desde administración si es necesario.<br>"
                                "📞 Contacte con el equipo ante cualquier duda.<br>🔧 Gracias por su gestión."
                            )

                            # Enviar notificaciones
                            correo_asignacion_administracion(destinatario_comercial, municipio_sel, poblacion_sel,
                                                             descripcion_asignacion)
                            for email_admin in emails_admins:
                                correo_asignacion_administracion2(email_admin, municipio_sel, poblacion_sel,
                                                                  descripcion_admin)

                            st.success("✅ Zona asignada correctamente y notificaciones enviadas.")
                            st.info(f"📧 Se notificó a {comercial_elegido} y a los administradores.")

                            log_trazabilidad(st.session_state["username"], "Asignación",
                                             f"Asignó zona {municipio_sel} - {poblacion_sel} a {comercial_elegido}")
                        except Exception as e:
                            st.error(f"❌ Error al enviar la notificación: {e}")
                        finally:
                            conn.close()

        elif accion == "Desasignar Zona":
            conn = get_db_connection()
            assigned_zones = pd.read_sql("SELECT DISTINCT municipio, poblacion, comercial FROM comercial_rafa", conn)
            conn.close()
            if assigned_zones.empty:
                st.warning("No hay zonas asignadas para desasignar.")
            else:
                assigned_zones['zona'] = assigned_zones['municipio'] + " - " + assigned_zones['poblacion']
                zonas_list = sorted(assigned_zones['zona'].unique())
                zona_seleccionada = st.selectbox("Seleccione la zona asignada a desasignar", zonas_list,
                                                 key="zona_seleccionada")
                if zona_seleccionada:
                    municipio_sel, poblacion_sel = zona_seleccionada.split(" - ")
                    if st.button("Desasignar Zona"):
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        cursor.execute("SELECT comercial FROM comercial_rafa WHERE municipio = ? AND poblacion = ?",
                                       (municipio_sel, poblacion_sel))
                        comercial_asignado = cursor.fetchone()[0]
                        conn.close()

                        # Borrar asignación
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM comercial_rafa WHERE municipio = ? AND poblacion = ?",
                                       (municipio_sel, poblacion_sel))
                        conn.commit()
                        conn.close()

                        try:
                            conn = get_db_connection()
                            cursor = conn.cursor()
                            cursor.execute("SELECT email FROM usuarios WHERE username = ?", (comercial_asignado,))
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
                                "ℹ️ Revise su asignación actualizada en el sistema.<br><br>"
                                "📞 Si tiene dudas, contacte con administración.<br>"
                                "💬 Estamos aquí para ayudarle."
                            )

                            descripcion_admin = (
                                f"📢 Se ha realizado una desasignación de zona.<br><br>"
                                f"📌 Zona Desasignada: {municipio_sel} - {poblacion_sel}<br>"
                                f"👤 Comercial afectado: {comercial_asignado}<br>"
                                f"🕵️ Desasignado por: {st.session_state['username']}<br><br>"
                                "ℹ️ Revise los detalles en la plataforma.<br>"
                                "⚡ Ajuste la asignación desde administración si es necesario.<br>"
                                "🔧 Gracias por su gestión."
                            )

                            # Enviar notificaciones
                            correo_desasignacion_administracion(destinatario_comercial, municipio_sel, poblacion_sel,
                                                                descripcion_desasignacion)
                            for email_admin in emails_admins:
                                correo_desasignacion_administracion2(email_admin, municipio_sel, poblacion_sel,
                                                                     descripcion_admin)

                            st.success("✅ Zona desasignada correctamente y notificaciones enviadas.")
                            st.info(f"📧 Se notificó a {comercial_asignado} y a los administradores.")

                            log_trazabilidad(st.session_state["username"], "Desasignación",
                                             f"Desasignó zona {municipio_sel} - {poblacion_sel}")
                        except Exception as e:
                            st.error(f"❌ Error al enviar la notificación: {e}")

        # Mostrar tabla de zonas asignadas en el panel de asignación
        conn = get_db_connection()
        assigned_zones = pd.read_sql("SELECT DISTINCT municipio, poblacion, comercial FROM comercial_rafa", conn)
        conn.close()

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
            marker_cluster = MarkerCluster(disableClusteringAtZoom=16, maxClusterRadius=50,
                                           spiderfyOnMaxZoom=True).add_to(m)

            for _, row in datos_uis.iterrows():
                lat, lon = row['latitud'], row['longitud']
                apartment_id = row['apartment_id']
                vial = row.get('vial', 'No Disponible')
                numero = row.get('numero', 'No Disponible')
                letra = row.get('letra', 'No Disponible')

                oferta = comercial_rafa[comercial_rafa['apartment_id'] == apartment_id]
                color = 'blue'
                if str(row.get('serviciable', '')).strip().lower() == "sí":
                    color = 'green'
                elif not oferta.empty:
                    oferta_serviciable = str(oferta.iloc[0].get('serviciable', '')).strip().lower()
                    contrato = str(oferta.iloc[0].get('Contrato', '')).strip().lower()
                    if oferta_serviciable == "no":
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
            st_folium(m, height=500, width=700)

    # Mostrar tabla de zonas asignadas y total de ofertas
    conn = get_db_connection()
    assigned_zones = pd.read_sql("SELECT DISTINCT municipio, poblacion, comercial FROM comercial_rafa", conn)
    total_ofertas = pd.read_sql("SELECT DISTINCT * FROM comercial_rafa", conn)
    conn.close()
    if not assigned_zones.empty:
        st.info("ℹ️ Zonas ya asignadas:")
        st.dataframe(assigned_zones, use_container_width=True)
    log_trazabilidad(st.session_state["username"], "Visualización de mapa", "Usuario visualizó el mapa de Rafa Sanz.")
    st.info("ℹ️ Ofertas comerciales: Visualización del total de ofertas asignadas a cada comercial y su estado actual")
    st.dataframe(total_ofertas, use_container_width=True)

    # Sección de descarga de datos
    st.subheader("Descargar Datos")
    descarga_opcion = st.radio("Formato de descarga:", ["CSV", "Excel"])
    if descarga_opcion == "CSV":
        log_trazabilidad(st.session_state["username"], "Descarga de datos", "Usuario descargó datos en CSV.")
        st.download_button(
            label="Descargar como CSV",
            data=datos_uis.to_csv(index=False).encode(),
            file_name="datos_rafa_sanz.csv",
            mime="text/csv"
        )
    elif descarga_opcion == "Excel":
        log_trazabilidad(st.session_state["username"], "Descarga de datos", "Usuario descargó datos en Excel.")
        with io.BytesIO() as towrite:
            with pd.ExcelWriter(towrite, engine='xlsxwriter') as writer:
                datos_uis.to_excel(writer, index=False, sheet_name="Datos Rafa Sanz")
            towrite.seek(0)
            st.download_button(
                label="Descargar como Excel",
                data=towrite,
                file_name="datos_rafa_sanz.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
    st.info("Dependiendo del tamaño de los datos, la descarga puede tardar algunos segundos.")
if __name__ == "__main__":
    mapa_dashboard()
