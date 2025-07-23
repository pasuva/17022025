import streamlit as st
from folium.plugins import MarkerCluster
import pandas as pd
import os, re, time, folium, sqlitecloud
from streamlit_folium import st_folium
import streamlit.components.v1 as components
from datetime import datetime
from modules import login
from folium.plugins import Geocoder
from modules.cloudinary import upload_image_to_cloudinary
from modules.notificaciones import correo_oferta_comercial, correo_viabilidad_comercial
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


def guardar_en_base_de_datos(oferta_data, imagen_incidencia, apartment_id):
    """Guarda o actualiza la oferta en SQLite y almacena la imagen en Cloudinary si es necesario."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Verificar si el apartment_id existe en la base de datos
        cursor.execute("SELECT COUNT(*) FROM comercial_rafa WHERE apartment_id = ?", (apartment_id,))
        if cursor.fetchone()[0] == 0:
            st.error("❌ El Apartment ID no existe en la base de datos. No se puede guardar ni actualizar la oferta.")
            conn.close()
            return

        st.info(f"⚠️ El Apartment ID {apartment_id} está asignado, se actualizarán los datos.")

        # Subir la imagen a Cloudinary si hay incidencia
        imagen_url = None
        if oferta_data["incidencia"] == "Sí" and imagen_incidencia:
            # Extraer la extensión del archivo para formar un nombre adecuado
            extension = os.path.splitext(imagen_incidencia.name)[1]
            filename = f"{apartment_id}{extension}"
            imagen_url = upload_image_to_cloudinary(imagen_incidencia, filename)

        comercial_logueado = st.session_state.get("username", None)

        # Actualizar los datos en la base de datos, usando imagen_url en lugar de imagen_path
        cursor.execute('''UPDATE comercial_rafa SET 
                            provincia = ?, municipio = ?, poblacion = ?, vial = ?, numero = ?, letra = ?, 
                            cp = ?, latitud = ?, longitud = ?, nombre_cliente = ?, telefono = ?, 
                            direccion_alternativa = ?, observaciones = ?, serviciable = ?, motivo_serviciable = ?, 
                            incidencia = ?, motivo_incidencia = ?, fichero_imagen = ?, fecha = ?, Tipo_Vivienda = ?, 
                            Contrato = ?, comercial = ?
                          WHERE apartment_id = ?''',
                       (
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

        conn.commit()
        conn.close()
        st.success("✅ ¡Oferta actualizada con éxito en la base de datos!")

        # Enviar notificación al administrador
        # Obtener todos los correos de usuarios con rol 'admin' o 'comercial_jefe'
        cursor.execute("SELECT email FROM usuarios WHERE role IN ('admin', 'comercial_jefe')")
        destinatario_admin = [fila[0] for fila in cursor.fetchall()]
        descripcion_oferta = f"Se ha actualizado una oferta para el apartamento con ID {apartment_id}.\n\nDetalles: {oferta_data}"
        for correo in destinatario_admin:
            correo_oferta_comercial(correo, apartment_id, descripcion_oferta)

        st.success("✅ Oferta actualizada con éxito")
        st.info(f"📧 Se ha enviado una notificación a {len(destinatario_admin)} destinatario(s) con rol 'admin' o 'comercial_jefe', sobre la oferta actualizada.")

        # Registrar trazabilidad
        log_trazabilidad(st.session_state["username"], "Actualizar Oferta",
                         f"Oferta actualizada para Apartment ID: {apartment_id}")

    except Exception as e:
        st.error(f"❌ Error al guardar o actualizar la oferta en la base de datos: {e}")

    except Exception as e:
        st.error(f"❌ Error al guardar la oferta en la base de datos: {e}")

def comercial_dashboard():
    """Muestra el mapa y formulario de Ofertas Comerciales para el comercial logueado."""
    controller = CookieController(key="cookies")
    st.sidebar.title("Mapa de Ubicaciones")
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
                    margin-bottom: 30px;
                    text-align: center;
                    margin-left: auto;
                    margin-right: auto;
                }
            </style>
            <div class="user-circle">👤</div>
            <div>Rol: Comercial</div>
        """, unsafe_allow_html=True)
        st.sidebar.write(f"Bienvenido, {st.session_state['username']}")
        st.sidebar.markdown("---")
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
            st.session_state["login_ok"] = False
            st.session_state["username"] = ""
            st.session_state["role"] = ""
            st.session_state["session_id"] = ""

            st.success("✅ Has cerrado sesión correctamente. Redirigiendo al login...")
            st.rerun()

    # Se utiliza un ícono de marcador por defecto (sin comprobación de cto_con_proyecto)
    marker_icon_type = 'info-sign'

    if menu_opcion == "Ofertas Comerciales":
        st.markdown("""
         🟢 Serviciable (Finalizado)
         🟠 Oferta (Contrato: Sí)
         ⚫ Oferta (No Interesado)
         🔵 Sin Oferta
         🔴 No Serviciable
        """)

        log_trazabilidad(comercial, "Visualización de Dashboard", "El comercial visualizó la sección de Ofertas Comerciales.")

        with st.spinner("⏳ Cargando los datos del comercial..."):
            try:
                conn = get_db_connection()
                query_tables = "SELECT name FROM sqlite_master WHERE type='table';"
                tables = pd.read_sql(query_tables, conn)

                if 'comercial_rafa' not in tables['name'].values:
                    st.error("❌ La tabla 'comercial_rafa' no se encuentra en la base de datos.")
                    conn.close()
                    return

                #query = "SELECT * FROM comercial_rafa WHERE LOWER(comercial) = LOWER(?)"
                query= """
                    SELECT cr.*
                    FROM comercial_rafa cr
                    LEFT JOIN datos_uis du ON cr.apartment_id = du.apartment_id
                    WHERE LOWER(cr.comercial) = LOWER(?)
                    AND (
                        LOWER(cr.serviciable) <> 'no'
                        OR UPPER(IFNULL(du.cto_con_proyecto, '')) = 'SI'
                    )
                    """
                df = pd.read_sql(query, conn, params=(comercial,))

                query_ofertas = "SELECT apartment_id, Contrato FROM comercial_rafa"
                ofertas_df = pd.read_sql(query_ofertas, conn)

                query_ams = "SELECT apartment_id FROM datos_uis WHERE LOWER(serviciable) = 'sí'"
                ams_df = pd.read_sql(query_ams, conn)
                conn.close()

                if df.empty:
                    st.warning("⚠️ No hay datos asignados a este comercial.")
                    return
            except Exception as e:
                st.error(f"❌ Error al cargar los datos de la base de datos: {e}")
                return

        if not isinstance(df, pd.DataFrame):
            st.error("❌ Los datos no se cargaron correctamente.")
            return

        for col in ['latitud', 'longitud', 'apartment_id']:
            if col not in df.columns:
                st.error(f"❌ No se encuentra la columna '{col}'.")
                return

        if "clicks" not in st.session_state:
            st.session_state.clicks = []

        location = get_user_location()
        if "ultima_lat" in st.session_state and "ultima_lon" in st.session_state:
            # Usar la última ubicación guardada
            lat, lon = st.session_state["ultima_lat"], st.session_state["ultima_lon"]
        elif location is None:
            st.warning("❌ No se pudo obtener la ubicación. Cargando el mapa en la ubicación predeterminada.")
            lat, lon = 43.463444, -3.790476
        else:
            lat, lon = location

        # Construir conjuntos y diccionarios para el estado de cada apartamento
        serviciable_set = set(ams_df["apartment_id"])
        contrato_dict = dict(zip(ofertas_df["apartment_id"], ofertas_df["Contrato"]))

        with st.spinner("⏳ Cargando datos..."):
            try:
                conn = get_db_connection()
                # Consulta para obtener apartamentos no servicibles
                query_serviciable = "SELECT apartment_id FROM comercial_rafa WHERE LOWER(serviciable) = 'no'"
                serviciable_no_df = pd.read_sql(query_serviciable, conn)
                serviciable_no_set = set(serviciable_no_df["apartment_id"])  # Set de IDs no servicibles

                with st.spinner("⏳ Cargando mapa..."):
                    m = folium.Map(location=[lat, lon], zoom_start=12, max_zoom=21,
                                   tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
                                   attr="Google")

                    Geocoder().add_to(m)

                    if m.options['zoom'] >= 15:  # Si el zoom es alto, desactivar clustering
                        cluster_layer = m
                    else:
                        cluster_layer = MarkerCluster(maxClusterRadius=5, minClusterSize=3).add_to(m)

                    # Calcular cuántos apartamentos comparten las mismas coordenadas
                    coord_counts = {}
                    for _, row in df.iterrows():
                        coord = (row['latitud'], row['longitud'])
                        coord_counts[coord] = coord_counts.get(coord, 0) + 1

                    for index, row in df.iterrows():
                        popup_text = f"🏠 {row['apartment_id']} - 📍 {row['latitud']}, {row['longitud']}"
                        apartment_id = row['apartment_id']

                        # Obtener estado de serviciable desde datos_uis (no desde comercial_rafa)
                        serviciable_val = str(row.get("serviciable", "")).strip().lower()

                        # Lógica para determinar el color del marcador
                        if serviciable_val == "no":
                            marker_color = 'red'  # 🔴 No Serviciable
                        elif serviciable_val == "si":
                            marker_color = 'green'  # 🟢 Serviciable
                        elif apartment_id in contrato_dict:
                            contrato_val = contrato_dict[apartment_id].strip().lower()
                            if contrato_val == "sí":
                                marker_color = 'orange'  # 🟠 Oferta (Contrato: Sí)
                            elif contrato_val == "no interesado":
                                marker_color = 'black'  # ⚫ Oferta (No Interesado)
                            else:
                                marker_color = 'blue'  # 🔵 Sin oferta ni contrato
                        else:
                            marker_color = 'blue'  # 🔵 Sin información

                        # Aplicar desplazamiento si hay coordenadas duplicadas
                        coord = (row['latitud'], row['longitud'])
                        offset_factor = coord_counts[coord]
                        if offset_factor > 1:
                            lat_offset = offset_factor * 0.00003
                            lon_offset = offset_factor * -0.00003
                        else:
                            lat_offset, lon_offset = 0, 0

                        new_lat = row['latitud'] + lat_offset
                        new_lon = row['longitud'] + lon_offset

                        # Reducir el contador para el siguiente marcador con las mismas coordenadas
                        coord_counts[coord] -= 1

                        folium.Marker(
                            location=[new_lat, new_lon],
                            popup=popup_text,
                            icon=folium.Icon(color=marker_color, icon=marker_icon_type)
                        ).add_to(cluster_layer)

                    map_data = st_folium(m, height=500, width=700)
                conn.close()
            except Exception as e:
                st.error(f"❌ Error al cargar los datos: {e}")

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
            SELECT v.provincia, v.municipio, v.poblacion, v.vial, v.numero, v.letra, v.cp, 
                   v.serviciable, v.coste, v.comentarios_comercial
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
            if df_viabilidades.empty:
                st.warning(f"⚠️ No hay viabilidades disponibles para el comercial '{comercial_usuario}'.")
            else:
                st.subheader("📋 Tabla de Viabilidades")
                st.dataframe(df_viabilidades, use_container_width=True)

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
            usuario
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?, ?)
    """, datos)
    conn.commit()

    # Obtener los emails de todos los administradores
    cursor.execute("SELECT email FROM usuarios WHERE role IN ('admin', 'comercial_jefe')")
    resultados = cursor.fetchall()  # Obtiene una lista de tuplas con cada email
    emails_admin = [fila[0] for fila in resultados]
    conn.close()

    # Información de la viabilidad
    ticket_id = datos[10]  # Asumiendo que 'ticket' está en la posición 10
    nombre_comercial = st.session_state.get("username")
    descripcion_viabilidad = (
        f"📝 Viabilidad para el ticket {ticket_id}:<br><br>"
        f"🧑‍💼 Comercial: {nombre_comercial}<br><br>"  # Nombre del comercial (usuario logueado)
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
        f"ℹ️ Por favor, revise todos los detalles de la viabilidad para asegurar que toda la información esté correcta. "
        f"Si tiene alguna pregunta o necesita más detalles, no dude en ponerse en contacto con el comercial {nombre_comercial} o con el equipo responsable."
    )

    # Enviar la notificación por correo a cada administrador
    if emails_admin:
        for email in emails_admin:
            correo_viabilidad_comercial(email, ticket_id, descripcion_viabilidad)
        st.info(
            f"📧 Se ha enviado una notificación a los administradores: {', '.join(emails_admin)} sobre la viabilidad completada.")
    else:
        st.warning("⚠️ No se encontró ningún email de administrador, no se pudo enviar la notificación.")

    # Mostrar mensaje de éxito en Streamlit
    st.success("✅ Los cambios para la viabilidad han sido guardados correctamente")


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
    map_data = st_folium(m, height=500, width=700)

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
                    st.session_state["username"]
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
    lat_value = click_data.get("lat", "N/D")
    lng_value = click_data.get("lng", "N/D")
    form_key = f"{lat_value}_{lng_value}"

    # Consultar la base de datos para las coordenadas seleccionadas.
    try:
        conn = get_db_connection()
        query = """
            SELECT * FROM datos_uis 
            WHERE latitud = ? AND longitud = ?
        """
        df = pd.read_sql(query, conn, params=(lat_value, lng_value))
        conn.close()
    except Exception as e:
        st.error(f"❌ Error al obtener datos de la base de datos: {e}")
        return

    # Si no se encontraron registros, avisar y salir
    if df.empty:
        st.warning("⚠️ No se encontraron datos para estas coordenadas.")
        return  # O podrías inicializar un formulario en blanco aquí

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
            guardar_en_base_de_datos(oferta_data, imagen_incidencia, apartment_id)

            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT email FROM usuarios WHERE role IN ('admin', 'comercial_jefe')")
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
    comercial_dashboard()