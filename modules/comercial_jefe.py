import streamlit as st
import pandas as pd
import sqlite3
import folium
from streamlit_folium import st_folium
from datetime import datetime
import io
from modules.notificaciones import correo_asignacion_administracion, correo_desasignacion_administracion, correo_asignacion_administracion2, correo_desasignacion_administracion2
from folium.plugins import MarkerCluster
from streamlit_cookies_controller import CookieController  # Se importa localmente

cookie_name = "my_app"

def log_trazabilidad(usuario, accion, detalles):
    """ Inserta un registro en la tabla de trazabilidad """
    conn = sqlite3.connect("data/usuarios.db")
    cursor = conn.cursor()
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT INTO trazabilidad (usuario_id, accion, detalles, fecha)
        VALUES (?, ?, ?, ?)
    """, (usuario, accion, detalles, fecha))
    conn.commit()
    conn.close()


@st.cache_data
def cargar_datos():
    """Carga los datos de las tablas de base de datos con caché"""
    conn = sqlite3.connect("data/usuarios.db")
    # Cargar datos de la tabla datos_uis (incluimos municipio y población)
    query_datos_uis = """
        SELECT apartment_id, latitud, longitud, fecha, provincia, municipio, vial, numero, letra, poblacion, cto_con_proyecto, serviciable 
        FROM datos_uis 
        WHERE comercial = 'RAFA SANZ'
    """
    datos_uis = pd.read_sql(query_datos_uis, conn)
    # Cargar datos de la tabla comercial_rafa (incluimos Contrato, municipio, población y comercial)
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
    # Descripción de los íconos
    st.markdown("""
        **Iconos:**
        🏠 **Oferta con Proyecto:** Representado por un icono de casa azul.
        ℹ️ **Oferta sin Proyecto:** Representado por un icono de información azul.
        \n
        **Colores:**
        🟢 **Serviciable (Sí)**
        🔴 **No Serviciable (No)**
        🟠 **Oferta (Contrato: Sí)**
        ⚫ **Oferta (Contrato: No Interesado)**
        🔵 **No Visitado**
    """)

    # Barra lateral con bienvenida y botón de cerrar sesión
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

            # Eliminar las cookies del session_id, username y role para esta sesión
            if controller.get(f'{cookie_name}_session_id'):
                controller.set(f'{cookie_name}_session_id', '', max_age=0, path='/')
            if controller.get(f'{cookie_name}_username'):
                controller.set(f'{cookie_name}_username', '', max_age=0, path='/')
            if controller.get(f'{cookie_name}_role'):
                controller.set(f'{cookie_name}_role', '', max_age=0, path='/')

            # Reiniciar el estado de sesión
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

    # Cargar datos
    with st.spinner("Cargando datos..."):
        datos_uis, comercial_rafa = cargar_datos()
        if datos_uis.empty:
            st.error("❌ No se encontraron datos para Rafa Sanz.")
            return

    # Convertir 'fecha' a datetime y filtrar
    datos_uis['fecha'] = pd.to_datetime(datos_uis['fecha'], errors='coerce')
    fecha_min = pd.to_datetime(fecha_min)
    fecha_max = pd.to_datetime(fecha_max)
    datos_uis = datos_uis[(datos_uis["fecha"] >= fecha_min) & (datos_uis["fecha"] <= fecha_max)]

    # Filtro por provincia
    provincias = datos_uis['provincia'].unique()
    provincia_seleccionada = st.sidebar.selectbox("Selecciona una provincia", provincias)
    datos_uis = datos_uis[datos_uis["provincia"] == provincia_seleccionada]

    # Limpiar datos de latitud y longitud
    datos_uis = datos_uis.dropna(subset=['latitud', 'longitud'])
    datos_uis['latitud'] = datos_uis['latitud'].astype(float)
    datos_uis['longitud'] = datos_uis['longitud'].astype(float)

    # --- Crear columnas: la columna derecha tendrá el panel de asignación ---
    col1, col2 = st.columns([3, 3])
    with col2:
        st.subheader("Asignación de Zonas para Comerciales")
        # Seleccionar la acción a realizar
        accion = st.radio("Seleccione acción", ["Asignar Zona", "Desasignar Zona"], key="accion")
        if accion == "Asignar Zona":
            municipios = sorted(datos_uis['municipio'].dropna().unique())
            municipio_sel = st.selectbox("Seleccione Municipio", municipios, key="municipio_sel")
            poblacion_sel = None
            if municipio_sel:
                poblaciones = sorted(datos_uis[datos_uis['municipio'] == municipio_sel]['poblacion'].dropna().unique())
                poblacion_sel = st.selectbox("Seleccione Población", poblaciones, key="poblacion_sel")
            comercial_elegido = st.radio("Asignar a:", ["comercial_rafa1", "comercial_rafa2"], key="comercial_elegido")

            if municipio_sel and poblacion_sel:
                conn = sqlite3.connect("data/usuarios.db")
                conn = sqlite3.connect("data/usuarios.db")
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM comercial_rafa WHERE municipio = ? AND poblacion = ?",
                               (municipio_sel, poblacion_sel))
                count_assigned = cursor.fetchone()[0]
                conn.close()

                if count_assigned > 0:
                    st.warning("🚫 Esta zona ya ha sido asignada.")
                else:
                    if st.button("Asignar Zona"):
                        conn = sqlite3.connect("data/usuarios.db")
                        cursor = conn.cursor()
                        cursor.execute("""
                            INSERT INTO comercial_rafa (apartment_id, provincia, municipio, poblacion, vial, numero, letra, cp, latitud, longitud, comercial, Contrato)
                            SELECT apartment_id, provincia, municipio, poblacion, vial, numero, letra, cp, latitud, longitud, ?, 'Pendiente'
                            FROM datos_uis
                            WHERE municipio = ? AND poblacion = ?
                        """, (comercial_elegido, municipio_sel, poblacion_sel))
                        conn.commit()

                        try:
                            # Obtener email del comercial asignado
                            cursor.execute("SELECT email FROM usuarios WHERE username = ?", (comercial_elegido,))
                            email_comercial = cursor.fetchone()

                            destinatario_comercial = email_comercial[0] if email_comercial else "patricia@redytelcomputer.com"

                            # Obtener emails de administradores
                            cursor.execute("SELECT email FROM usuarios WHERE role = 'admin'")
                            emails_admins = [fila[0] for fila in cursor.fetchall()]

                            conn.close()

                            # **Mensaje para el comercial asignado**
                            descripcion_asignacion = (
                                f"📍 Le informamos que se le ha asignado la zona {municipio_sel} - {poblacion_sel}.<br><br>"
                                f"💼 Ya puede comenzar a gestionar las tareas correspondientes en esta zona.<br>"
                                f"🔑 Esta asignación implica que ahora estará a cargo de todas las actividades y gestiones.<br>"
                                f"ℹ️ Revise su panel de usuario para conocer más detalles.<br><br>"
                                f"🚨 Si tiene alguna duda, contacte con administración.<br>"
                                f"¡Gracias!"
                            )

                            # **Mensaje para los administradores**
                            descripcion_admin = (
                                f"📢 Se ha realizado una nueva asignación de zona.<br><br>"
                                f"📌 <strong>Zona Asignada:</strong> {municipio_sel} - {poblacion_sel}<br>"
                                f"👤 <strong>Asignado a:</strong> {comercial_elegido}<br>"
                                f"🕵️ <strong>Asignado por:</strong> {st.session_state['username']}<br><br>"
                                f"ℹ️ Revise los detalles en la plataforma.<br>"
                                f"⚡ Si necesita realizar algún cambio, puede hacerlo desde administración.<br>"
                                f"📞 Contacte con el equipo si hay dudas.<br>"
                                f"🔧 Gracias por su gestión."
                            )

                            # **Enviar correos**
                            correo_asignacion_administracion(destinatario_comercial, municipio_sel, poblacion_sel,
                                                             descripcion_asignacion)

                            for email_admin in emails_admins:
                                correo_asignacion_administracion2(email_admin, municipio_sel, poblacion_sel,
                                                                 descripcion_admin)

                            # **Mensajes en Streamlit**
                            st.success("✅ Zona asignada correctamente y notificaciones enviadas.")
                            st.info(
                                f"📧 Se ha notificado a {comercial_elegido} y a los administradores sobre la asignación.")

                            # **Registrar trazabilidad**
                            log_trazabilidad(st.session_state["username"], "Asignación",
                                             f"Asignó zona {municipio_sel} - {poblacion_sel} a {comercial_elegido}")

                        except Exception as e:
                            st.error(f"❌ Error al enviar la notificación: {e}")
                        finally:
                            conn.close()

        elif accion == "Desasignar Zona":
            conn = sqlite3.connect("data/usuarios.db")
            assigned_zones = pd.read_sql("SELECT DISTINCT municipio, poblacion, comercial FROM comercial_rafa", conn)
            conn.close()
            if assigned_zones.empty:
                st.warning("No hay zonas asignadas para desasignar.")
            else:
                assigned_zones['zona'] = assigned_zones['municipio'] + " - " + assigned_zones['poblacion']
                zonas_list = sorted(assigned_zones['zona'].unique())
                zona_seleccionada = st.selectbox("Seleccione la zona asignada a desasignar", zonas_list, key="zona_seleccionada")
                if zona_seleccionada:
                    municipio_sel, poblacion_sel = zona_seleccionada.split(" - ")
                    if st.button("Desasignar Zona"):
                        # Obtener el comercial asignado a la zona
                        conn = sqlite3.connect("data/usuarios.db")
                        cursor = conn.cursor()
                        cursor.execute("SELECT comercial FROM comercial_rafa WHERE municipio = ? AND poblacion = ?",
                                       (municipio_sel, poblacion_sel))
                        comercial_asignado = cursor.fetchone()[0]
                        conn.close()

                        # Desasignar la zona
                        conn = sqlite3.connect("data/usuarios.db")
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM comercial_rafa WHERE municipio = ? AND poblacion = ?",
                                       (municipio_sel, poblacion_sel))
                        conn.commit()
                        conn.close()

                        try:
                            # Conectar a la base de datos (usuarios.db)
                            conn = sqlite3.connect("data/usuarios.db")
                            cursor = conn.cursor()

                            # Obtener email del comercial desasignado
                            cursor.execute("SELECT email FROM usuarios WHERE username = ?", (comercial_asignado,))
                            email_comercial = cursor.fetchone()
                            destinatario_comercial = email_comercial[0] if email_comercial else "patricia@redytelcomputer.com"

                            # Obtener emails de los administradores
                            cursor.execute("SELECT email FROM usuarios WHERE role = 'admin'")
                            emails_admins = [fila[0] for fila in cursor.fetchall()]

                            conn.close()

                            # **Mensaje para el comercial desasignado**
                            descripcion_desasignacion = (
                                f"📍 Se le ha desasignado la zona {municipio_sel} - {poblacion_sel}.<br>"
                                f"🔄 Este cambio puede deberse a una reestructuración o ajuste en las zonas asignadas.<br>"
                                f"⚠️ Ya no estará a cargo de las actividades y tareas correspondientes a esta zona.<br>"
                                f"ℹ️ Revise su asignación actualizada en el sistema.<br><br>"
                                f"📞 Si tiene dudas, contacte con administración.<br>"
                                f"💬 Estamos aquí para ayudarle con la transición."
                            )

                            # **Mensaje para los administradores**
                            descripcion_admin = (
                                f"📢 Se ha realizado una desasignación de zona.<br><br>"
                                f"📌 <strong>Zona Desasignada:</strong> {municipio_sel} - {poblacion_sel}<br>"
                                f"👤 <strong>Comercial afectado:</strong> {comercial_asignado}<br>"
                                f"🕵️ <strong>Desasignado por:</strong> {st.session_state['username']}<br><br>"
                                f"ℹ️ Revise los detalles en la plataforma.<br>"
                                f"⚡ Si necesita realizar algún ajuste, puede hacerlo desde administración.<br>"
                                f"🔧 Gracias por su gestión."
                            )

                            # **Enviar correos**
                            correo_desasignacion_administracion(destinatario_comercial, municipio_sel, poblacion_sel,
                                                                descripcion_desasignacion)

                            for email_admin in emails_admins:
                                correo_desasignacion_administracion2(email_admin, municipio_sel, poblacion_sel,
                                                                    descripcion_admin)

                            # **Mensajes en Streamlit**
                            st.success("✅ Zona desasignada correctamente y notificaciones enviadas.")
                            st.info(
                                f"📧 Se ha notificado a {comercial_asignado} y a los administradores sobre la desasignación.")

                            # **Registrar trazabilidad**
                            log_trazabilidad(st.session_state["username"], "Desasignación",
                                             f"Desasignó zona {municipio_sel} - {poblacion_sel}")

                        except Exception as e:
                            st.error(f"❌ Error al enviar la notificación: {e}")

        # Mostrar la tabla de zonas asignadas (dentro del panel de asignación)
        conn = sqlite3.connect("data/usuarios.db")
        assigned_zones = pd.read_sql("SELECT DISTINCT municipio, poblacion, comercial FROM comercial_rafa", conn)
        conn.close()

    # --- Generar el mapa en la columna izquierda, usando los valores de asignación para centrar ---
    with col1:
        # Generar el mapa con spinner
        with col1:
            # Dentro de la sección donde generas el mapa...
            with st.spinner("⏳ Cargando mapa... (Puede tardar según la cantidad de puntos)"):
                # Definir la ubicación inicial en base a los datos disponibles
                center = [datos_uis.iloc[0]['latitud'], datos_uis.iloc[0]['longitud']]
                zoom_start = 12

                # Si el usuario ha filtrado por municipio/población, centrar el mapa en esa zona
                if "municipio_sel" in st.session_state and "poblacion_sel" in st.session_state:
                    zone_data = datos_uis[
                        (datos_uis["municipio"] == st.session_state["municipio_sel"]) &
                        (datos_uis["poblacion"] == st.session_state["poblacion_sel"])
                        ]
                    if not zone_data.empty:
                        center = [zone_data["latitud"].mean(), zone_data["longitud"].mean()]
                        zoom_start = 14

                m = folium.Map(
                    location=center,
                    zoom_start=zoom_start,
                    tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
                    attr="Google"
                )

                # Agrupar marcadores
                marker_cluster = MarkerCluster(
                    disableClusteringAtZoom=16,
                    maxClusterRadius=50,
                    spiderfyOnMaxZoom=True
                ).add_to(m)

                # Definir colores y asignarlos correctamente
                for _, row in datos_uis.iterrows():
                    lat = row['latitud']
                    lon = row['longitud']
                    apartment_id = row['apartment_id']
                    vial = row.get('vial', 'No Disponible')
                    numero = row.get('numero', 'No Disponible')
                    letra = row.get('letra', 'No Disponible')

                    # Buscar en comercial_rafa
                    oferta = comercial_rafa[comercial_rafa['apartment_id'] == apartment_id]

                    # Color por defecto
                    color = 'blue'

                    # Revisar 'serviciable' primero
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

                    # Icono según cto_con_proyecto
                    icon_name = 'home' if str(row.get('cto_con_proyecto', '')).strip().lower() == 'si' else 'info-sign'

                    # Popup con información
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

                # Mostrar el mapa en Streamlit
                st_folium(m, height=500, width=700)

    # Mostrar la tabla de zonas asignadas ocupando el ancho completo, justo debajo de las columnas
    conn = sqlite3.connect("data/usuarios.db")
    assigned_zones = pd.read_sql("SELECT DISTINCT municipio, poblacion, comercial FROM comercial_rafa", conn)
    total_ofertas = pd.read_sql("SELECT DISTINCT * FROM comercial_rafa", conn)
    conn.close()
    if not assigned_zones.empty:
        st.info("ℹ️ Zonas ya asignadas:")
        st.dataframe(assigned_zones, use_container_width=True)

    # Registro de trazabilidad para la visualización del mapa
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
