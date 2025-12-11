import streamlit as st
import pandas as pd
import os, time, sqlitecloud
from datetime import datetime
from modules import login
from modules.cloudinary import upload_image_to_cloudinary

from streamlit_option_menu import option_menu
from streamlit_cookies_controller import CookieController  # Se importa localmente
import warnings

from modules.notificaciones import notificar_creacion_ticket, notificar_asignacion_ticket

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


def tecnico_dashboard():
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
            <div class="user-info">Rol: Técnico</div>
            <div class="welcome-msg">Bienvenido, <strong>{username}</strong></div>
            <hr>
            """.replace("{username}", st.session_state.get('username', 'N/A')), unsafe_allow_html=True)

        menu_opcion = option_menu(
            menu_title=None,
            options=["Mis tickets asignados", "Crear ticket"],
            icons=["ticket-detailed", "ticket-fill"],
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
    if menu_opcion == "Mis tickets asignados":
        mis_tickets()

    # Sección de Viabilidades
    elif menu_opcion == "Crear ticket":
        crear_tickets()


def mis_tickets():
    """Muestra los tickets asignados al técnico actual."""
    st.title("🎫 Mis Tickets Asignados")
    st.markdown("---")

    # Obtener ID del usuario actual (técnico)
    user_id = st.session_state.get("user_id")
    if not user_id:
        # Intentar obtenerlo de la base de datos si no está en session_state
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM usuarios WHERE username = ?", (st.session_state['username'],))
            result = cursor.fetchone()
            conn.close()
            if result:
                user_id = result[0]
            else:
                st.toast("❌ No se pudo identificar al usuario.")
                return
        except Exception as e:
            st.toast(f"❌ Error al obtener información del usuario: {str(e)[:100]}")
            return

    try:
        conn = get_db_connection()

        # Consulta para obtener tickets asignados al técnico
        query = """
        SELECT 
            t.ticket_id,
            t.fecha_creacion,
            u.username as reportado_por,
            t.categoria,
            t.prioridad,
            t.estado,
            t.titulo,
            t.descripcion,
            t.comentarios,
            t.usuario_id as id_cliente
        FROM tickets t
        LEFT JOIN usuarios u ON t.usuario_id = u.id
        WHERE t.asignado_a = ?
        ORDER BY 
            CASE t.prioridad 
                WHEN 'Alta' THEN 1
                WHEN 'Media' THEN 2
                WHEN 'Baja' THEN 3
            END,
            t.fecha_creacion DESC
        """

        df_tickets = pd.read_sql(query, conn, params=(user_id,))
        conn.close()

        if df_tickets.empty:
            st.toast("✅ ¡Genial! No tienes tickets asignados en este momento.")
            st.info("Los tickets que te asigne el administrador aparecerán aquí.")
            return

        # --- RESUMEN ESTADÍSTICO ---
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("Total Asignados", len(df_tickets))
        with col2:
            alta = len(df_tickets[df_tickets['estado'] == 'Cancelado'])
            st.metric("Cancelado", alta, delta_color="inverse")
        with col3:
            en_progreso = len(df_tickets[df_tickets['estado'] == 'En Progreso'])
            st.metric("En Progreso", en_progreso)
        with col4:
            abiertos = len(df_tickets[df_tickets['estado'] == 'Abierto'])
            st.metric("Abiertos", abiertos)
        with col5:
            resuelto = len(df_tickets[df_tickets['estado'] == 'Resuelto'])
            st.metric("Resuelto", resuelto)

        # --- FILTROS RÁPIDOS ---
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            estado_filtro = st.multiselect(
                "Estado",
                options=df_tickets['estado'].unique(),
                default=df_tickets['estado'].unique()
            )
        with col_f2:
            prioridad_filtro = st.multiselect(
                "Prioridad",
                options=df_tickets['prioridad'].unique(),
                default=df_tickets['prioridad'].unique()
            )
        with col_f3:
            categoria_filtro = st.multiselect(
                "Categoría",
                options=df_tickets['categoria'].unique(),
                default=df_tickets['categoria'].unique()
            )

        # Aplicar filtros
        mask = (
                df_tickets['estado'].isin(estado_filtro) &
                df_tickets['prioridad'].isin(prioridad_filtro) &
                df_tickets['categoria'].isin(categoria_filtro)
        )
        df_filtrado = df_tickets[mask]

        st.markdown(f"### 📋 Tickets Asignados ({len(df_filtrado)})")

        # Mostrar cada ticket
        for _, ticket in df_filtrado.iterrows():
            # Calcular días desde creación
            fecha_creacion = pd.to_datetime(ticket['fecha_creacion'])
            dias_transcurridos = (datetime.now() - fecha_creacion).days

            # Determinar color de borde según antigüedad
            if dias_transcurridos > 7:
                borde_color = "#FF0000"  # Rojo: muy antiguo
                antiguedad_texto = f"⚠️ {dias_transcurridos} días"
            elif dias_transcurridos > 3:
                borde_color = "#FF9900"  # Naranja: moderadamente antiguo
                antiguedad_texto = f"📅 {dias_transcurridos} días"
            else:
                borde_color = "#4CAF50"  # Verde: reciente
                antiguedad_texto = f"🆕 {dias_transcurridos} días"

            # Icono según prioridad
            prioridad_icono = {
                'Alta': '🔴',
                'Media': '🟡',
                'Baja': '🟢'
            }.get(ticket['prioridad'], '⚪')

            # Icono según estado
            estado_icono = {
                'Abierto': '📥',
                'En Progreso': '⚙️',
                'Resuelto': '✅',
                'Cancelado': '🔒'
            }.get(ticket['estado'], '📋')

            with st.expander(f"{estado_icono} {prioridad_icono} Ticket #{ticket['ticket_id']}: {ticket['titulo']}"):
                # Encabezado del ticket
                col_head1, col_head2 = st.columns([2, 1])

                with col_head1:
                    st.markdown(f"**📅 Creado:** {fecha_creacion.strftime('%d/%m/%Y %H:%M')}")
                    st.markdown(f"**👤 Reportado por:** {ticket['reportado_por']}")
                    st.markdown(f"**🏷️ Categoría:** {ticket['categoria']}")

                with col_head2:
                    st.markdown(f"**🚨 Prioridad:** {ticket['prioridad']}")
                    st.markdown(f"**📊 Estado:** {ticket['estado']}")
                    st.markdown(f"**⏳ Antigüedad:** {antiguedad_texto}")

                st.markdown("---")

                # Pestañas para contenido
                tab_desc, tab_com, tab_acc = st.tabs(["📄 Descripción", "💬 Comentarios", "🔧 Acciones"])

                with tab_desc:
                    st.markdown("**Descripción original:**")
                    st.info(ticket['descripcion'])

                with tab_com:
                    if ticket['comentarios']:
                        st.markdown("**Historial de comentarios:**")
                        # Dividir comentarios por saltos de línea dobles
                        comentarios = ticket['comentarios'].split('\n\n')
                        for comentario in comentarios:
                            if comentario.strip():
                                # Detectar si es comentario interno o del cliente
                                if '(cliente):' in comentario or 'Ticket creado por' in comentario:
                                    st.info(comentario.strip())
                                else:
                                    st.warning(comentario.strip())
                    else:
                        st.info("No hay comentarios aún.")

                    # Formulario para añadir comentario
                    st.markdown("---")
                    st.markdown("**💬 Añadir comentario:**")

                    with st.form(key=f"comentario_form_{ticket['ticket_id']}"):
                        nuevo_comentario = st.text_area(
                            "Escribe tu comentario:",
                            placeholder="Actualización, solución, preguntas para el cliente...",
                            height=120,
                            key=f"comentario_{ticket['ticket_id']}"
                        )

                        tipo_comentario = st.selectbox(
                            "Tipo de comentario:",
                            ["Actualización", "Pregunta al cliente", "Solución", "Esperando respuesta"],
                            key=f"tipo_{ticket['ticket_id']}"
                        )

                        es_interno = st.checkbox(
                            "Comentario interno (solo visible para equipo)",
                            key=f"interno_{ticket['ticket_id']}"
                        )

                        enviar_comentario = st.form_submit_button(
                            "💬 Enviar comentario",
                            use_container_width=True
                        )

                        if enviar_comentario and nuevo_comentario.strip():
                            try:
                                conn = get_db_connection()
                                cursor = conn.cursor()

                                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
                                usuario = st.session_state.get('username', 'Técnico')
                                tipo = f"[{tipo_comentario}]" if not es_interno else f"[{tipo_comentario} - INTERNO]"

                                comentario_formateado = f"\n\n[{timestamp}] {usuario} {tipo}:\n{nuevo_comentario.strip()}"

                                cursor.execute("""
                                    UPDATE tickets 
                                    SET comentarios = COALESCE(comentarios || ?, ?)
                                    WHERE ticket_id = ?
                                """, (
                                    comentario_formateado,
                                    f"[{timestamp}] {usuario} {tipo}:\n{nuevo_comentario.strip()}",
                                    ticket['ticket_id']
                                ))

                                conn.commit()
                                conn.close()

                                log_trazabilidad(
                                    usuario,
                                    "Comentario en ticket (técnico)",
                                    f"Añadió comentario al ticket #{ticket['ticket_id']}"
                                )

                                st.toast("✅ Comentario añadido")
                                st.rerun()

                            except Exception as e:
                                st.toast(f"❌ Error al añadir comentario: {str(e)[:100]}")

                with tab_acc:
                    st.markdown("**⚡ Acciones disponibles:**")

                    # Cambiar estado
                    col_est1, col_est2 = st.columns(2)
                    with col_est1:
                        nuevo_estado = st.selectbox(
                            "Cambiar estado:",
                            ["Abierto", "En Progreso", "Resuelto", "Cancelado"],
                            index=0 if ticket['estado'] == 'Abierto' else
                            1 if ticket['estado'] == 'En Progreso' else
                            2 if ticket['estado'] == 'Resuelto' else 3,
                            key=f"cambiar_estado_{ticket['ticket_id']}"
                        )

                    with col_est2:
                        if st.button("🔄 Actualizar estado",
                                     key=f"btn_estado_{ticket['ticket_id']}",
                                     use_container_width=True):
                            if nuevo_estado != ticket['estado']:
                                actualizar_estado_ticket(ticket['ticket_id'], nuevo_estado)

                                # Añadir comentario automático
                                conn = get_db_connection()
                                cursor = conn.cursor()
                                cursor.execute("""
                                    UPDATE tickets 
                                    SET comentarios = COALESCE(comentarios || '\n\n', '') || ?
                                    WHERE ticket_id = ?
                                """, (
                                    f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] {st.session_state['username']} cambió el estado a '{nuevo_estado}'.",
                                    ticket['ticket_id']
                                ))
                                conn.commit()
                                conn.close()

                                st.toast(f"✅ Estado cambiado a '{nuevo_estado}'")
                                st.rerun()

                    st.markdown("---")

                    # Otras acciones
                    col_acc1, col_acc2 = st.columns(2)
                    with col_acc1:
                        if st.button("📧 Solicitar más info",
                                     key=f"solicitar_{ticket['ticket_id']}",
                                     use_container_width=True):
                            try:
                                conn = get_db_connection()
                                cursor = conn.cursor()

                                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
                                mensaje = f"\n\n[{timestamp}] {st.session_state['username']} [PREGUNTA AL CLIENTE]:\nSolicito más información para poder resolver este ticket. Por favor, proporcione detalles adicionales sobre el problema."

                                cursor.execute("""
                                    UPDATE tickets 
                                    SET comentarios = COALESCE(comentarios || ?, ?),
                                        estado = 'En Progreso'
                                    WHERE ticket_id = ?
                                """, (
                                    mensaje,
                                    f"[{timestamp}] {st.session_state['username']} [PREGUNTA AL CLIENTE]:\nSolicito más información para poder resolver este ticket. Por favor, proporcione detalles adicionales sobre el problema.",
                                    ticket['ticket_id']
                                ))

                                conn.commit()
                                conn.close()

                                st.toast("✅ Solicitud de información enviada")
                                st.rerun()

                            except Exception as e:
                                st.toast(f"❌ Error: {str(e)[:100]}")

                    with col_acc2:
                        if st.button("📋 Ver historial completo",
                                     key=f"historial_{ticket['ticket_id']}",
                                     use_container_width=True):
                            # Aquí podríamos expandir para mostrar historial detallado
                            st.info("El historial completo se muestra en la pestaña de Comentarios")

        # --- RESUMEN AL FINAL ---
        st.markdown("---")
        st.markdown("### 📈 Estadísticas de Mis Tickets")

        if len(df_filtrado) > 0:
            col_stat1, col_stat2, col_stat3 = st.columns(3)

            with col_stat1:
                # Distribución por estado
                distribucion_estado = df_filtrado['estado'].value_counts()
                st.markdown("**Por estado:**")
                for estado, cantidad in distribucion_estado.items():
                    st.write(f"{estado}: {cantidad}")

            with col_stat2:
                # Distribución por prioridad
                distribucion_prioridad = df_filtrado['prioridad'].value_counts()
                st.markdown("**Por prioridad:**")
                for prioridad, cantidad in distribucion_prioridad.items():
                    st.write(f"{prioridad}: {cantidad}")

            with col_stat3:
                # Tiempo promedio abierto
                df_abiertos = df_filtrado[df_filtrado['estado'].isin(['Abierto', 'En Progreso'])]
                if len(df_abiertos) > 0:
                    df_abiertos['dias_abierto'] = df_abiertos['fecha_creacion'].apply(
                        lambda x: (datetime.now() - pd.to_datetime(x)).days
                    )
                    promedio_dias = df_abiertos['dias_abierto'].mean()
                    st.markdown("**Promedio días abierto:**")
                    st.write(f"{promedio_dias:.1f} días")

    except Exception as e:
        st.toast(f"⚠️ Error al cargar tickets: {str(e)[:200]}")


def crear_tickets():
    """Permite al técnico crear tickets internos o para otros usuarios."""
    st.title("➕ Crear Ticket (Modo Técnico)")
    st.markdown("---")

    st.info("""
    **Modo Técnico:** 
    Como técnico, puedes crear tickets para:
    - 📋 **Problemas internos** (equipo, servidores, sistemas)
    - 🔧 **Seguimiento de tareas** 
    - 👥 **Derivar trabajo** a otro compañero
    - 📝 **Documentar incidencias** técnicas
    """)

    # Variable para controlar si mostrar el botón después de crear
    ticket_creado_exitosamente = False
    ticket_id_creado = None
    resumen_ticket = None

    with st.form("form_ticket_tecnico"):
        # Sección 1: Información básica
        st.markdown("### 📝 Información del Ticket")

        titulo = st.text_input(
            "**Título/Asunto** *",
            placeholder="Ej: Problema con el servidor de base de datos",
            help="Describe brevemente el problema o tarea"
        )

        col_cat, col_pri = st.columns(2)
        with col_cat:
            categoria = st.selectbox(
                "**Categoría** *",
                [
                    "Problema Técnico Interno",
                    "Tarea de Mantenimiento",
                    "Solicitud de Equipo",
                    "Documentación",
                    "Capacitación",
                    "Otro"
                ]
            )

        with col_pri:
            prioridad = st.selectbox(
                "**Prioridad** *",
                ["Baja", "Media", "Alta"],
                help="Considera el impacto en el servicio"
            )

        # Sección 2: Asignación (opcional)
        st.markdown("### 👤 Asignación")

        try:
            conn = get_db_connection()
            # Obtener todos los usuarios que pueden recibir tickets (incluyendo email)
            usuarios_df = pd.read_sql("""
                SELECT id, username, role, email 
                FROM usuarios 
                WHERE role IN ('admin', 'tecnico', 'agent', 'soporte', 'comercial')
                ORDER BY username
            """, conn)
            conn.close()

            if not usuarios_df.empty:
                opciones_usuario = ["Sin asignar (abierto)"] + usuarios_df['username'].tolist()
                usuario_asignado = st.selectbox(
                    "Asignar a (opcional):",
                    options=opciones_usuario,
                    index=0,
                    help="Deja 'Sin asignar' para que el administrador lo asigne después"
                )

                asignado_id = None
                asignado_email = None
                asignado_username = None

                if usuario_asignado != "Sin asignar (abierto)":
                    usuario_info = usuarios_df[usuarios_df['username'] == usuario_asignado].iloc[0]
                    asignado_id = usuario_info['id']
                    asignado_email = usuario_info['email']
                    asignado_username = usuario_asignado
            else:
                st.warning("No se encontraron usuarios para asignar")
                usuario_asignado = "Sin asignar (abierto)"
                asignado_id = None
                asignado_email = None
                asignado_username = None

        except Exception as e:
            st.warning(f"No se pudo cargar la lista de usuarios: {str(e)[:100]}")
            usuario_asignado = "Sin asignar (abierto)"
            asignado_id = None
            asignado_email = None
            asignado_username = None

        # Sección 3: Descripción detallada
        st.markdown("### 📄 Descripción Detallada *")
        descripcion = st.text_area(
            label="",
            placeholder="""Describe el problema o tarea con todo detalle:

• ¿Qué está ocurriendo?
• ¿Cuándo comenzó?
• ¿Qué sistemas/componentes están afectados?
• ¿Qué impacto tiene?
• ¿Qué se ha intentado hasta ahora?

Si es una tarea:
• Objetivo:
• Pasos requeridos:
• Recursos necesarios:
• Plazo estimado:""",
            height=250,
            label_visibility="collapsed"
        )

        # Sección 4: Información adicional
        with st.expander("🔧 Información Técnica (opcional)"):
            col_tech1, col_tech2 = st.columns(2)
            with col_tech1:
                sistema_afectado = st.selectbox(
                    "Sistema afectado:",
                    ["Base de datos", "Servidor web", "API", "Frontend", "Backend", "Infraestructura", "Otro"]
                )

                entorno = st.selectbox(
                    "Entorno:",
                    ["Producción", "Desarrollo", "Testing", "Staging"]
                )

            with col_tech2:
                urgencia = st.select_slider(
                    "Nivel de urgencia:",
                    options=["Baja", "Media", "Alta", "Crítica"]
                )

                tiempo_estimado = st.number_input(
                    "Tiempo estimado (horas):",
                    min_value=0.5,
                    max_value=100.0,
                    value=2.0,
                    step=0.5
                )

        st.markdown("---")
        st.markdown("**\* Campos obligatorios**")

        # Botones DEL FORMULARIO (solo st.form_submit_button)
        col_btn1, col_btn2 = st.columns([1, 1])
        with col_btn1:
            enviar = st.form_submit_button(
                "✅ **Crear Ticket**",
                type="primary",
                use_container_width=True
            )
        with col_btn2:
            cancelar = st.form_submit_button(
                "❌ **Cancelar**",
                use_container_width=True
            )

    # #########################
    # FUERA DEL FORMULARIO - INDENTACIÓN CRÍTICA
    # #########################

    # Manejar la cancelación
    if 'cancelar' in locals() and cancelar:
        st.info("Formulario cancelado.")
        st.rerun()

    # Manejar el envío del formulario
    if enviar:
        if not titulo or not descripcion:
            st.toast("⚠️ Por favor, completa todos los campos obligatorios (*)")
        else:
            try:
                # Obtener ID del técnico actual
                user_id = st.session_state.get("user_id")
                if not user_id:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("SELECT id FROM usuarios WHERE username = ?", (st.session_state['username'],))
                    result = cursor.fetchone()
                    if result:
                        user_id = int(result[0])
                    else:
                        st.toast("❌ No se pudo identificar al usuario.")
                        return
                    conn.close()

                # Determinar estado inicial
                if asignado_id:
                    estado_inicial = "En Progreso"
                    comentario_asignacion = f"Asignado inicialmente a {asignado_username}"
                    asignado_id = int(asignado_id) if asignado_id is not None else None
                else:
                    estado_inicial = "Abierto"
                    comentario_asignacion = "Creado por técnico, pendiente de asignación"

                # Crear descripción completa
                descripcion_completa = descripcion

                # Añadir información técnica si se proporcionó
                if 'sistema_afectado' in locals():
                    info_tecnica = "\n\n--- INFORMACIÓN TÉCNICA ---\n"
                    info_tecnica += f"• Sistema afectado: {sistema_afectado}\n"
                    info_tecnica += f"• Entorno: {entorno}\n"
                    info_tecnica += f"• Nivel de urgencia: {urgencia}\n"
                    info_tecnica += f"• Tiempo estimado: {tiempo_estimado} horas\n"
                    info_tecnica += f"• Creado por técnico: {st.session_state['username']}\n"
                    descripcion_completa += info_tecnica

                # Insertar ticket
                conn = get_db_connection()
                cursor = conn.cursor()
                user_id = int(user_id) if user_id is not None else None

                if asignado_id:
                    cursor.execute("""
                        INSERT INTO tickets 
                        (usuario_id, categoria, prioridad, estado, asignado_a, titulo, descripcion)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        user_id,
                        categoria,
                        prioridad,
                        estado_inicial,
                        asignado_id,
                        titulo,
                        descripcion_completa
                    ))
                else:
                    cursor.execute("""
                        INSERT INTO tickets 
                        (usuario_id, categoria, prioridad, estado, titulo, descripcion)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        user_id,
                        categoria,
                        prioridad,
                        estado_inicial,
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
                    f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] {comentario_asignacion} por {st.session_state['username']}.",
                    ticket_id
                ))

                # NOTIFICACIÓN: Enviar correo si el ticket fue asignado
                if asignado_id and asignado_email:
                    try:
                        # Obtener información del creador para posibles notificaciones adicionales
                        cursor.execute("SELECT email, username FROM usuarios WHERE id = ?", (user_id,))
                        creador_info = cursor.fetchone()

                        ticket_info = {
                            'ticket_id': ticket_id,
                            'titulo': titulo,
                            'asignado_por': st.session_state['username'],
                            'prioridad': prioridad,
                            'categoria': categoria,
                            'enlace': f"https://tu-dominio.com/ticket/{ticket_id}"
                        }

                        # Notificar al agente asignado
                        notificar_asignacion_ticket(asignado_email, ticket_info)

                        # Opcional: Notificar al creador que su ticket fue creado y asignado
                        if creador_info and creador_info[0]:
                            notificacion_creacion = {
                                'ticket_id': ticket_id,
                                'titulo': titulo,
                                'creado_por': st.session_state['username'],
                                'prioridad': prioridad,
                                'categoria': categoria,
                                'estado': estado_inicial,
                                'descripcion': descripcion[:100] + '...' if len(descripcion) > 100 else descripcion,
                                'enlace': f"https://tu-dominio.com/ticket/{ticket_id}"
                            }
                            notificar_creacion_ticket(creador_info[0], notificacion_creacion)

                        st.toast(f"📧 Notificación de asignación enviada a {asignado_username}")

                    except Exception as e:
                        st.warning(f"No se pudo enviar la notificación por correo: {str(e)[:100]}")
                        # Continuar con el flujo aunque falle la notificación

                # Si no fue asignado, notificar al administrador
                elif not asignado_id:
                    try:
                        # Obtener email del administrador
                        cursor.execute("SELECT email FROM usuarios WHERE role = 'admin' LIMIT 1")
                        admin_result = cursor.fetchone()

                        if admin_result and admin_result[0]:
                            ticket_info = {
                                'ticket_id': ticket_id,
                                'titulo': titulo,
                                'creado_por': st.session_state['username'],
                                'prioridad': prioridad,
                                'categoria': categoria,
                                'estado': estado_inicial,
                                'descripcion': descripcion[:100] + '...' if len(descripcion) > 100 else descripcion,
                                'enlace': f"https://tu-dominio.com/ticket/{ticket_id}"
                            }
                            notificar_creacion_ticket(admin_result[0], ticket_info)
                            st.toast("📧 Notificación enviada al administrador para asignación")

                    except Exception as e:
                        st.warning(f"No se pudo enviar notificación al administrador: {str(e)[:100]}")

                conn.commit()
                conn.close()

                # Registrar en trazabilidad
                log_trazabilidad(
                    st.session_state["username"],
                    "Creación de ticket (técnico)",
                    f"Ticket técnico #{ticket_id} creado: {titulo}"
                )

                # Mostrar éxito
                st.toast(f"✅ **Ticket #{ticket_id} creado correctamente**")

                # Guardar información para mostrar el resumen
                ticket_creado_exitosamente = True
                ticket_id_creado = ticket_id
                resumen_ticket = {
                    "titulo": titulo,
                    "categoria": categoria,
                    "prioridad": prioridad,
                    "estado": estado_inicial,
                    "usuario_asignado": asignado_username if asignado_id else None,
                    "asignado_id": asignado_id
                }

            except Exception as e:
                st.toast(f"❌ Error al crear el ticket: {str(e)[:200]}")

    # #########################
    # SECCIÓN FUERA DEL FORMULARIO
    # #########################

    # Mostrar resumen después de crear el ticket
    if ticket_creado_exitosamente and resumen_ticket:
        with st.expander("📋 Ver resumen del ticket creado", expanded=True):
            col_res1, col_res2 = st.columns(2)
            with col_res1:
                st.markdown(f"**🎫 ID:** #{ticket_id_creado}")
                st.markdown(f"**📝 Asunto:** {resumen_ticket['titulo']}")
                st.markdown(f"**🏷️ Categoría:** {resumen_ticket['categoria']}")
                st.markdown(f"**🚨 Prioridad:** {resumen_ticket['prioridad']}")

            with col_res2:
                st.markdown(f"**📊 Estado:** {resumen_ticket['estado']}")
                st.markdown(f"**👤 Creado por:** {st.session_state['username']}")
                if resumen_ticket['usuario_asignado']:
                    st.markdown(f"**👥 Asignado a:** {resumen_ticket['usuario_asignado']}")
                else:
                    st.markdown(f"**👥 Asignado a:** Pendiente")
                st.markdown(f"**📅 Fecha:** {datetime.now().strftime('%d/%m/%Y %H:%M')}")

        st.markdown("---")

        # Botón para ver tickets asignados (FUERA del formulario)
        if st.button("📋 Ver mis tickets asignados", use_container_width=True):
            # Aquí puedes navegar a otra vista o filtrar tickets
            # Por ejemplo, establecer un estado de sesión
            st.session_state['ver_mis_tickets'] = True
            st.rerun()


def actualizar_estado_ticket(ticket_id, nuevo_estado):
    """Actualiza el estado de un ticket y registra la acción."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Primero, obtener información actual del ticket para el log
        cursor.execute("SELECT titulo, estado FROM tickets WHERE ticket_id = ?", (ticket_id,))
        ticket_info = cursor.fetchone()

        if not ticket_info:
            st.toast(f"❌ Ticket #{ticket_id} no encontrado")
            return False

        titulo_ticket, estado_anterior = ticket_info

        # Verificar si el campo fecha_cierre existe en la tabla
        cursor.execute("PRAGMA table_info(tickets)")
        columnas = cursor.fetchall()
        column_names = [col[1] for col in columnas]
        tiene_fecha_cierre = 'fecha_cierre' in column_names

        # Si el estado es 'Resuelto' o 'Cancelado', intentamos añadir fecha_cierre si el campo existe
        if nuevo_estado in ['Resuelto', 'Cancelado'] and tiene_fecha_cierre:
            try:
                cursor.execute("""
                    UPDATE tickets 
                    SET estado = ?, fecha_cierre = CURRENT_TIMESTAMP 
                    WHERE ticket_id = ?
                """, (nuevo_estado, ticket_id))
            except Exception as e:
                # Si falla, solo actualizar estado
                cursor.execute("""
                    UPDATE tickets 
                    SET estado = ? 
                    WHERE ticket_id = ?
                """, (nuevo_estado, ticket_id))
        else:
            # Actualizar solo el estado
            cursor.execute("""
                UPDATE tickets 
                SET estado = ? 
                WHERE ticket_id = ?
            """, (nuevo_estado, ticket_id))

        # Añadir comentario sobre el cambio de estado
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
        username = st.session_state.get("username", "Usuario")

        # Buscar si el usuario actual es el asignado o el creador para contexto
        cursor.execute("""
            SELECT asignado_a, usuario_id FROM tickets WHERE ticket_id = ?
        """, (ticket_id,))
        asignacion = cursor.fetchone()

        contexto = "técnico" if asignacion and asignacion[0] == st.session_state.get("user_id") else "usuario"

        comentario_cambio = f"\n\n[{timestamp}] {username} ({contexto}) cambió el estado de '{estado_anterior}' a '{nuevo_estado}'."

        cursor.execute("""
            UPDATE tickets 
            SET comentarios = COALESCE(comentarios || ?, ?)
            WHERE ticket_id = ?
        """, (
            comentario_cambio,
            f"[{timestamp}] {username} ({contexto}) cambió el estado de '{estado_anterior}' a '{nuevo_estado}'.",
            ticket_id
        ))

        conn.commit()
        conn.close()

        # Registrar en trazabilidad
        log_trazabilidad(
            username,
            "Actualización de estado de ticket",
            f"Cambió estado del ticket #{ticket_id} ('{titulo_ticket}') de '{estado_anterior}' a '{nuevo_estado}'"
        )

        # Mostrar notificación si estamos en un contexto Streamlit
        try:
            st.toast(f"✅ Ticket #{ticket_id} actualizado a '{nuevo_estado}'")
        except:
            pass  # Si no estamos en contexto Streamlit, ignoramos

        return True

    except Exception as e:
        error_msg = str(e)
        st.toast(f"⚠️ Error al actualizar ticket #{ticket_id}: {error_msg[:150]}")

        # Diagnosticar el error común
        if "no such table" in error_msg.lower():
            st.info("""
            **Posible solución:**
            1. Verifica que la tabla 'tickets' existe en la base de datos
            2. Ejecuta este SQL si no existe:
            ```sql
            CREATE TABLE IF NOT EXISTS tickets (
                ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
                usuario_id INTEGER NOT NULL,
                categoria TEXT NOT NULL,
                prioridad TEXT CHECK(prioridad IN ('Alta', 'Media', 'Baja')) DEFAULT 'Media',
                estado TEXT CHECK(estado IN ('Abierto', 'En Progreso', 'Resuelto', 'Cancelado')) DEFAULT 'Abierto',
                asignado_a INTEGER,
                titulo TEXT NOT NULL,
                descripcion TEXT NOT NULL,
                comentarios TEXT,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id),
                FOREIGN KEY (asignado_a) REFERENCES usuarios(id)
            );
            ```
            """)

        return False

if __name__ == "__main__":
    tecnico_dashboard()