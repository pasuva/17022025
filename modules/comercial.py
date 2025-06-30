import streamlit as st
import folium, os, re, time, sqlitecloud
from folium.plugins import MarkerCluster
import pandas as pd
from streamlit_folium import st_folium
from datetime import datetime
from modules import login
from folium.plugins import Geocoder
from modules.notificaciones import correo_oferta_comercial, correo_viabilidad_comercial
from streamlit_geolocation import streamlit_geolocation
from streamlit_option_menu import option_menu
from streamlit_cookies_controller import CookieController  # Se importa localmente
from modules.cloudinary import upload_image_to_cloudinary

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


def guardar_en_base_de_datos(oferta_data, imagen_incidencia):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM ofertas_comercial WHERE apartment_id = ?", (oferta_data["Apartment ID"],))
        existe = cursor.fetchone()[0] > 0

        imagen_url = None
        if oferta_data["incidencia"] == "Sí" and imagen_incidencia:
            extension = os.path.splitext(imagen_incidencia.name)[1]
            # Puedes definir un nombre basado en el apartment_id, por ejemplo
            filename = f"{oferta_data['Apartment ID']}{extension}"
            imagen_url = upload_image_to_cloudinary(imagen_incidencia)

        comercial = st.session_state["username"]  # Nombre del comercial actual
        print("Se va a guardar el comercial:", st.session_state.get("username"))

        if existe:
            cursor.execute('''UPDATE ofertas_comercial SET
                                provincia=?, municipio=?, poblacion=?, vial=?, numero=?, letra=?, cp=?, latitud=?, longitud=?,
                                nombre_cliente=?, telefono=?, direccion_alternativa=?, observaciones=?, serviciable=?,
                                motivo_serviciable=?, incidencia=?, motivo_incidencia=?, fichero_imagen=?, fecha=?, Tipo_Vivienda=?, Contrato=?, comercial=?
                              WHERE apartment_id=?''',
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
                               imagen_url,  # Aquí se guarda la URL obtenida de Cloudinary
                               oferta_data["fecha"].strftime('%Y-%m-%d %H:%M:%S'),
                               oferta_data["Tipo_Vivienda"],
                               oferta_data["Contrato"],
                               st.session_state.get("username"),
                               oferta_data["Apartment ID"]
                           ))
            mensaje = "✅ ¡Oferta modificada con éxito!"
        else:
            cursor.execute('''INSERT INTO ofertas_comercial (
                                apartment_id, provincia, municipio, poblacion, vial, numero, letra, cp, latitud, longitud,
                                nombre_cliente, telefono, direccion_alternativa, observaciones, serviciable,
                                motivo_serviciable, incidencia, motivo_incidencia, fichero_imagen, fecha, Tipo_Vivienda, Contrato, comercial
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                           (
                               oferta_data["Apartment ID"],
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
                               st.session_state.get("username")
                           ))
            mensaje = "✅ ¡Oferta enviada y guardada en la base de datos con éxito!"

        conn.commit()
        conn.close()
        st.success(mensaje)

        st.session_state["ultima_lat"] = oferta_data["Latitud"]
        st.session_state["ultima_lon"] = oferta_data["Longitud"]

        log_trazabilidad(st.session_state["username"], "Guardar Oferta",
                         f"Oferta guardada/modificada para Apartment ID: {oferta_data['Apartment ID']}")
    except Exception as e:
        st.error(f"❌ Error al guardar/modificar la oferta en la base de datos: {e}")


def comercial_dashboard():
    """Muestra el mapa y formulario de Ofertas Comerciales para el comercial logueado."""
    controller = CookieController(key="cookies")
    st.sidebar.title("📍 Mapa de Ubicaciones")
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
            icons=["bar-chart", "check-circle", "graph-up"],  # Íconos de Bootstrap
            menu_icon="list",  # Ícono del menú
            default_index=0,  # Opción seleccionada por defecto
            styles={
                "container": {"padding": "0px", "background-color": "#262730"},  # Fondo oscuro
                "icon": {"color": "#ffffff", "font-size": "18px"},  # Íconos blancos
                "nav-link": {
                    "color": "#ffffff", "font-size": "16px", "text-align": "left", "margin": "0px"
                },  # Texto en blanco sin margen extra
                "nav-link-selected": {
                    "background-color": "#0073e6", "color": "white"  # Resaltado azul en la opción seleccionada
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

                if 'datos_uis' not in tables['name'].values:
                    st.error("❌ La tabla 'datos_uis' no se encuentra en la base de datos.")
                    conn.close()
                    return

                # Si el comercial es Nestor, cargamos los datos de Roberto
                #if comercial.lower() == "nestor":
                #     comercial = "roberto"

                query = "SELECT * FROM datos_uis WHERE LOWER(COMERCIAL) = LOWER(?)"
                df = pd.read_sql(query, conn, params=(comercial,))

                query_ofertas = "SELECT apartment_id, serviciable, Contrato FROM ofertas_comercial"
                ofertas_df = pd.read_sql(query_ofertas, conn)

                query_ams = "SELECT apartment_id FROM datos_uis WHERE LOWER(site_operational_state) = 'serviciable'"
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

        for col in ['latitud', 'longitud', 'address_id', 'apartment_id']:
            if col not in df.columns:
                st.error(f"❌ No se encuentra la columna '{col}'.")
                return

        if "clicks" not in st.session_state:
            st.session_state.clicks = []

        location = get_user_location()

        if "ultima_lat" in st.session_state and "ultima_lon" in st.session_state:
            # 📍 Usar la última ubicación de la oferta guardada
            lat, lon = st.session_state["ultima_lat"], st.session_state["ultima_lon"]
        elif location is None:
            # ❌ Si no hay ubicación ni última oferta, usar la predeterminada
            st.warning("❌ No se pudo obtener la ubicación. Cargando el mapa en la ubicación predeterminada.")
            lat, lon = 43.463444, -3.790476
        else:
            lat, lon = location

        serviciable_set = set(ams_df["apartment_id"])
        contrato_dict = dict(zip(ofertas_df["apartment_id"], ofertas_df["Contrato"]))

        with st.spinner("⏳ Cargando mapa..."):
            m = folium.Map(location=[lat, lon], zoom_start=12, max_zoom=21,
                           tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
                           attr="Google")

            Geocoder().add_to(m)

            if m.options['zoom'] >= 15:  # Si el zoom es alto, desactivar clustering
                cluster_layer = m
            else:
                cluster_layer = MarkerCluster(maxClusterRadius=5, minClusterSize=3).add_to(m)

            # 📌 Detectar coordenadas duplicadas para aplicar desplazamiento ordenado
            coord_counts = {}
            for _, row in df.iterrows():
                coord = (row['latitud'], row['longitud'])
                coord_counts[coord] = coord_counts.get(coord, 0) + 1

            for index, row in df.iterrows():
                popup_text = f"🏠 {row['apartment_id']} - 📍 {row['latitud']}, {row['longitud']}"
                apartment_id = row['apartment_id']

                # Serviciable real: de datos_uis
                serviciable_val = str(row.get("serviciable", "")).strip().lower()

                # Info adicional desde ofertas
                oferta = ofertas_df[ofertas_df["apartment_id"] == apartment_id]
                contrato_val = str(oferta.iloc[0].get("Contrato", "")).strip().lower() if not oferta.empty else ""
                oferta_serviciable = str(
                    oferta.iloc[0].get("serviciable", "")).strip().lower() if not oferta.empty else ""

                # ✅ Prioridad correcta: primero el serviciable real de datos_uis
                if serviciable_val == "si":
                    marker_color = 'green'  # 🟢 Serviciable (datos_uis)
                elif oferta_serviciable == "no":
                    marker_color = 'red'  # 🔴 No Serviciable (desde oferta, si aplica)
                elif contrato_val == "sí":
                    marker_color = 'orange'  # 🟠 Oferta con contrato
                elif contrato_val == "no interesado":
                    marker_color = 'gray'  # ⚫ Oferta no interesado
                else:
                    marker_color = 'blue'  # 🔵 Sin oferta

                # 📌 Aplicar desplazamiento ordenado SOLO si hay coordenadas duplicadas
                coord = (row['latitud'], row['longitud'])
                offset_factor = coord_counts[coord]  # Cuántos hay en la misma posición
                if offset_factor > 1:
                    lat_offset = (offset_factor * 0.00003)  # Desplazamiento fijo incremental
                    lon_offset = (offset_factor * -0.00003)
                else:
                    lat_offset, lon_offset = 0, 0  # No mover si no está duplicado

                new_lat = row['latitud'] + lat_offset
                new_lon = row['longitud'] + lon_offset

                coord_counts[coord] -= 1  # Reducir el contador después de usarlo

                folium.Marker(
                    location=[new_lat, new_lon],  # 📍 Usamos coordenadas desplazadas si es necesario
                    popup=popup_text,
                    icon=folium.Icon(color=marker_color, icon=marker_icon_type)
                ).add_to(cluster_layer)

            map_data = st_folium(m, height=500, width=700)


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

    # Sección de Visualización de datos (en construcción o con otra funcionalidad)
    elif menu_opcion == "Visualización de Datos":
        st.subheader("📊 Datos de Ofertas con Contrato")

        # Verificar si el usuario ha iniciado sesión
        if "username" not in st.session_state:
            st.error("❌ No has iniciado sesión. Por favor, vuelve a la pantalla de inicio de sesión.")
            st.stop()

        comercial_usuario = st.session_state["username"]  # Obtener el comercial logueado

        try:
            conn = get_db_connection()
            # Consulta SQL con filtro por comercial logueado (primera tabla: ofertas_comercial)
            query_ofertas = """
                SELECT oc.apartment_id, oc.provincia, oc.municipio, oc.poblacion, 
                       oc.vial, oc.numero, oc.letra, oc.cp, oc.latitud, oc.longitud, oc.nombre_cliente, 
                       oc.telefono, oc.direccion_alternativa, oc.observaciones, oc.serviciable, oc.motivo_serviciable, oc.incidencia, oc.motivo_incidencia,
                       oc.fichero_imagen, oc.fecha, oc.Tipo_Vivienda, oc.Contrato,  du.site_operational_state
                FROM ofertas_comercial oc
                LEFT JOIN datos_uis du ON oc.apartment_id = du.apartment_id
                WHERE LOWER(oc.Contrato) = 'sí' 
                AND LOWER(du.comercial) = LOWER(?)
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

            # Consulta SQL para ofertas con "No Interesado"
            query_no_interesado = """
                SELECT oc.apartment_id, oc.provincia, oc.municipio, oc.poblacion, 
                       oc.vial, oc.numero, oc.letra, oc.cp, oc.latitud, oc.longitud, oc.nombre_cliente, 
                       oc.telefono, oc.direccion_alternativa, oc.observaciones, oc.serviciable, oc.motivo_serviciable, oc.incidencia, oc.motivo_incidencia,
                       oc.fichero_imagen, oc.fecha, oc.Tipo_Vivienda, oc.Contrato,  du.site_operational_state
                FROM ofertas_comercial oc
                LEFT JOIN datos_uis du ON oc.apartment_id = du.apartment_id
                WHERE LOWER(oc.Contrato) = 'no interesado' 
                AND LOWER(du.comercial) = LOWER(?)
                """

            df_no_interesado = pd.read_sql(query_no_interesado, conn, params=(comercial_usuario,))

            conn.close()

            # Verificar si hay datos para mostrar en la primera tabla (ofertas_comercial)
            if df_ofertas.empty:
                st.warning(f"⚠️ No hay ofertas con contrato activo para el comercial '{comercial_usuario}'.")
            else:
                st.subheader("📋 Tabla de Ofertas con Contrato Activo / Cliente Interesado")
                st.dataframe(df_ofertas, use_container_width=True)

            # Verificar si hay datos para mostrar en la segunda tabla (viabilidades)
            if df_viabilidades.empty:
                st.warning(f"⚠️ No hay viabilidades disponibles para el comercial '{comercial_usuario}'.")
            else:
                st.subheader("📋 Tabla de Viabilidades")
                st.dataframe(df_viabilidades, use_container_width=True)

            # Verificar si hay datos para mostrar en la tercera tabla (No Interesado)
            if df_no_interesado.empty:
                st.warning(f"⚠️ No hay ofertas marcadas como 'No Interesado' para el comercial '{comercial_usuario}'.")
            else:
                st.subheader("📋 Tabla de Ofertas No Interesadas")
                st.dataframe(df_no_interesado, use_container_width=True)

        except Exception as e:
            st.error(f"❌ Error al cargar los datos: {e}")

    # Botón de Cerrar Sesión en la barra lateral
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
    cursor.execute("SELECT email FROM usuarios WHERE role = 'admin'")
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

    # Enviar la notificación por correo a cada administrador si existen emails
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
    st.title("✔️ Viabilidades")
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
    # Se asume que `obtener_viabilidades()` retorna registros con la siguiente estructura:
    # (latitud, longitud, ticket, serviciable, apartment_id)
    viabilidades = obtener_viabilidades()
    for v in viabilidades:
        # Desempaquetamos cada registro
        lat, lon, ticket, serviciable, apartment_id = v

        # Determinar color según la respuesta al comercial y estado:
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

    # Si hay un marcador nuevo (seleccionado mediante clic en el mapa), agregarlo en azul
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
    #Geocoder().add_to(m)

    # Detectar el clic para agregar el marcador
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

    # Mostrar el formulario si hay un marcador
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
    """Obtiene la ubicación del usuario a través de un componente de geolocalización."""
    st.info(
        "ℹ️ Pulsa el botón de ubicación para centrar el mapa en el lugar en el que te encuentras actualmente.")

    # Usar el componente de geolocalización
    location = streamlit_geolocation()

    # Verificar si se ha obtenido la ubicación
    if location is None:
        st.warning("❌ No se pudo obtener la ubicación. Cargando el mapa en la ubicación predeterminada.")
        lat, lon = 43.463444, -3.790476  # Ubicación predeterminada si no se obtiene la geolocalización
    else:
        # Extraer latitud y longitud del diccionario
        lat = location.get('latitude')
        lon = location.get('longitude')

        # Si por alguna razón no se obtuvieron las coordenadas, usar las predeterminadas
        if lat is None or lon is None:
            st.warning("❌ No se pudo obtener la ubicación precisa. Cargando el mapa en la ubicación predeterminada.")
            lat, lon = 43.463444, -3.790476

    return lat, lon


# Obtener la ubicación
lat, lon = get_user_location()

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

    # Si no se encontraron registros, el formulario se mostrará vacío.
    if df.empty:
        st.warning("⚠️ No se encontraron datos para estas coordenadas.")
        form_data = {}    # Formulario vacío
        es_serviciable_default = "Sí"  # Por defecto, para nuevos puntos, se marca como "Sí"
    else:
        # Si hay más de un registro, pedir al usuario que seleccione uno
        if len(df) > 1:
            # Generamos una lista de opciones con más info
            opciones = [
                f"{row['apartment_id']}  –  Vial: {row['vial']}  –  Nº: {row['numero']}  –  Letra: {row['letra']}"
                for _, row in df.iterrows()
            ]
            st.warning("⚠️ Hay varias ofertas en estas coordenadas. Elige un Apartment ID de la lista del deplegable, en este caso, no es necesario que vayas eligiendo cada punto,"
                       "puedes elegir siempre el mismo e ir cambiando de Apartment ID en el listado que aparece a continuación, los colores se irán actualizando solos. ¡NO TE OLVIDES DE GUARDAR"
                       "CADA OFERTA POR SEPARADO!")
            seleccion = st.selectbox(
                "Elige un Apartment ID:",
                options=opciones,
                key=f"select_apartment_{form_key}"
            )
            # Extraemos el apartment_id (es la parte antes del primer espacio)
            apartment_id = seleccion.split()[0]
            # Filtramos el DataFrame por ese apartment_id
            df = df[df["apartment_id"] == apartment_id]

        # Tomamos los datos de la (o la única) fila
        apartment_id = df.iloc[0]["apartment_id"]
        provincia = df.iloc[0]["provincia"]
        municipio = df.iloc[0]["municipio"]
        poblacion = df.iloc[0]["poblacion"]
        vial = df.iloc[0]["vial"]
        numero = df.iloc[0]["numero"]
        letra = df.iloc[0]["letra"]
        cp = df.iloc[0]["cp"]
        # Suponemos que en la base se guardó el estado "serviciable" en una columna, de lo contrario lo dejamos en "Sí"
        es_serviciable_default = df.iloc[0].get("serviciable", "Sí")
        form_data = {
            "apartment_id": apartment_id,
            "provincia": provincia,
            "municipio": municipio,
            "poblacion": poblacion,
            "vial": vial,
            "numero": numero,
            "letra": letra,
            "cp": cp
        }

    # Rellenar campos con datos existentes o dejar en blanco si es nuevo
    apartment_id = form_data.get("apartment_id", "N/D")
    provincia = form_data.get("provincia", "")
    municipio = form_data.get("municipio", "")
    poblacion = form_data.get("poblacion", "")
    vial = form_data.get("vial", "")
    numero = form_data.get("numero", "")
    letra = form_data.get("letra", "")
    cp = form_data.get("cp", "")

    # Mostrar campos bloqueados (datos no editables) con la información del punto
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

    # Selector reactivo para "¿Es serviciable?"
    # Si es un punto nuevo (no hay datos) usamos "Sí" por defecto, de lo contrario usamos lo guardado
    es_serviciable = st.radio("🛠️ ¿Es serviciable?",
                              ["Sí", "No"],
                              index=0 if es_serviciable_default == "Sí" else 1,
                              horizontal=True)

    # Aquí se construye el resto del formulario, dentro de un contenedor
    with st.container():
        if es_serviciable == "Sí":
            col1, col2 = st.columns(2)
            with col1:
                tipo_vivienda = st.selectbox("🏠 Tipo de Ui",
                                             ["Piso", "Casa", "Dúplex", "Negocio", "Ático", "Otro"],
                                             index=0)
                contrato = st.radio("📑 Tipo de Contrato",
                                    ["Sí", "No Interesado"],
                                    index=0,
                                    horizontal=True)
                client_name = st.text_input("👤 Nombre del Cliente", max_chars=100)
                phone = st.text_input("📞 Teléfono", max_chars=15)
            with col2:
                tipo_vivienda_otro = st.text_input("📝 Especificar Tipo de Ui") if tipo_vivienda == "Otro" else ""
                alt_address = st.text_input("📌 Dirección Alternativa (Rellenar si difiere de la original)")
                observations = st.text_area("📝 Observaciones")
            contiene_incidencias = st.radio("⚠️ ¿Contiene incidencias?",
                                            ["Sí", "No"],
                                            index=1,
                                            horizontal=True)
            if contiene_incidencias == "Sí":
                motivo_incidencia = st.text_area("📄 Motivo de la Incidencia")
                imagen_incidencia = st.file_uploader("📷 Adjuntar Imagen (PNG, JPG, JPEG)",
                                                     type=["png", "jpg", "jpeg"])
            else:
                motivo_incidencia = ""
                imagen_incidencia = None
            motivo_serviciable = ""
        else:
            motivo_serviciable = st.text_area("❌ Motivo de No Servicio")
            # Estos campos estarán vacíos si se marca "No"
            tipo_vivienda = tipo_vivienda_otro = contrato = client_name = phone = alt_address = observations = contiene_incidencias = motivo_incidencia = ""
            imagen_incidencia = None

    # Botón de envío
    enviar = st.button("🚀 Enviar Oferta")

    if enviar:
        if es_serviciable == "Sí" and phone and not phone.isdigit():
            st.error("❌ El teléfono debe contener solo números.")
        else:
            oferta_data = {
                "Apartment ID": apartment_id,
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
                guardar_en_base_de_datos(oferta_data, imagen_incidencia)

                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT email FROM usuarios WHERE role = 'admin'")
                emails_admin = [fila[0] for fila in cursor.fetchall()]
                conn.close()

                nombre_comercial = st.session_state.get("username", "N/D")

                if emails_admin:
                    descripcion_oferta = (
                        f"📢 Se ha añadido una nueva oferta para el apartamento con ID {apartment_id}.<br><br>"
                        f"📝 Detalles de la oferta realizada por el comercial {nombre_comercial}:<br>"
                        f"🌍 <strong>Provincia:</strong> {provincia}<br>"
                        f"📍 <strong>Municipio:</strong> {municipio}<br>"
                        f"🏘️ <strong>Población:</strong> {poblacion}<br>"
                        f"🛣️ <strong>Vial:</strong> {vial}<br>"
                        f"🏠 <strong>Número:</strong> {numero}<br>"
                        f"📮 <strong>Código Postal:</strong> {cp}<br>"
                        f"📅 <strong>Fecha:</strong> {oferta_data['fecha']}<br>"
                        f"📱 <strong>Teléfono:</strong> {phone}<br>"
                        f"🏡 <strong>Tipo Vivienda:</strong> {oferta_data['Tipo_Vivienda']}<br>"
                        f"✅ <strong>Contratado:</strong> {contrato}<br>"
                        f"🔧 <strong>Servicio:</strong> {es_serviciable}<br>"
                        f"⚠️ <strong>Incidencia:</strong> {contiene_incidencias}<br>"
                        f"💬 <strong>Observaciones:</strong> {observations}<br><br>"
                        f"ℹ️ Por favor, revise los detalles de la oferta y asegúrese de que toda la información sea correcta."
                    )
                    for email in emails_admin:
                        correo_oferta_comercial(email, apartment_id, descripcion_oferta)

                    st.success("✅ Oferta enviada con éxito")
                    st.info(f"📧 Se ha enviado una notificación a los administradores: {', '.join(emails_admin)}")
                else:
                    st.warning("⚠️ No se encontró ningún email de administrador, no se pudo enviar la notificación.")

if __name__ == "__main__":
    comercial_dashboard()