import streamlit as st
import pandas as pd
import folium, io, sqlitecloud
from streamlit_folium import st_folium
from datetime import datetime
from modules.notificaciones import correo_asignacion_administracion, correo_desasignacion_administracion, correo_asignacion_administracion2, correo_desasignacion_administracion2
from folium.plugins import MarkerCluster
from streamlit_cookies_controller import CookieController  # Se importa localmente
from datetime import datetime

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
        🟢 **Serviciable (Sí - Finalizado)**
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
            comerciales_disponibles = ["jose ramon", "rafaela", "nestor", "roberto"]
            comerciales_seleccionados = st.multiselect("Asignar equitativamente a:", comerciales_disponibles,
                                                       key="comerciales_seleccionados")

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
                    if municipio_sel and poblacion_sel and comerciales_seleccionados:
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

                                # Obtener todos los puntos por esa población
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

                                    # Enviar notificaciones (mismo sistema, ahora por cada comercial)
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
                # Convertir a string y llenar NaN antes de concatenar
                assigned_zones['municipio'] = assigned_zones['municipio'].fillna('').astype(str)
                assigned_zones['poblacion'] = assigned_zones['poblacion'].fillna('').astype(str)

                # Filtrar zonas completas
                assigned_zones = assigned_zones[
                    (assigned_zones['municipio'] != '') & (assigned_zones['poblacion'] != '')]
                assigned_zones['zona'] = assigned_zones['municipio'] + " - " + assigned_zones['poblacion']
                zonas_list = sorted(assigned_zones['zona'].unique())
                zona_seleccionada = st.selectbox("Seleccione la zona asignada a desasignar", zonas_list,
                                                 key="zona_seleccionada")

                if zona_seleccionada:
                    municipio_sel, poblacion_sel = zona_seleccionada.split(" - ")

                    # Obtener comerciales asignados a esa zona
                    conn = get_db_connection()
                    query = """
                                SELECT DISTINCT comercial FROM comercial_rafa 
                                WHERE municipio = ? AND poblacion = ?
                            """
                    comerciales_asignados = pd.read_sql(query, conn, params=(municipio_sel, poblacion_sel))
                    conn.close()

                    if comerciales_asignados.empty:
                        st.warning("No hay comerciales asignados a esta zona.")
                    else:
                        comercial_a_eliminar = st.selectbox("Seleccione el comercial a desasignar",
                                                            comerciales_asignados["comercial"].tolist())
                        if st.button("Desasignar Comercial de Zona"):
                            conn = get_db_connection()
                            cursor = conn.cursor()
                            cursor.execute("""
                                        DELETE FROM comercial_rafa 
                                        WHERE municipio = ? AND poblacion = ? AND comercial = ?
                                    """, (municipio_sel, poblacion_sel, comercial_a_eliminar))
                            conn.commit()

                            # Buscar correo del comercial

                            cursor.execute("SELECT email FROM usuarios WHERE username = ?", (comercial_a_eliminar,))
                            email_comercial = cursor.fetchone()
                            destinatario_comercial = email_comercial[
                                0] if email_comercial else "patricia@redytelcomputer.com"

                            # Correos admin
                            cursor.execute("SELECT email FROM usuarios WHERE role = 'admin'")
                            emails_admins = [fila[0] for fila in cursor.fetchall()]
                            conn.close()

                            # Notificaciones
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
                                f"👤 Comercial afectado: {comercial_a_eliminar}<br>"
                                f"🕵️ Desasignado por: {st.session_state['username']}<br><br>"
                                "ℹ️ Revise los detalles en la plataforma.<br>"
                                "⚡ Ajuste la asignación desde administración si es necesario.<br>"
                                "🔧 Gracias por su gestión."
                            )
                            correo_desasignacion_administracion(destinatario_comercial, municipio_sel, poblacion_sel,
                                                                descripcion_desasignacion)
                            for email_admin in emails_admins:
                                correo_desasignacion_administracion2(email_admin, municipio_sel, poblacion_sel,
                                                                     descripcion_admin)
                            st.success(f"✅ Se desasignó la zona a {comercial_a_eliminar} correctamente.")
                            st.info(f"📧 Se notificó a {comercial_a_eliminar} y a los administradores.")
                            log_trazabilidad(st.session_state["username"], "Desasignación",

                                             f"Desasignó zona {municipio_sel} - {poblacion_sel} del comercial {comercial_a_eliminar}")

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

                # Valor de serviciable desde datos_uis
                serviciable_val = str(row.get('serviciable', '')).strip().lower()

                oferta = comercial_rafa[comercial_rafa['apartment_id'] == apartment_id]
                color = 'blue'

                if serviciable_val == "si":
                    color = 'green'  # 🟢 Serviciable desde datos_uis
                elif serviciable_val == "no":
                    color = 'red'  # 🔴 No serviciable desde datos_uis
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

    # Obtener contratos activos desde seguimiento_contratos
    query_contratos = """
        SELECT apartment_id
        FROM seguimiento_contratos
        WHERE TRIM(LOWER(estado)) = 'finalizado'
    """
    df_contratos = pd.read_sql(query_contratos, conn)

    conn.close()

    # Agregar columna 'Contrato_Activo' a total_ofertas
    total_ofertas['Contrato_Activo'] = total_ofertas['apartment_id'].isin(df_contratos['apartment_id']).map(
        {True: '✅ Activo', False: '❌ No Activo'})

    if not assigned_zones.empty:
        st.info("ℹ️ Zonas ya asignadas:")
        st.dataframe(assigned_zones, use_container_width=True)
    log_trazabilidad(st.session_state["username"], "Visualización de mapa", "Usuario visualizó el mapa de Rafa Sanz.")
    st.info("ℹ️ Ofertas comerciales: Visualización del total de ofertas asignadas a cada comercial y su estado actual")
    st.dataframe(total_ofertas, use_container_width=True)

    # Mostrar tabla de viabilidades
    conn = get_db_connection()
    viabilidades = pd.read_sql("""
        SELECT DISTINCT 
            id, latitud, longitud, provincia, municipio, poblacion, 
            vial, numero, letra, cp, comentario, olt, serviciable, 
            comentarios_comercial, fecha_viabilidad, ticket, apartment_id, 
            nombre_cliente, telefono, usuario
        FROM viabilidades 
        WHERE usuario = 'jose ramon' OR usuario = 'rafaela' OR usuario = 'nestor' OR usuario = 'roberto'
    """, conn)
    conn.close()
    st.info("ℹ️ Viabilidades: Visualización del total de viabilidades y su estado actual")
    st.dataframe(viabilidades, use_container_width=True)

    # Sección de descarga de datos
    st.subheader("Descargar Datos")

    # Opciones de descarga
    dataset_opcion = st.selectbox("¿Qué deseas descargar?", ["Datos", "Ofertas asignadas", "Viabilidades", "Todo"])
    formato_opcion = st.radio("Formato de descarga:", ["CSV", "Excel"])
    nombre_base = st.text_input("Nombre base del archivo:", "rafa_sanz_datos")

    # Fecha para incluir en el nombre del archivo
    fecha_actual = datetime.now().strftime("%Y-%m-%d")
    nombre_archivo_final = f"{nombre_base}_{fecha_actual}"

    # Funciones auxiliares
    def descargar_csv(df, nombre_archivo):
        st.download_button(
            label=f"Descargar {nombre_archivo} como CSV",
            data=df.to_csv(index=False).encode(),
            file_name=f"{nombre_archivo}.csv",
            mime="text/csv"
        )

    def descargar_excel(dfs_dict, nombre_archivo):
        with io.BytesIO() as output:
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                for sheet_name, df in dfs_dict.items():
                    df.to_excel(writer, sheet_name=sheet_name[:31], index=False)
            output.seek(0)
            st.download_button(
                label=f"Descargar {nombre_archivo} como Excel",
                data=output,
                file_name=f"{nombre_archivo}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    # Mostrar botón según selección
    if dataset_opcion == "Datos":
        log_trazabilidad(st.session_state["username"], "Descarga de datos", "Usuario descargó los datos.")
        if formato_opcion == "CSV":
            descargar_csv(datos_uis, nombre_archivo_final)
        else:
            descargar_excel({"Datos Rafa Sanz": datos_uis}, nombre_archivo_final)

    elif dataset_opcion == "Ofertas asignadas":
        log_trazabilidad(st.session_state["username"], "Descarga de datos", "Usuario descargó ofertas asignadas.")
        if formato_opcion == "CSV":
            descargar_csv(total_ofertas, nombre_archivo_final)
        else:
            descargar_excel({"Ofertas Asignadas": total_ofertas}, nombre_archivo_final)

    elif dataset_opcion == "Viabilidades":
        log_trazabilidad(st.session_state["username"], "Descarga de datos", "Usuario descargó viabilidades.")
        if formato_opcion == "CSV":
            descargar_csv(viabilidades, nombre_archivo_final)
        else:
            descargar_excel({"Viabilidades": viabilidades}, nombre_archivo_final)

    elif dataset_opcion == "Todo":
        log_trazabilidad(st.session_state["username"], "Descarga de datos", "Usuario descargó todos los datos.")
        if formato_opcion == "Excel":
            descargar_excel({
                "Datos Rafa Sanz": datos_uis,
                "Ofertas Asignadas": total_ofertas,
                "Viabilidades": viabilidades
            }, nombre_archivo_final)
        else:
            st.warning("⚠️ Para descargar todo junto, selecciona el formato Excel.")
    st.info("Dependiendo del tamaño de los datos, la descarga puede tardar algunos segundos.")
if __name__ == "__main__":
    mapa_dashboard()
