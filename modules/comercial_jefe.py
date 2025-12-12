import streamlit as st
import pandas as pd
import folium, io, sqlitecloud
from streamlit_folium import st_folium
from streamlit_option_menu import option_menu

from modules.notificaciones import correo_asignacion_administracion, correo_desasignacion_administracion, \
    correo_asignacion_administracion2, correo_reasignacion_saliente, \
    correo_reasignacion_entrante, correo_confirmacion_viab_admin, correo_viabilidad_comercial, \
    notificar_creacion_ticket, notificar_actualizacion_ticket
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
def cargar_datos(usuario=None):
    """Carga los datos de las tablas con caché"""
    conn = get_db_connection()

    # Usar el usuario proporcionado o el de la sesión
    if usuario is None:
        username = st.session_state.get("username", "").strip()
    else:
        username = usuario

    # Construir query dinámica según el usuario
    if username:
        query_datos_uis = """
            SELECT apartment_id, latitud, longitud, fecha, provincia, municipio, vial, numero, letra, poblacion, tipo_olt_rental, serviciable 
            FROM datos_uis 
            WHERE comercial = ?
        """
        datos_uis = pd.read_sql(query_datos_uis, conn, params=(username,))
    else:
        # Si no hay usuario, cargar todos los datos (para compatibilidad)
        query_datos_uis = """
            SELECT apartment_id, latitud, longitud, fecha, provincia, municipio, vial, numero, letra, poblacion, tipo_olt_rental, serviciable 
            FROM datos_uis
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
        st.toast(f"Error cargando total_ofertas: {e}")
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
        st.toast(f"Error cargando total_ofertas: {e}")
        return pd.DataFrame()

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
            options=["Mapa Asignaciones", "Viabilidades", "Ver Datos", "Buscar Coordenadas", "Descargar Datos","Soporte"],
            icons=["globe", "check-circle", "bar-chart", "compass", "download","ticket"],
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
            st.toast("✅ Has cerrado sesión correctamente. Redirigiendo al login...")
            st.rerun()

    # Lógica principal según la opción
    if opcion == "Mapa Asignaciones":
        mostrar_ultimo_anuncio()
        mostrar_mapa_de_asignaciones()
    elif opcion == "Viabilidades":
        mostrar_viabilidades()
    elif opcion == "Ver Datos":
        mostrar_descarga_datos()
    elif opcion == "Buscar Coordenadas":
        mostrar_coordenadas()
    elif opcion == "Descargar Datos":
        download_datos(datos_uis, total_ofertas, viabilidades)
    elif opcion == "Soporte":
        mostrar_soporte_gestor_comercial()


def mostrar_soporte_gestor_comercial():
    """Panel de soporte para gestores comerciales (clientes)."""
    st.title("🎫 Soporte Técnico")
    st.markdown("---")

    # Pestañas para diferentes funciones
    tab1, tab2 = st.tabs(["📋 Mis Tickets", "➕ Nuevo Ticket"])

    with tab1:
        mostrar_mis_tickets_gestor()

    with tab2:
        crear_ticket_cliente()


def obtener_emails_administradores():
    """Obtiene los correos de todos los administradores."""
    try:
        conn = obtener_conexion()
        query = "SELECT email FROM usuarios WHERE role = 'admin' AND email IS NOT NULL"
        df = pd.read_sql(query, conn)
        conn.close()
        return df['email'].tolist()
    except Exception as e:
        st.warning(f"No se pudieron obtener correos de administradores: {str(e)[:100]}")
        return []


def mostrar_mis_tickets_gestor():
    """Muestra los tickets creados por el gestor comercial actual."""

    # Obtener el ID del usuario actual (gestor comercial)
    user_id = st.session_state.get("user_id")
    if not user_id:
        # Intentar obtenerlo de otra manera si no está en session_state
        try:
            conn = obtener_conexion()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM usuarios WHERE username = ?", (st.session_state['username'],))
            result = cursor.fetchone()
            conn.close()
            if result:
                user_id = result[0]
            else:
                st.toast("❌ No se pudo identificar al usuario.")
                return
        except:
            st.toast("❌ Error al obtener información del usuario.")
            return

    st.subheader("📋 Mis Tickets Reportados")
    st.markdown("---")

    try:
        conn = obtener_conexion()

        # Consulta para obtener tickets del gestor comercial
        query = """
        SELECT 
            t.ticket_id,
            t.fecha_creacion,
            t.categoria,
            t.prioridad,
            t.estado,
            u.username as asignado_a,
            t.titulo,
            t.descripcion,
            t.comentarios
        FROM tickets t
        LEFT JOIN usuarios u ON t.asignado_a = u.id
        WHERE t.usuario_id = ?
        ORDER BY t.fecha_creacion DESC
        """

        df_tickets = pd.read_sql(query, conn, params=(user_id,))
        conn.close()

        if df_tickets.empty:
            st.toast("🎉 No has creado ningún ticket aún.")
            st.info("Usa la pestaña '➕ Nuevo Ticket' para reportar una incidencia.")
            return

        # Mostrar métricas rápidas
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Tickets", len(df_tickets))
        with col2:
            abiertos = len(df_tickets[df_tickets['estado'] == 'Abierto'])
            st.metric("Abiertos", abiertos)
        with col3:
            resueltos = len(df_tickets[df_tickets['estado'].isin(['Resuelto', 'Cancelado'])])
            st.metric("Resueltos", resueltos)

        st.markdown("---")

        # Mostrar cada ticket en un expander
        for _, ticket in df_tickets.iterrows():
            # Determinar color según prioridad
            prioridad_color = {
                'Alta': '🔴',
                'Media': '🟡',
                'Baja': '🟢'
            }.get(ticket['prioridad'], '⚪')

            # Determinar color según estado
            estado_color = {
                'Abierto': '🟢',
                'En Progreso': '🟡',
                'Resuelto': '🔵',
                'Cancelado': '⚫'
            }.get(ticket['estado'], '⚪')

            with st.expander(f"{estado_color} Ticket #{ticket['ticket_id']}: {ticket['titulo']} {prioridad_color}"):
                col_info1, col_info2 = st.columns(2)

                with col_info1:
                    st.markdown(f"**📅 Creado:** {ticket['fecha_creacion']}")
                    st.markdown(f"**🏷️ Categoría:** {ticket['categoria']}")
                    st.markdown(f"**🚨 Prioridad:** {ticket['prioridad']}")

                with col_info2:
                    st.markdown(f"**📊 Estado:** {ticket['estado']}")
                    st.markdown(f"**👥 Asignado a:** {ticket['asignado_a'] or 'Pendiente de asignación'}")
                    st.markdown(f"**🎫 ID:** #{ticket['ticket_id']}")

                st.markdown("---")
                st.markdown("**📄 Descripción:**")
                st.info(ticket['descripcion'])

                if ticket['comentarios']:
                    st.markdown("---")
                    st.markdown("**💬 Comentarios del equipo:**")
                    # Mostrar comentarios con formato
                    comentarios = ticket['comentarios'].split('\n\n')
                    for comentario in comentarios:
                        if comentario.strip():
                            st.warning(comentario.strip())

                # Botón para añadir más información (solo si el ticket está abierto)
                if ticket['estado'] in ['Abierto', 'En Progreso']:
                    st.markdown("---")
                    st.markdown("**📝 Añadir información adicional:**")

                    # Formulario separado para añadir información
                    with st.form(key=f"add_info_{ticket['ticket_id']}"):
                        nueva_info = st.text_area(
                            "Información adicional:",
                            placeholder="Si tienes más detalles sobre esta incidencia, añádelos aquí...",
                            height=100,
                            key=f"info_{ticket['ticket_id']}"
                        )

                        enviar_info = st.form_submit_button("📤 Enviar información", use_container_width=True)

                        if enviar_info and nueva_info.strip():
                            try:
                                conn = obtener_conexion()
                                cursor = conn.cursor()

                                # Obtener información del ticket para notificaciones
                                cursor.execute("""
                                    SELECT t.titulo, t.prioridad, t.categoria,
                                           u.email as asignado_email, u.username as asignado_username,
                                           u2.email as creador_email, u2.username as creador_username
                                    FROM tickets t
                                    LEFT JOIN usuarios u ON t.asignado_a = u.id
                                    LEFT JOIN usuarios u2 ON t.usuario_id = u2.id
                                    WHERE t.ticket_id = ?
                                """, (ticket['ticket_id'],))

                                ticket_data = cursor.fetchone()

                                # Añadir la información al campo de comentarios
                                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
                                info_formateada = f"\n\n[{timestamp}] {st.session_state['username']} (cliente):\n{nueva_info.strip()}"

                                cursor.execute("""
                                    UPDATE tickets 
                                    SET comentarios = COALESCE(comentarios || ?, ?)
                                    WHERE ticket_id = ?
                                """, (
                                    info_formateada,
                                    f"[{timestamp}] {st.session_state['username']} (cliente):\n{nueva_info.strip()}",
                                    ticket['ticket_id']
                                ))

                                conn.commit()
                                conn.close()

                                # Enviar notificaciones por correo
                                if ticket_data:
                                    try:
                                        ticket_info = {
                                            'ticket_id': ticket['ticket_id'],
                                            'titulo': ticket_data[0],
                                            'actualizado_por': st.session_state['username'],
                                            'tipo_actualizacion': 'informacion_adicional',
                                            'descripcion_cambio': nueva_info.strip(),
                                            'enlace': f"https://tu-dominio.com/ticket/{ticket['ticket_id']}"
                                        }

                                        # Notificar al asignado (si existe)
                                        if ticket_data[3] and ticket_data[4] != st.session_state['username']:
                                            notificar_actualizacion_ticket(ticket_data[3], ticket_info)

                                        # Notificar a todos los administradores
                                        admin_emails = obtener_emails_administradores()
                                        for email in admin_emails:
                                            if email != st.session_state.get('email', ''):  # Evitar auto-notificación
                                                notificar_actualizacion_ticket(email, ticket_info)

                                        st.toast(f"📧 Notificaciones enviadas")

                                    except Exception as e:
                                        st.warning(f"No se pudieron enviar notificaciones: {str(e)[:100]}")

                                # Registrar en trazabilidad
                                log_trazabilidad(
                                    st.session_state["username"],
                                    "Información adicional en ticket",
                                    f"Añadió información al ticket #{ticket['ticket_id']}"
                                )

                                st.toast("✅ Información añadida al ticket")
                                st.rerun()
                            except Exception as e:
                                st.toast(f"❌ Error al añadir información: {str(e)[:100]}")

    except Exception as e:
        st.toast(f"⚠️ Error al cargar tickets: {str(e)[:200]}")


def crear_ticket_cliente():
    """Formulario para que los gestores comerciales creen tickets como clientes."""

    st.subheader("➕ Crear Nuevo Ticket")
    st.markdown("---")

    # Información del gestor comercial
    st.info(f"**👤 Reportando como:** {st.session_state.get('username', 'Gestor comercial')}")

    # Inicializar estado para manejar confirmación
    if 'ticket_creado' not in st.session_state:
        st.session_state['ticket_creado'] = False
        st.session_state['ticket_info'] = {}

    # Si ya se creó un ticket, mostrar confirmación
    if st.session_state.get('ticket_creado'):
        ticket_info = st.session_state.get('ticket_info', {})

        st.success(f"✅ **Ticket #{ticket_info.get('id')} creado correctamente**")

        # Mostrar resumen
        with st.expander("📋 Ver resumen del ticket", expanded=True):
            col_sum1, col_sum2 = st.columns(2)
            with col_sum1:
                st.markdown(f"**🎫 ID:** #{ticket_info.get('id')}")
                st.markdown(f"**📝 Asunto:** {ticket_info.get('titulo')}")
                st.markdown(f"**🏷️ Tipo:** {ticket_info.get('categoria')}")
                st.markdown(f"**🚨 Urgencia:** {ticket_info.get('prioridad')}")

            with col_sum2:
                st.markdown(f"**📊 Estado:** Abierto")
                st.markdown(f"**👤 Reportado por:** {st.session_state.get('username')}")
                st.markdown(f"**👥 Asignado a:** Pendiente de asignación")
                st.markdown(f"**📅 Fecha:** {ticket_info.get('fecha')}")

        # Opciones después de crear
        st.markdown("---")
        col_opc1, col_opc2 = st.columns(2)
        with col_opc1:
            if st.button("📋 Ver mis tickets", use_container_width=True):
                # Limpiar estado y mostrar la pestaña de tickets
                st.session_state['ticket_creado'] = False
                st.rerun()

        with col_opc2:
            if st.button("➕ Crear otro ticket", use_container_width=True):
                # Limpiar estado para mostrar formulario nuevamente
                st.session_state['ticket_creado'] = False
                st.rerun()

        return

    # Si no se ha creado ticket, mostrar formulario
    st.markdown("---")

    with st.form("form_ticket_cliente"):
        # Título y categoría
        titulo = st.text_input(
            "📝 **Asunto del ticket** *",
            placeholder="Ej: Problema con la visualización de datos en el mapa de asignaciones",
            help="Describe brevemente la incidencia"
        )

        col_cat, col_pri = st.columns(2)
        with col_cat:
            categoria = st.selectbox(
                "🏷️ **Tipo de incidencia** *",
                [
                    "Problema técnico",
                    "Error en datos",
                    "Consulta sobre funcionalidad",
                    "Solicitud de nueva característica",
                    "Problema de acceso",
                    "Otro"
                ]
            )

        with col_pri:
            prioridad = st.selectbox(
                "🚨 **Urgencia** *",
                ["Baja", "Media", "Alta"],
                help="Alta = Bloqueante, Media = Importante, Baja = Mejora"
            )

        # Descripción detallada
        st.markdown("**📄 Descripción detallada** *")
        descripcion = st.text_area(
            label="",
            placeholder="""Por favor, describe la incidencia con el mayor detalle posible:

• ¿Qué problema has encontrado?
• ¿Qué estabas intentando hacer?
• ¿Qué pasó exactamente?
• ¿Qué esperabas que sucediera?
• ¿Cuándo ocurrió? (Fecha y hora aproximada)

Si es un error técnico:
• ¿Qué pasos seguiste para que ocurriera?
• ¿Apareció algún mensaje de error?
• ¿En qué pantalla o sección ocurrió?

Información adicional:
• Navegador que usas:
• Sistema operativo:
• Dispositivo (PC, móvil, tablet):""",
            height=300,
            label_visibility="collapsed"
        )

        # Información adicional opcional
        with st.expander("🔧 Información técnica adicional (opcional)"):
            st.markdown("Esta información ayuda a los técnicos a diagnosticar el problema más rápido.")

            col_tech1, col_tech2 = st.columns(2)
            with col_tech1:
                navegador = st.selectbox(
                    "Navegador:",
                    ["Chrome", "Firefox", "Edge", "Safari", "Otro", "No sé"]
                )

                sistema_operativo = st.selectbox(
                    "Sistema operativo:",
                    ["Windows", "macOS", "Linux", "iOS", "Android", "Otro"]
                )

            with col_tech2:
                dispositivo = st.selectbox(
                    "Dispositivo:",
                    ["PC/Laptop", "Móvil", "Tablet", "Otro"]
                )

                url_pagina = st.text_input(
                    "URL de la página (si aplica):",
                    placeholder="https://..."
                )

        # Adjuntar archivos (opcional)
        with st.expander("📎 Adjuntar archivos (opcional)"):
            st.info("Puedes adjuntar capturas de pantalla o documentos relacionados con la incidencia.")
            archivos = st.file_uploader(
                "Selecciona archivos:",
                type=['png', 'jpg', 'jpeg', 'pdf', 'txt', 'csv'],
                accept_multiple_files=True
            )

            if archivos:
                st.toast(f"✅ {len(archivos)} archivo(s) listo(s) para adjuntar")
                for archivo in archivos:
                    st.write(f"📄 {archivo.name} ({archivo.size / 1024:.1f} KB)")

        st.markdown("---")
        st.markdown("**\* Campos obligatorios**")

        # Botones del formulario (SOLO form_submit_button permitido)
        col_btn1, col_btn2 = st.columns([1, 1])
        with col_btn1:
            enviar = st.form_submit_button(
                "✅ **Enviar Ticket**",
                type="primary",
                use_container_width=True
            )
        with col_btn2:
            cancelar = st.form_submit_button(
                "❌ **Cancelar**",
                use_container_width=True
            )

        # Procesar formulario
        if enviar:
            if not titulo or not descripcion:
                st.toast("⚠️ Por favor, completa todos los campos obligatorios (*)")
            else:
                try:
                    # Obtener user_id del gestor comercial
                    user_id = st.session_state.get("user_id")
                    if not user_id:
                        # Intentar obtenerlo de la base de datos
                        conn = obtener_conexion()
                        cursor = conn.cursor()
                        cursor.execute("SELECT id FROM usuarios WHERE username = ?", (st.session_state['username'],))
                        result = cursor.fetchone()
                        if result:
                            user_id = result[0]
                        else:
                            st.toast("❌ No se pudo identificar al usuario. Por favor, contacta con administración.")
                            return
                        conn.close()

                    # Crear descripción completa con información técnica
                    descripcion_completa = descripcion

                    # Añadir información técnica si se proporcionó
                    info_tecnica = "\n\n--- INFORMACIÓN TÉCNICA ---\n"
                    info_tecnica += f"• Navegador: {navegador}\n"
                    info_tecnica += f"• Sistema operativo: {sistema_operativo}\n"
                    info_tecnica += f"• Dispositivo: {dispositivo}\n"
                    if url_pagina:
                        info_tecnica += f"• URL: {url_pagina}\n"
                    info_tecnica += f"• Fecha reporte: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"

                    descripcion_completa += info_tecnica

                    # Insertar el ticket en la base de datos
                    conn = obtener_conexion()
                    cursor = conn.cursor()

                    cursor.execute("""
                        INSERT INTO tickets 
                        (usuario_id, categoria, prioridad, estado, titulo, descripcion)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        user_id,
                        categoria,
                        prioridad,
                        "Abierto",  # Estado inicial: Abierto sin asignar
                        titulo,
                        descripcion_completa
                    ))

                    conn.commit()
                    ticket_id = cursor.lastrowid

                    # Añadir comentario inicial
                    cursor.execute("""
                        UPDATE tickets 
                        SET comentarios = ?
                        WHERE ticket_id = ?
                    """, (
                        f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Ticket creado por gestor comercial {st.session_state['username']}. Pendiente de asignación a técnico.",
                        ticket_id
                    ))

                    conn.commit()

                    # Obtener email del creador para notificación
                    cursor.execute("SELECT email FROM usuarios WHERE id = ?", (user_id,))
                    creador_info = cursor.fetchone()

                    conn.close()

                    # Enviar notificaciones por correo
                    try:
                        # Obtener correos de todos los administradores
                        admin_emails = obtener_emails_administradores()

                        ticket_info = {
                            'ticket_id': ticket_id,
                            'titulo': titulo,
                            'creado_por': st.session_state['username'],
                            'prioridad': prioridad,
                            'categoria': categoria,
                            'estado': "Abierto",
                            'descripcion': descripcion[:100] + '...' if len(descripcion) > 100 else descripcion,
                            'enlace': f"https://tu-dominio.com/ticket/{ticket_id}"
                        }

                        # Notificar a todos los administradores
                        for email in admin_emails:
                            notificar_creacion_ticket(email, ticket_info)

                        # Notificar al creador (gestor comercial)
                        if creador_info and creador_info[0]:
                            notificar_creacion_ticket(creador_info[0], ticket_info)

                        st.toast(f"📧 Notificaciones enviadas a {len(admin_emails)} administrador(es)")

                    except Exception as e:
                        st.warning(f"No se pudieron enviar notificaciones: {str(e)[:100]}")

                    # Registrar en trazabilidad
                    log_trazabilidad(
                        st.session_state["username"],
                        "Creación de ticket (cliente)",
                        f"Ticket #{ticket_id} creado como cliente: {titulo}"
                    )

                    # Guardar información para mostrar confirmación
                    st.session_state['ticket_creado'] = True
                    st.session_state['ticket_info'] = {
                        'id': ticket_id,
                        'titulo': titulo,
                        'categoria': categoria,
                        'prioridad': prioridad,
                        'fecha': datetime.now().strftime('%d/%m/%Y %H:%M')
                    }

                    # Recargar para mostrar confirmación
                    st.rerun()

                except Exception as e:
                    st.toast(f"❌ Error al crear el ticket: {str(e)[:200]}")
                    st.info("""
                    **Solución:**
                    1. Verifica tu conexión a internet
                    2. Contacta con el administrador si el problema persiste
                    3. Intenta nuevamente en unos minutos
                    """)

        if cancelar:
            # Solo se ejecuta si se presiona Cancelar
            st.info("Formulario cancelado. No se ha creado ningún ticket.")

def obtener_conexion():
    return sqlitecloud.connect(
        "sqlitecloud://ceafu04onz.g6.sqlite.cloud:8860/usuarios.db?apikey=Qo9m18B9ONpfEGYngUKm99QB5bgzUTGtK7iAcThmwvY"
    )
########################

def mostrar_coordenadas():
    import folium
    from folium.plugins import MarkerCluster
    from streamlit_folium import st_folium
    from geopy.distance import geodesic

    st.info(
        "📍 **Búsqueda por coordenadas**\n\n"
        "En esta sección puedes visualizar todos los puntos serviciables disponibles dentro de un radio específico "
        "a partir de las coordenadas que introduzcas. "
        "Al hacer clic sobre cualquiera de los puntos del mapa, se mostrará debajo una tarjeta informativa con los datos "
        "detallados del punto seleccionado. "
        "Cuando existen muchos puntos muy próximos entre sí, estos se agrupan en un *cluster* con un número en su interior, "
        "que indica la cantidad de puntos disponibles en esa zona. Puedes pinchar en el *cluster* para desplegar cada uno de los puntos que contiene."
    )

    # --- Entradas ---
    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        lat = st.number_input("🌐 Latitud", value=40.4168, format="%.6f", key="coord_lat")
    with col2:
        lon = st.number_input("🌐 Longitud", value=-3.7038, format="%.6f", key="coord_lon")
    with col3:
        radio_km = st.number_input("📏 Radio (km)", value=1.0, min_value=0.1, max_value=50.0, step=0.5, key="coord_radio")

    buscar = st.button("🔍 Buscar coordenadas", width='stretch')

    if buscar:
        with st.spinner("🗺️ Calculando puntos dentro del radio..."):
            try:
                # --- Cargar datos desde BD ---
                conn = get_db_connection()
                query = "SELECT municipio, poblacion, latitud, longitud, vial, numero, cp FROM datos_uis"
                df = pd.read_sql(query, conn)
                conn.close()

                # --- Filtrar coordenadas válidas ---
                df = df[
                    (df["latitud"].between(-90, 90)) &
                    (df["longitud"].between(-180, 180))
                ].dropna(subset=["latitud", "longitud"])

                if df.empty:
                    st.warning("⚠️ No hay coordenadas válidas en la base de datos.")
                    return

                # --- Calcular distancias ---
                df["distancia_km"] = [
                    geodesic((lat, lon), (r_lat, r_lon)).km
                    for r_lat, r_lon in zip(df["latitud"], df["longitud"])
                ]

                # --- Filtrar por radio ---
                df_radio = df[df["distancia_km"] <= radio_km].copy()
                df_radio.reset_index(drop=True, inplace=True)

                if df_radio.empty:
                    st.warning("⚠️ No se encontraron puntos dentro del radio indicado.")
                    return

                # --- Guardar en sesión ---
                st.session_state["busqueda_coordenadas"] = {
                    "lat": lat,
                    "lon": lon,
                    "radio_km": radio_km,
                    "df_radio": df_radio
                }

                st.toast(f"✅ Se encontraron {len(df_radio)} puntos dentro de {radio_km:.2f} km.")

            except Exception as e:
                st.toast(f"❌ Error al buscar coordenadas: {e}")

    # --- Mostrar mapa si ya hay datos ---
    if "busqueda_coordenadas" in st.session_state:
        datos = st.session_state["busqueda_coordenadas"]
        lat, lon, radio_km, df_radio = (
            datos["lat"], datos["lon"], datos["radio_km"], datos["df_radio"]
        )

        # Crear mapa centrado en las coordenadas
        m = folium.Map(location=[lat, lon], zoom_start=15, control_scale=True, max_zoom=19)

        # Capa satélite + etiquetas (persistente al hacer zoom)
        folium.TileLayer(
            tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
            attr="Google Satellite",
            name="🛰️ Google Satélite",
            overlay=False,
            control=True,
            max_zoom=20
        ).add_to(m)
        folium.TileLayer(
            tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
            attr="Google Hybrid",
            name="🗺️ Etiquetas",
            overlay=True,
            control=True,
            max_zoom=20
        ).add_to(m)

        # Círculo del radio
        folium.Circle(
            location=[lat, lon],
            radius=radio_km * 1000,
            color="blue",
            weight=2,
            fill=True,
            fill_color="#3186cc",
            fill_opacity=0.15,
            popup=f"Radio: {radio_km} km"
        ).add_to(m)

        # Marcador central
        folium.Marker(
            location=[lat, lon],
            popup="📍 Coordenadas buscadas",
            icon=folium.Icon(color="red", icon="glyphicon-screenshot")
        ).add_to(m)

        # Agrupar puntos dentro del radio
        cluster = MarkerCluster().add_to(m)
        for i, row in df_radio.iterrows():
            folium.Marker(
                location=[row["latitud"], row["longitud"]],
                popup=f"{row.get('municipio', '—')} - {row.get('poblacion', '—')}",
                tooltip=f"📍 {row.get('municipio', '—')} ({row['distancia_km']:.2f} km)",
                icon=folium.Icon(color="green", icon="glyphicon-tint")  # vuelve al icono gotita
            ).add_to(cluster)

        # Mostrar mapa
        mapa_output = st_folium(m, height=680, width="100%", key="mapa_busqueda_coordenadas")

        # --- Detectar clic y guardar punto seleccionado ---
        if mapa_output and mapa_output.get("last_object_clicked") is not None:
            click_lat = mapa_output["last_object_clicked"]["lat"]
            click_lon = mapa_output["last_object_clicked"]["lng"]

            df_radio["distancia_click"] = [
                geodesic((click_lat, click_lon), (r_lat, r_lon)).meters
                for r_lat, r_lon in zip(df_radio["latitud"], df_radio["longitud"])
            ]

            punto_mas_cercano = df_radio.loc[df_radio["distancia_click"].idxmin()]
            st.session_state["punto_seleccionado"] = punto_mas_cercano

        # --- Mostrar ficha del punto seleccionado ---
        if st.session_state.get("punto_seleccionado") is not None:
            seleccionado = st.session_state["punto_seleccionado"].fillna("—")

            st.markdown("### 📋 Detalles del punto seleccionado")

            st.markdown(
                f"""
                <div style='background-color:#f9f9f9; padding:15px; border-radius:10px; border:1px solid #ddd;'>
                    <p><strong>🏘️ Municipio:</strong> {seleccionado.get('municipio', '—')}</p>
                    <p><strong>🏡 Población:</strong> {seleccionado.get('poblacion', '—')}</p>
                    <p><strong>📍 Dirección:</strong> {seleccionado.get('vial', '—')} {seleccionado.get('numero', '—')}</p>
                    <p><strong>📮 Código Postal:</strong> {seleccionado.get('cp', '—')}</p>
                    <p><strong>🌐 Latitud:</strong> {seleccionado.get('latitud', '—')}</p>
                    <p><strong>🌐 Longitud:</strong> {seleccionado.get('longitud', '—')}</p>
                    <p><strong>📏 Distancia al punto:</strong> {seleccionado.get('distancia_km', '—')} km</p>
                </div>
                """,
                unsafe_allow_html=True
            )

        # Botón limpiar búsqueda
        if st.button("🧹 Limpiar búsqueda"):
            for key in ["busqueda_coordenadas", "punto_seleccionado"]:
                st.session_state.pop(key, None)
            st.rerun()


def mostrar_mapa_de_asignaciones():
    username = st.session_state.get("username", "").strip()

    # Cargar datos con spinner
    with st.spinner("Cargando datos..."):
        # Pasar el username actual a cargar_datos
        datos_uis, comercial_rafa = cargar_datos(username)

        # Si después del filtro no quedan datos, detenemos
        if datos_uis.empty:
            st.warning("⚠️ No hay datos disponibles para mostrar.")
            st.stop()

    with st.expander("📊 Información sobre el funcionamiento del mapa", expanded=False):
        st.info("""
        🔦 **Por cuestiones de eficiencia en la carga de datos**, cuando hay una alta concentración de puntos, 
        el mapa solo mostrará los puntos relativos a los **filtros elegidos por el usuario**.

        Usa los filtros de **Provincia**, **Municipio** y **Población** para ver las zonas que necesites.  
        Opcionalmente, puedes usar los **rangos de fecha** para una búsqueda más precisa.
        """)

    # Filtro por provincia
    provincias = datos_uis['provincia'].unique()
    provincia_seleccionada = st.selectbox("Seleccione una provincia:", provincias)
    datos_uis = datos_uis[datos_uis["provincia"] == provincia_seleccionada]

    col_cto1, col_cto2, col_cto3 = st.columns([1, 1, 2])
    with col_cto1:
        mostrar_verde = st.checkbox("CTO Verde", value=True)
    with col_cto2:
        mostrar_compartida = st.checkbox("CTO Compartida", value=True)

    # Aplica el filtro solo si existe la columna tipo_olt_rental
    if "tipo_olt_rental" in datos_uis.columns:
        condiciones = []
        if mostrar_verde:
            condiciones.append(datos_uis["tipo_olt_rental"].str.contains("verde", case=False, na=False))
        if mostrar_compartida:
            condiciones.append(datos_uis["tipo_olt_rental"].str.contains("compartida", case=False, na=False))
        if condiciones:
            datos_uis = datos_uis[pd.concat(condiciones, axis=1).any(axis=1)]
        else:
            st.warning("⚠️ Debes seleccionar al menos un tipo de CTO para mostrar datos.")
            st.stop()
    else:
        st.warning("⚠️ No se encontró la columna 'tipo_olt_rental' en los datos.")

    # --------------------
    # CONVERTIR FECHA DE TEXTO A DATETIME
    # --------------------
    if 'fecha' in datos_uis.columns:
        datos_uis['fecha'] = pd.to_datetime(datos_uis['fecha'], errors='coerce')
    else:
        st.warning("⚠️ No se encontró la columna 'fecha' en los datos.")

    # --------------------
    # FILTRO DE PUNTOS NUEVOS
    # --------------------
    mostrar_nuevos = st.checkbox("Mostrar novedades: huella cargada mas reciente")

    if mostrar_nuevos:
        if 'fecha' in datos_uis.columns:
            # Convertir texto a datetime
            datos_uis['fecha'] = pd.to_datetime(datos_uis['fecha'], errors='coerce')
            hoy = datetime.now()
            datos_uis = datos_uis[
                (datos_uis['fecha'].dt.year == hoy.year) &
                (datos_uis['fecha'].dt.month == hoy.month)
                ]
            if datos_uis.empty:
                st.warning("⚠️ No hay puntos nuevos en el mes actual.")
                st.stop()
        else:
            st.warning("⚠️ No se encontró la columna 'fecha' en los datos.")

    # --------------------
    # FILTRO DE RANGO DE FECHAS
    # --------------------
    if 'fecha' in datos_uis.columns:
        fecha_min = datos_uis['fecha'].min().date()
        fecha_max = datos_uis['fecha'].max().date()

        rango_fechas = st.date_input(
            "(Opcional) Seleccione rango de fechas:",
            value=(fecha_min, fecha_max),
            min_value=fecha_min,
            max_value=fecha_max
        )

        if len(rango_fechas) == 2:
            fecha_inicio, fecha_fin = rango_fechas
            datos_uis = datos_uis[
                (datos_uis['fecha'].dt.date >= fecha_inicio) &
                (datos_uis['fecha'].dt.date <= fecha_fin)
                ]
            if datos_uis.empty:
                st.warning("⚠️ No hay puntos en el rango de fechas seleccionado.")
                st.stop()

    # Limpiar latitud y longitud
    datos_uis = datos_uis.dropna(subset=['latitud', 'longitud'])
    datos_uis['latitud'] = datos_uis['latitud'].astype(float)
    datos_uis['longitud'] = datos_uis['longitud'].astype(float)

    # Lista general de comerciales para otros usuarios
    comerciales_generales = ["jose ramon"]

    # Comerciales disponibles según usuario
    if username.lower() == "juan":
        comerciales_disponibles = ["Comercial2", "Comercial3"]
    else:
        comerciales_disponibles = comerciales_generales

    col1, col2 = st.columns([3, 3])
    with col2:
        accion = st.radio("Seleccione la acción requerida:", ["Asignar Zona", "Desasignar Zona"], key="accion")

        if accion == "Asignar Zona":
            import unicodedata
            def limpiar_texto(txt):
                if not isinstance(txt, str):
                    return ""
                # Normalizar tildes y eliminar comillas/apóstrofes dobles
                txt = unicodedata.normalize('NFKC', txt)
                txt = txt.replace("'", "").replace('"', "").strip()
                return txt

            municipios = sorted(datos_uis['municipio'].dropna().unique())
            municipio_sel = st.selectbox("Seleccione un municipio:", municipios, key="municipio_sel")

            tipo_asignacion = st.radio(
                "¿Qué desea asignar?",
                ["Población específica", "Municipio completo"],
                horizontal=True,
                key="tipo_asignacion"
            )

            poblacion_sel = None
            if tipo_asignacion == "Población específica" and municipio_sel:
                poblaciones = sorted(datos_uis[datos_uis['municipio'] == municipio_sel]['poblacion'].dropna().unique())
                poblacion_sel = st.selectbox("Seleccione una población:", poblaciones, key="poblacion_sel")

            # Mostrar comerciales filtrados según usuario
            comerciales_seleccionados = st.multiselect(
                "Asignar equitativamente a:", comerciales_disponibles,
                key="comerciales_seleccionados"
            )

            # Condición general
            if municipio_sel and comerciales_seleccionados and (
                    tipo_asignacion == "Municipio completo" or poblacion_sel
            ):
                conn = get_db_connection()
                cursor = conn.cursor()

                if tipo_asignacion == "Municipio completo":
                    condicion_where = "municipio = ? AND comercial = ?"
                    params = (municipio_sel, username)
                else:
                    condicion_where = "municipio = ? AND poblacion = ? AND comercial = ?"
                    params = (municipio_sel, poblacion_sel, username)

                # Total de puntos de esa zona
                cursor.execute(f"SELECT COUNT(*) FROM datos_uis WHERE {condicion_where}", params)
                total_puntos = cursor.fetchone()[0] or 0

                # Total ya asignados
                cursor.execute(
                    f"SELECT COUNT(*) FROM comercial_rafa WHERE {condicion_where.replace('comercial = ?', '1=1')}",
                    params[:-1] if len(params) > 1 else params)
                asignados = cursor.fetchone()[0] or 0

                pendientes = total_puntos - asignados
                conn.close()

                if asignados >= total_puntos and total_puntos > 0:
                    st.warning("🚫 Esta zona ya ha sido asignada completamente.")
                else:
                    if st.button("Asignar Zona"):
                        conn = get_db_connection()
                        cursor = conn.cursor()

                        if tipo_asignacion == "Municipio completo":
                            cursor.execute(f"""
                                SELECT apartment_id, provincia, municipio, poblacion, vial, numero, letra, cp, latitud, longitud
                                FROM datos_uis
                                WHERE municipio = ?
                                  AND comercial = ?
                                  AND apartment_id NOT IN (
                                      SELECT apartment_id FROM comercial_rafa WHERE municipio = ?
                                  )
                            """, (municipio_sel, username, municipio_sel))
                        else:
                            cursor.execute(f"""
                                SELECT apartment_id, provincia, municipio, poblacion, vial, numero, letra, cp, latitud, longitud
                                FROM datos_uis
                                WHERE municipio = ? AND poblacion = ?
                                  AND comercial = ?
                                  AND apartment_id NOT IN (
                                      SELECT apartment_id FROM comercial_rafa
                                      WHERE municipio = ? AND poblacion = ?
                                  )
                            """, (municipio_sel, poblacion_sel, username, municipio_sel, poblacion_sel))

                        puntos = cursor.fetchall()
                        nuevos_asignados = len(puntos)

                        if not puntos:
                            st.warning("⚠️ No se encontraron puntos pendientes de asignar en esta zona.")
                            conn.close()
                            st.stop()

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
                                    INSERT OR IGNORE INTO comercial_rafa 
                                    (apartment_id, provincia, municipio, poblacion, vial, numero, letra, cp, latitud, longitud, comercial, Contrato)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """, (*punto, comercial, 'Pendiente'))

                                # 2️⃣ Reasignar el comercial si ya existía
                                cursor.execute("""
                                            UPDATE comercial_rafa
                                            SET comercial = ?
                                            WHERE apartment_id = ?
                                        """, (comercial, punto[0]))  # punto[0] = apartment_id

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
                                        f"📍 Se le ha asignado la zona {municipio_sel}"
                                        + (
                                            f" - {poblacion_sel}" if tipo_asignacion == "Población específica" else " (municipio completo)")
                                        + ".<br><br>💼 Ya puede comenzar a gestionar las tareas correspondientes.<br>"
                                          "ℹ️ Revise su panel de usuario para más detalles.<br><br>"
                                          "🚨 Si tiene dudas, contacte con administración.<br>¡Gracias!"
                                )
                                correo_asignacion_administracion(destinatario_comercial, municipio_sel,
                                                                 poblacion_sel if poblacion_sel else "",
                                                                 descripcion_asignacion)
                            except Exception as e:
                                st.toast(f"❌ Error al notificar a {comercial}: {e}")

                        # Notificar administradores
                        cursor.execute("SELECT email FROM usuarios WHERE role = 'admin'")
                        emails_admins = [fila[0] for fila in cursor.fetchall()]
                        descripcion_admin = (
                                f"📢 Nueva asignación de zona.\n\n"
                                f"📌 Zona Asignada: {municipio_sel}"
                                + (
                                    f" - {poblacion_sel}" if tipo_asignacion == "Población específica" else " (municipio completo)")
                                + f"\n👥 Asignado a: {', '.join(comerciales_seleccionados)}\n"
                                  f"🕵️ Asignado por: {username}"
                        )
                        for email_admin in emails_admins:
                            correo_asignacion_administracion2(email_admin, municipio_sel,
                                                              poblacion_sel if poblacion_sel else "",
                                                              descripcion_admin)

                        st.toast("✅ Zona asignada correctamente y notificaciones enviadas.")
                        st.toast(f"📧 Se notificó a: {', '.join(comerciales_seleccionados)}")
                        st.toast(
                            f"📊 Total puntos: {total_puntos} | Ya asignados: {asignados} | Nuevos: {nuevos_asignados} | Pendientes tras asignación: {total_puntos - (asignados + nuevos_asignados)}"
                        )

                        log_trazabilidad(
                            username, "Asignación múltiple",
                            f"Zona {municipio_sel} "
                            + (
                                f"- {poblacion_sel}" if tipo_asignacion == "Población específica" else " (municipio completo)")
                            + f" repartida entre {', '.join(comerciales_seleccionados)}"
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

                    municipio_sel = municipio_sel.strip()
                    poblacion_sel = poblacion_sel.strip()

                    conn = get_db_connection()
                    query = """
                        SELECT DISTINCT comercial 
                        FROM comercial_rafa 
                        WHERE LOWER(TRIM(municipio)) = LOWER(TRIM(?))
                          AND LOWER(TRIM(poblacion)) = LOWER(TRIM(?))
                    """
                    comerciales_asignados = pd.read_sql(query, conn, params=(municipio_sel, poblacion_sel))
                    conn.close()

                    # Filtrar comerciales asignados según usuario
                    if username == "juan":
                        comerciales_asignados = comerciales_asignados[
                            comerciales_asignados['comercial'].isin(["Comercial2", "Comercial3"])]

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
                                st.toast(
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
                                st.toast(
                                    f"ℹ️ No había puntos para desasignar en la zona {municipio_sel} - {poblacion_sel} "
                                    f"para el comercial **{comercial_a_eliminar}**."
                                )

        # --- REASIGNAR PUNTOS ---
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
                                st.toast(f"✅ Puntos liberados reasignados correctamente.\nTotal puntos: {total_puntos}\n{resumen}")

                                # Recargar la página para ver los cambios
                                st.rerun()

                        except Exception as e:
                            # En caso de error, revertir los cambios
                            if 'conn' in locals():
                                conn.rollback()
                                st.toast(f"❌ Error al reasignar: {str(e)}")
                        finally:
                            # Cerrar la conexión
                            if 'conn' in locals():
                                conn.close()
        with st.expander("🗂️ Guía sobre las secciones del menú 'Ver Datos'", expanded=False):
            st.info("""
            📋 **Para revisar las asignaciones y reportes realizados:**

            Dirígete al menú **Ver Datos**, donde encontrarás tres secciones principales:

            - **Zonas asignadas:** muestra las asignaciones realizadas por el gestor.  
            - **Ofertas realizadas:** detalla las visitas y ofertas gestionadas por los comerciales, junto a su estado actual.  
            - **Viabilidades estudiadas:** presenta el historial completo de viabilidades reportadas por los comerciales.
            """)

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

                #icon_name = 'home' if str(row.get('tipo_olt_rental', '')).strip().lower() == 'si' else 'info-sign'
                tipo_olt = str(row.get('tipo_olt_rental', '')).strip()

                # Selección de icono según tipo OLT
                if "CTO VERDE" in tipo_olt:
                    icon_name = "cloud"
                else:
                    icon_name = "info-circle"
                popup_text = f"""
                    <b>Apartment ID:</b> {apartment_id}<br>
                    <b>Vial:</b> {vial}<br>
                    <b>Número:</b> {numero}<br>
                    <b>Letra:</b> {letra}<br>
                """
                folium.Marker(
                    [lat, lon],
                    icon=folium.Icon(icon=icon_name, color=color, prefix="fa"),
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
            <i class="fa fa-cloud" style="color:#2C5A2E;"></i> CTO VERDE<br>
            <i class="fa fa-info-circle" style="color:#2C5A2E;"></i> CTO COMPARTIDA
            </div>
            {% endmacro %}
            """

            macro = MacroElement()
            macro._template = Template(legend)
            m.get_root().add_child(macro)
            st_folium(m, height=500, width=700)


def mostrar_descarga_datos():
    # Configuración común para el menú
    SUB_SECCIONES = {
        "Zonas asignadas": {
            "icon": "geo-alt",
            "description": "Visualiza el total de asignaciones realizadas por el gestor."
        },
        "Ofertas realizadas": {
            "icon": "bar-chart-line",
            "description": "Ofertas comerciales: Visualización del total de ofertas asignadas."
        },
        "Viabilidades estudiadas": {
            "icon": "check2-square",
            "description": "Viabilidades: Visualización del total de viabilidades reportadas."
        },
        "Datos totales": {
            "icon": "database",
            "description": "Visualización total de los datos"
        }
    }

    # Estilos reutilizables
    MENU_STYLES = {
        "container": {
            "padding": "0!important",
            "margin": "0px",
            "background-color": "#F0F7F2",
            "border-radius": "0px",
            "max-width": "none"
        },
        "icon": {"color": "#2C5A2E", "font-size": "25px"},
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

    sub_seccion = option_menu(
        menu_title=None,
        options=list(SUB_SECCIONES.keys()),
        icons=[SUB_SECCIONES[sec]["icon"] for sec in SUB_SECCIONES],
        default_index=0,
        orientation="horizontal",
        styles=MENU_STYLES
    )

    # Obtener datos una sola vez
    username = st.session_state.get("username", "").strip().lower()

    # Cargar todos los datos necesarios en una sola conexión
    conn = get_db_connection()

    # Definir configuraciones por usuario
    USER_CONFIGS = {
        "juan": {
            "excluir_comerciales": ["nestor", "rafaela", "jose ramon", "roberto", "marian", "juan pablo"],
            "comerciales_mios": ["comercial2", "comercial3"],
            "provincias_datos": ["lugo", "asturias"],
            "excluir_viabilidades": ["roberto", "jose ramon", "nestor", "rafaela",
                                     "rebe", "marian", "rafa sanz", "juan pablo"]
        },
        "rafa sanz": {
            "excluir_comerciales": ["juan pablo"],
            "comerciales_mios": ["roberto", "nestor", "jose ramon"],
            "provincias_datos": None,
            "excluir_viabilidades": ["juan pablo", "roberto", "nestor",
                                     "comercial2", "comercial3", "juan", "marian"]
        }
    }

    config = USER_CONFIGS.get(username, {})

    # Función para construir consultas con parámetros
    def construir_consulta_exclusion(base_query, exclusion_field="comercial", exclusion_list=None):
        if not exclusion_list:
            return base_query, []

        placeholders = ",".join(["?"] * len(exclusion_list))
        query = f"{base_query} WHERE LOWER({exclusion_field}) NOT IN ({placeholders})"
        return query, [c.lower() for c in exclusion_list]

    # Cargar datos de zonas asignadas y ofertas
    if username in USER_CONFIGS:
        # Consulta base
        query_zonas = "SELECT DISTINCT municipio, poblacion, comercial FROM comercial_rafa"
        query_ofertas = "SELECT DISTINCT * FROM comercial_rafa"

        # Aplicar filtros según usuario
        exclusion_list = config.get("excluir_comerciales", [])

        if exclusion_list:
            query_zonas, params = construir_consulta_exclusion(query_zonas, "comercial", exclusion_list)
            query_ofertas, params_ofertas = construir_consulta_exclusion(query_ofertas, "comercial", exclusion_list)
        else:
            query_zonas, params = query_zonas, []
            query_ofertas, params_ofertas = query_ofertas, []

        assigned_zones = pd.read_sql(query_zonas, conn, params=params)
        total_ofertas = pd.read_sql(query_ofertas, conn, params=params_ofertas)
    else:
        # Usuario sin filtros especiales
        assigned_zones = pd.read_sql(
            "SELECT DISTINCT municipio, poblacion, comercial FROM comercial_rafa",
            conn
        )
        total_ofertas = pd.read_sql("SELECT DISTINCT * FROM comercial_rafa", conn)

    # Cargar contratos activos
    df_contratos = pd.read_sql("""
        SELECT apartment_id
        FROM seguimiento_contratos
        WHERE TRIM(LOWER(estado)) = 'finalizado'
    """, conn)

    # Marcar contratos activos (optimizado)
    total_ofertas['Contrato_Activo'] = total_ofertas['apartment_id'].isin(
        df_contratos['apartment_id']
    ).map({True: '✅ Activo', False: '❌ No Activo'})

    # Cerrar conexión temprana
    conn.close()

    # Función para mostrar tarjetas de zonas
    def mostrar_tarjetas_zonas(zonas_df):
        if zonas_df.empty:
            st.warning("⚠️ No se encontraron zonas asignadas para los comerciales de este gestor.")
            return

        resumen = (
            zonas_df.groupby("comercial")
            .agg(total_zonas=("municipio", "count"))
            .reset_index()
            .sort_values("total_zonas", ascending=False)
        )

        # Definir colores por rango
        COLORES_RANGO = {
            (31, float('inf')): "#C8E6C9",  # verde claro
            (16, 30): "#FFF9C4",  # amarillo claro
            (0, 15): "#FFEBEE"  # rojo claro
        }

        cols = st.columns(len(resumen))
        for i, row in enumerate(resumen.itertuples()):
            total = int(row.total_zonas)

            # Determinar color
            bg_color = "#FFFFFF"  # default
            for (min_val, max_val), color in COLORES_RANGO.items():
                if min_val <= total <= max_val:
                    bg_color = color
                    break

            with cols[i]:
                st.markdown(f"""
                    <div style="
                        background-color:{bg_color};
                        padding:20px;
                        text-align:center;
                        transition:transform 0.2s ease-in-out;
                    ">
                        <h3 style="color:#1B5E20; margin-bottom:10px;">👤 {row.comercial.title()}</h3>
                        <p style="font-size:30px; font-weight:bold; color:#2E7D32; margin:0;">{total}</p>
                        <p style="font-size:14px; color:#388E3C; margin-top:5px;">zonas asignadas</p>
                    </div>
                """, unsafe_allow_html=True)

    # Procesar según subsección
    if sub_seccion == "Zonas asignadas":
        with st.expander("📊 Información sobre las zonas asignadas", expanded=False):
            st.info("""
            ℹ️ **Zonas ya asignadas:**  
            Visualiza el total de asignaciones realizadas por el gestor.  
            Muestra tarjetas con el total de zonas por comercial.  
            El color indica la carga de trabajo de cada uno:

            - 🟢 **Verde:** más de 30 zonas.  
            - 🟡 **Amarillo:** entre 16 y 30 zonas.  
            - 🔴 **Rojo:** 15 o menos zonas.
            """)

        # Filtrar comerciales según el gestor
        comerciales_mios = config.get("comerciales_mios", [])
        if comerciales_mios:
            zonas_filtradas = assigned_zones[
                assigned_zones["comercial"].str.lower().isin(comerciales_mios)
            ]
        else:
            zonas_filtradas = assigned_zones.copy()

        mostrar_tarjetas_zonas(zonas_filtradas)
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.dataframe(zonas_filtradas, width='stretch')

    elif sub_seccion == "Ofertas realizadas":
        log_trazabilidad(username, "Visualización de mapa", "Usuario visualizó el mapa de Rafa Sanz.")
        st.info(f"ℹ️ {SUB_SECCIONES[sub_seccion]['description']}")
        st.dataframe(total_ofertas, width='stretch')

    elif sub_seccion == "Viabilidades estudiadas":
        # Cargar viabilidades (conexión específica si es necesario)
        conn = get_db_connection()
        viabilidades = pd.read_sql("""
            SELECT *
            FROM viabilidades
            ORDER BY id DESC
        """, conn)
        conn.close()

        # Procesar datos
        viabilidades['fecha_viabilidad'] = pd.to_datetime(
            viabilidades['fecha_viabilidad'], errors='coerce'
        )
        viabilidades['usuario'] = viabilidades['usuario'].fillna("").str.strip().str.lower()

        # Aplicar filtros de usuario
        excluir_viabilidades = config.get("excluir_viabilidades", [])
        if excluir_viabilidades:
            viabilidades = viabilidades[~viabilidades['usuario'].isin(excluir_viabilidades)]

        st.info(f"ℹ️ {SUB_SECCIONES[sub_seccion]['description']}")
        st.dataframe(viabilidades, width='stretch')

    elif sub_seccion == "Datos totales":
        st.info(f"ℹ️ {SUB_SECCIONES[sub_seccion]['description']}")

        # Cargar datos UIS según usuario
        conn = get_db_connection()

        if username == "juan":
            # Solo Lugo y Asturias
            datos_uis = pd.read_sql("""
                SELECT apartment_id, address_id, provincia, municipio, poblacion, 
                       vial, numero, parcela_catastral, letra, cp, olt, cto, 
                       latitud, longitud, comercial 
                FROM datos_uis
                WHERE LOWER(TRIM(provincia)) IN ('lugo', 'asturias')
            """, conn)

        elif username == "rafa sanz":
            # Solo registros de 'rafa sanz'
            datos_uis = pd.read_sql("""
                SELECT apartment_id, address_id, provincia, municipio, poblacion, 
                       vial, numero, parcela_catastral, letra, cp, olt, cto, 
                       latitud, longitud, comercial 
                FROM datos_uis
                WHERE LOWER(TRIM(comercial)) = 'rafa sanz'
            """, conn)
        else:
            datos_uis = pd.DataFrame()  # DataFrame vacío para otros usuarios

        conn.close()

        if not datos_uis.empty:
            st.dataframe(datos_uis, width='stretch', height=580)
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
                SELECT id, ticket,
                       provincia, municipio, poblacion,
                       vial, numero, letra,
                       latitud, longitud,
                       serviciable, resultado, justificacion, respuesta_comercial,
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
                    SELECT id, ticket,
                           provincia, municipio, poblacion,
                           vial, numero, letra,
                           latitud, longitud,
                           serviciable, resultado, justificacion, respuesta_comercial
                           usuario AS comercial_reporta,
                           confirmacion_rafa
                    FROM viabilidades
                    WHERE (confirmacion_rafa IS NULL OR confirmacion_rafa = '')
                      AND LOWER(usuario) != 'juan pablo'
                """
            df_viab = pd.read_sql(query, conn)
        else:
            df_viab = pd.read_sql("""
                SELECT id, ticket,
                       provincia, municipio, poblacion,
                       vial, numero, letra,
                       latitud, longitud,
                       serviciable, resultado, justificacion, respuesta_comercial
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

        with st.expander("🧭 Guía para la gestión de viabilidades", expanded=False):
            st.info("""
            ℹ️ **Desde este panel podrás:**  
            Revisar cuáles están pendientes de confirmación y reasignar una viabilidad a otro comercial, si lo consideras necesario.

            🔔 **NOTA:**  
            Para que una viabilidad sea enviada a la oficina de administración y comience su estudio, es imprescindible que la confirmes.  
            Solo deben ser confirmadas aquellas que, tras tu revisión, consideres aptas para recibir un estudio y presupuesto.

            📝 **¿Cómo confirmar una viabilidad?**  
            Haz clic sobre cualquier viabilidad del listado: se desplegará su descripción, un enlace directo a Google Maps,  
            la opción de reasignación y un botón para confirmar.
            """)

        if df_viab.empty:
            st.toast("🎉No hay viabilidades pendientes de confirmación.")
        else:
            if not df_viab.empty:

                # Limpiar lat/lon
                df_viab_map = df_viab.dropna(subset=['latitud', 'longitud']).copy()
                if not df_viab_map.empty:
                    # Centro del mapa
                    center = [df_viab_map['latitud'].mean(), df_viab_map['longitud'].mean()]
                    m = folium.Map(location=center, zoom_start=12,
                                   tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}", attr="Google")

                    marker_cluster = MarkerCluster(disableClusteringAtZoom=18, maxClusterRadius=70,
                                                   spiderfyOnMaxZoom=True).add_to(m)

                    for _, row in df_viab_map.iterrows():
                        lat, lon = row['latitud'], row['longitud']
                        popup_text = f"""
                        <b>ID Viabilidad:</b> {row.id}<br>
                        <b>Comercial:</b> {row.comercial_reporta}<br>
                        <b>Provincia:</b> {row.provincia}<br>
                        <b>Municipio:</b> {row.municipio}<br>
                        <b>Población:</b> {row.poblacion}<br>
                        <b>Vial:</b> {row.vial}<br>
                        <b>Número:</b> {row.numero}{row.letra or ''}<br>
                        <b>Serviciable:</b> {row.serviciable or 'Sin dato'}
                        """
                        folium.Marker(
                            [lat, lon],
                            icon=folium.Icon(icon="info-sign", color="blue"),
                            popup=folium.Popup(popup_text, max_width=300)
                        ).add_to(marker_cluster)

                    # Leyenda básica
                    legend = """
                    {% macro html(this, kwargs) %}
                    <div style="
                        position: fixed; 
                        bottom: 0px; left: 0px; width: 200px; 
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
                    <i style="color:blue;">●</i> Viabilidad pendiente de confirmación<br>
                    </div>
                    {% endmacro %}
                    """
                    macro = MacroElement()
                    macro._template = Template(legend)
                    m.get_root().add_child(macro)

                    st_folium(m, height=500, width=1750)

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
                        f"**Resultado:** {row.resultado or 'Sin dato'}<br>"
                        f"**Justificación:** {row.justificacion or 'Sin justificación'}<br>"
                        f"**Respuesta Oficina:** {row.respuesta_comercial or 'Sin respuesta'}<br>",
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

                    # ---- PRESUPUESTO---
                    # 🔎 Buscar presupuesto asociado
                    try:
                        conn2 = get_db_connection()
                        cursor2 = conn2.cursor()
                        cursor2.execute("""
                            SELECT archivo_nombre, archivo_url
                            FROM envios_presupuesto_viabilidad
                            WHERE ticket = ?
                            ORDER BY fecha_envio DESC
                            LIMIT 1
                        """, (row['ticket'],))  # Consulta directa por ticket
                        registro = cursor2.fetchone()
                        conn2.close()

                        if registro:
                            nombre_archivo, archivo_url = registro
                            if archivo_url and archivo_url.strip():
                                st.markdown(
                                    f"[📎 Descargar presupuesto ({nombre_archivo})]({archivo_url})",
                                    unsafe_allow_html=True
                                )
                            else:
                                st.caption("📭 No hay presupuesto enviado aún para esta viabilidad.")
                        else:
                            st.caption("📭 No hay presupuesto enviado aún para esta viabilidad.")
                    except Exception as e:
                        st.warning(f"⚠️ Error al buscar presupuesto: {e}")

                    # --------------- CONFIRMAR ----------------
                    with col_ok:
                        comentarios_gestor = st.text_area(
                            "💬 Comentarios gestor",
                            key=f"coment_{row.id}",
                            placeholder="Añade comentarios sobre esta viabilidad (opcional)..."
                        )
                        if st.button("✅Confirmar", key=f"ok_{row.id}"):
                            with st.spinner("Confirmando viabilidad…"):
                                conn.execute(
                                    """
                                    UPDATE viabilidades
                                    SET confirmacion_rafa = 'OK',
                                        comentarios_gestor = ?
                                    WHERE id = ?
                                    """,
                                    (comentarios_gestor, row.id)
                                )
                                conn.commit()

                                for email_admin in admins:
                                    correo_confirmacion_viab_admin(
                                        destinatario=email_admin,
                                        id_viab=row.id,
                                        comercial_orig=row.comercial_reporta
                                    )

                            st.toast(f"Viabilidad {row.id} confirmada.")
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

                                st.toast(f"Viabilidad {row.id} reasignada a {nuevo_com}.")

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
            # Rafa Sanz no ve a Juan Pablo, Roberto, Nestor, etc.
            comerciales_excluir = ["juan pablo", "roberto", "nestor", "Comercial2", "Comercial3"]
            viabilidades['usuario'] = viabilidades['usuario'].fillna("").str.strip().str.lower()
            viabilidades = viabilidades[~viabilidades['usuario'].isin([c.lower() for c in comerciales_excluir])]

        # 📋 Mostrar tabla resultante
        st.info("ℹ️ Listado completo de viabilidades y su estado actual.")
        st.dataframe(viabilidades, width='stretch')

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
                        comercial,
                        olt,  # nuevo campo
                        apartment_id  # nuevo campo
                    ))

                    st.toast(f"✅ Viabilidad guardada correctamente.\n\n📌 **Ticket:** `{ticket}`")

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
        st.toast(
            f"📧 Se ha enviado una notificación a los administradores: {', '.join(emails_admin)} sobre la viabilidad completada."
        )
    else:
        st.warning("⚠️ No se encontró ningún email de administrador, no se pudo enviar la notificación.")

    # Mostrar mensaje de éxito en Streamlit
    st.toast("✅ Los cambios para la viabilidad han sido guardados correctamente")

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
        viabilidades_filtradas['fecha_viabilidad'] = pd.to_datetime(
            viabilidades_filtradas['fecha_viabilidad'], errors='coerce'
        )
    else:
        datos_filtrados = datos_uis.copy()
        ofertas_filtradas = total_ofertas.copy()
        viabilidades_filtradas = viabilidades.copy()

    # ---------------------------------------------------------------
    # Función de descarga (sin tocar)
    # ---------------------------------------------------------------
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

    # ---------------------------------------------------------------
    # Lógica de descarga según la selección
    # ---------------------------------------------------------------
    if dataset_opcion == "Datos":
        log_trazabilidad(username, "Descarga de datos", "Usuario descargó los datos.")

        # ✅ Consulta directa a la base de datos para traer 'cto'
        try:
            conn = get_db_connection()
            query = ("SELECT apartment_id, address_id, provincia, municipio, poblacion, vial, numero, parcela_catastral, letra, cp, cto_id, olt, latitud, longitud"
                     ", tipo_olt_rental   FROM datos_uis;")
            df_db = pd.read_sql_query(query, conn)
            conn.close()

            # Aplica los mismos filtros de arriba si es necesario
            if username == "juan":
                df_db = df_db[df_db['provincia'].str.strip().str.lower().isin(["lugo", "asturias"])]

            # Exportar el DataFrame directamente (ya incluye CTO)
            descargar_excel({"Datos Gestor": df_db}, nombre_archivo_final)

        except Exception as e:
            st.toast(f"❌ Error al obtener los datos de la base de datos: {e}")

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