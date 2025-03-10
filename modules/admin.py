import zipfile
import folium
import io  # Necesario para trabajar con flujos de bytes
import sqlite3
import datetime
import bcrypt
import pandas as pd
import plotly.express as px
from folium.plugins import MarkerCluster
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import os  # Para trabajar con archivos en el sistema
import base64  # Para codificar la imagen en base64
import streamlit as st
from modules.notificaciones import correo_viabilidad_administracion, correo_usuario
from datetime import datetime as dt  # Para evitar conflicto con datetime
from streamlit_folium import st_folium
from streamlit_option_menu import option_menu

from modules.cookie_instance import controller  # <-- Importa la instancia central

cookie_name = "my_app"

def log_trazabilidad(usuario, accion, detalles):
    """Inserta un registro en la tabla de trazabilidad."""
    try:
        conn = sqlite3.connect("data/usuarios.db")
        cursor = conn.cursor()
        fecha = dt.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT INTO trazabilidad (usuario_id, accion, detalles, fecha)
            VALUES (?, ?, ?, ?)
        """, (usuario, accion, detalles, fecha))
        conn.commit()
        conn.close()
    except Exception as e:
        # En caso de error en la trazabilidad, se imprime en consola (no se interrumpe la app)
        print(f"Error registrando trazabilidad: {e}")


# Función para obtener conexión a la base de datos
def obtener_conexion():
    """Retorna una nueva conexión a la base de datos."""
    try:
        conn = sqlite3.connect("data/usuarios.db")
        return conn
    except sqlite3.Error as e:
        print(f"Error al conectar con la base de datos: {e}")
        return None


# Función para convertir a numérico y manejar excepciones
def safe_convert_to_numeric(col):
    try:
        return pd.to_numeric(col)
    except ValueError:
        return col  # Si ocurre un error, regresamos la columna original sin cambios


def cargar_usuarios():
    """Carga los usuarios desde la base de datos."""
    conn = obtener_conexion()  # Abre la conexión
    if conn:
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT id, username, role, email FROM usuarios")
            usuarios = cursor.fetchall()
            return usuarios
        except sqlite3.Error as e:
            print(f"Error al cargar los usuarios: {e}")
            return []
        finally:
            conn.close()  # Cierra la conexión
    else:
        return []  # Retorna una lista vacía si no pudo conectarse


# Función para agregar un nuevo usuario
def agregar_usuario(username, rol, password, email):
    conn = obtener_conexion()
    cursor = conn.cursor()
    hashed_pw = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    try:
        cursor.execute("INSERT INTO usuarios (username, password, role, email) VALUES (?, ?, ?, ?)", (username, hashed_pw, rol, email))
        conn.commit()
        st.success(f"Usuario '{username}' creado con éxito.")
        log_trazabilidad(st.session_state["username"], "Agregar Usuario",
                         f"El admin agregó al usuario '{username}' con rol '{rol}'.")

        # Enviar correo al usuario
        asunto = "🆕 ¡Nuevo Usuario Creado!"
        mensaje = (
            f"Estimado {username},<br><br>"
            f"Se ha creado una cuenta para ti en nuestro sistema con los siguientes detalles:<br><br>"
            f"📋 <strong>Nombre:</strong> {username}<br>"
            f"🛠 <strong>Rol:</strong> {rol}<br>"
            f"📧 <strong>Email:</strong> {email}<br><br>"
            f"🔑 <strong>Tu contraseña es:</strong> {password}<br><br>"
            f"Por favor, ingresa al sistema y comprueba que todo es correcto.<br><br>"
            f"⚠️ <strong>Por seguridad:</strong> No compartas esta información con nadie. "
            f"Si no has realizado esta solicitud o tienes alguna duda sobre la creación de tu cuenta, por favor contacta con nuestro equipo de soporte de inmediato.<br><br>"
            f"Si has recibido este correo por error, te recomendamos solicitar el cambio de tu contraseña tan pronto como puedas para garantizar la seguridad de tu cuenta.<br><br>"
            f"Gracias por ser parte de nuestro sistema.<br><br>"
        )

        correo_usuario(email, asunto, mensaje)  # Llamada a la función de correo

    except sqlite3.IntegrityError:
        st.error(f"El usuario '{username}' ya existe.")
    finally:
        conn.close()


def editar_usuario(id, username, rol, password, email):
    conn = obtener_conexion()
    cursor = conn.cursor()

    # Obtenemos los datos actuales del usuario
    cursor.execute("SELECT username, role, email, password FROM usuarios WHERE id = ?", (id,))
    usuario_actual = cursor.fetchone()

    if usuario_actual:
        # Guardamos los valores actuales
        username_anterior, rol_anterior, email_anterior, password_anterior = usuario_actual

        # Realizamos las actualizaciones solo si hay cambios
        hashed_pw = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode() if password else None

        # Si la contraseña fue cambiada, realizamos la actualización correspondiente
        if password:
            cursor.execute("UPDATE usuarios SET username = ?, role = ?, password = ?, email = ? WHERE id = ?",
                           (username, rol, hashed_pw, email, id))
        else:
            cursor.execute("UPDATE usuarios SET username = ?, role = ?, email = ? WHERE id = ?",
                           (username, rol, email, id))

        conn.commit()
        conn.close()

        st.success(f"Usuario con ID {id} actualizado correctamente.")
        log_trazabilidad(st.session_state["username"], "Editar Usuario", f"El admin editó al usuario con ID {id}.")

        # Ahora creamos el mensaje del correo, especificando qué ha cambiado
        cambios = []

        if username != username_anterior:
            cambios.append(f"📋 Nombre cambiado de <strong>{username_anterior}</strong> a <strong>{username}</strong>.")
        if rol != rol_anterior:
            cambios.append(f"🛠 Rol cambiado de <strong>{rol_anterior}</strong> a <strong>{rol}</strong>.")
        if email != email_anterior:
            cambios.append(f"📧 Email cambiado de <strong>{email_anterior}</strong> a <strong>{email}</strong>.")
        if password:  # Si la contraseña fue modificada
            cambios.append(f"🔑 Tu contraseña ha sido cambiada. Asegúrate de usar una nueva contraseña segura.")

        # Si no hay cambios, se indica en el correo
        if not cambios:
            cambios.append("❗ No se realizaron cambios en tu cuenta.")

        # Asunto y cuerpo del correo
        asunto = "🔄 ¡Detalles de tu cuenta actualizados!"
        mensaje = (
            f"📢 Se han realizado cambios en tu cuenta con los siguientes detalles:<br><br>"
            f"{''.join([f'🔄 <strong>{cambio}</strong><br>' for cambio in cambios])}"  # Unimos los cambios en un formato adecuado
            f"<br>ℹ️ Si no realizaste estos cambios o tienes alguna duda, por favor contacta con el equipo de administración.<br><br>"
            f"⚠️ <strong>Por seguridad, te recordamos no compartir este correo con nadie. Si no reconoces los cambios, por favor contacta con el equipo de administración de inmediato.</strong><br><br>"
        )

        # Enviamos el correo
        correo_usuario(email, asunto, mensaje)  # Llamada a la función de correo
    else:
        conn.close()
        st.error(f"Usuario con ID {id} no encontrado.")

# Función para eliminar un usuario
def eliminar_usuario(id):
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("SELECT username, email FROM usuarios WHERE id = ?", (id,))
    usuario = cursor.fetchone()

    if usuario:
        nombre_usuario = usuario[0]
        email_usuario = usuario[1]

        cursor.execute("DELETE FROM usuarios WHERE id = ?", (id,))
        conn.commit()
        conn.close()

        st.success(f"Usuario con ID {id} eliminado correctamente.")
        log_trazabilidad(st.session_state["username"], "Eliminar Usuario", f"El admin eliminó al usuario con ID {id}.")

        # Enviar correo de baja al usuario
        asunto = "❌ Tu cuenta ha sido desactivada"
        mensaje = (
            f"📢 Tu cuenta ha sido desactivada y eliminada de nuestro sistema. <br><br>"
            f"ℹ️ Si consideras que esto ha sido un error o necesitas más detalles, por favor, contacta con el equipo de administración.<br><br>"
            f"🔒 <strong>Por seguridad, no compartas este correo con nadie. Si no reconoces esta acción, contacta con el equipo de administración de inmediato.</strong><br><br>"
        )

        correo_usuario(email_usuario, asunto, mensaje)  # Llamada a la función de correo
    else:
        st.error("Usuario no encontrado.")

# Función para generar PDF con los datos del informe
def generar_pdf(df, encabezado_titulo, mensaje_intro, fecha_generacion, pie_de_pagina):
    # Crear un archivo PDF en memoria
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)

    # Título del informe
    c.setFont("Helvetica-Bold", 16)
    c.drawString(30, 750, encabezado_titulo)

    # Mensaje introductorio
    c.setFont("Helvetica", 12)
    c.drawString(30, 730, mensaje_intro)

    # Fecha de generación
    c.setFont("Helvetica", 10)
    c.drawString(30, 710, f"Fecha de generación: {fecha_generacion}")

    # Añadir datos del informe (limitado a la primera página)
    y_position = 690
    c.setFont("Helvetica", 8)
    for index, row in df.iterrows():
        y_position -= 10
        if y_position < 40:
            c.showPage()  # Crear nueva página si es necesario
            c.setFont("Helvetica", 8)
            y_position = 750

        c.drawString(30, y_position, str(row.tolist()))

    # Pie de página
    c.setFont("Helvetica", 10)
    c.drawString(30, 30, pie_de_pagina)

    c.save()
    buffer.seek(0)
    return buffer

# Función que genera un enlace de descarga en HTML (no se integra en la tabla)
def get_download_link_icon(img_path):
    # Determinar el MIME type según la extensión
    mime = "image/jpeg"
    if img_path.lower().endswith(".png"):
        mime = "image/png"
    elif img_path.lower().endswith((".jpg", ".jpeg")):
        mime = "image/jpeg"
    with open(img_path, "rb") as f:
        data = f.read()
    b64 = base64.b64encode(data).decode()
    file_name = os.path.basename(img_path)
    # Usamos un emoji de flecha abajo (⬇️) como icono
    html = f'<a href="data:{mime};base64,{b64}" download="{file_name}" style="text-decoration: none; font-size:20px;">⬇️</a>'
    return html

def viabilidades_seccion():
    log_trazabilidad("Administrador", "Visualización de Viabilidades",
                     "El administrador visualizó la sección de viabilidades.")

    # Cargar los datos de la base de datos
    with st.spinner("⏳ Cargando los datos de viabilidades..."):
        try:
            conn = sqlite3.connect("data/usuarios.db")
            query_tables = "SELECT name FROM sqlite_master WHERE type='table';"
            tables = pd.read_sql(query_tables, conn)

            if 'viabilidades' not in tables['name'].values:
                st.error("❌ La tabla 'viabilidades' no se encuentra en la base de datos.")
                conn.close()
                return

            query = "SELECT * FROM viabilidades"
            viabilidades_df = pd.read_sql(query, conn)
            conn.close()

            if viabilidades_df.empty:
                st.warning("⚠️ No hay viabilidades disponibles.")
                return

        except Exception as e:
            st.error(f"❌ Error al cargar los datos de la base de datos: {e}")
            return

    # Verificar que existan las columnas necesarias
    required_columns = ['latitud', 'longitud', 'ticket']
    for col in required_columns:
        if col not in viabilidades_df.columns:
            st.error(f"❌ No se encuentra la columna '{col}'.")
            return

    # Organizar la disposición de la interfaz con columnas
    col1, col2 = st.columns([3, 3])  # Hacemos la columna 1 más ancha para el mapa

    with col1:
        # Crear y mostrar el mapa con Folium
        with st.spinner("⏳ Cargando mapa..."):
            m = folium.Map(location=[43.463444, -3.790476], zoom_start=12,
                           tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
                           attr="Google")
            marker_cluster = MarkerCluster().add_to(m)

            # Iterar sobre los datos de las viabilidades para agregar marcadores
            for _, row in viabilidades_df.iterrows():
                popup_text = f"🏠 {row['ticket']} - 📍 {row['latitud']}, {row['longitud']}"
                folium.Marker(
                    location=[row['latitud'], row['longitud']],
                    popup=popup_text,  # Aquí se está pasando el popup
                    icon=folium.Icon(color='blue', icon='info-sign')
                ).add_to(marker_cluster)

            # Mostrar el mapa
            map_data = st_folium(m, height=500, width=700)

    with col2:
        # Mostrar la tabla de viabilidades
        st.subheader("Tabla de Viabilidades")
        # Identificar los apartment_id repetidos
        viabilidades_df['is_duplicate'] = viabilidades_df['apartment_id'].duplicated(keep=False)

        # Función para resaltar las celdas con apartment_id duplicados
        def highlight_duplicates(val):
            if isinstance(val, str) and val in viabilidades_df[viabilidades_df['is_duplicate']]['apartment_id'].values:
                return 'background-color: yellow'  # Cambia el color que desees
            return ''

        # Aplicar el estilo a la columna apartment_id
        styled_df = viabilidades_df.style.applymap(highlight_duplicates, subset=['apartment_id'])

        # Mostrar la tabla con el estilo aplicado
        st.dataframe(styled_df, use_container_width=True)

        # Añadir un botón de refresco para actualizar la tabla
        if st.button("🔄 Refrescar Tabla"):
            st.rerun()

    # Verificación del objeto del clic
    if map_data and "last_object_clicked" in map_data and map_data["last_object_clicked"]:
        clicked_object = map_data["last_object_clicked"]

        # Extraer latitud y longitud del objeto clicado
        lat_click = clicked_object.get("lat", "")
        lon_click = clicked_object.get("lng", "")

        if lat_click and lon_click:
            # Consultar en la base de datos para encontrar el ticket correspondiente a las coordenadas
            viabilidad_data = viabilidades_df[
                (viabilidades_df['latitud'] == lat_click) & (viabilidades_df['longitud'] == lon_click)
            ]

            if viabilidad_data.empty:
                st.error(f"❌ No se encontró viabilidad para las coordenadas: Lat: {lat_click}, Lon: {lon_click}")
                st.write(f"🚨 Viabilidades disponibles en la base de datos:")
                st.write(viabilidades_df[['ticket', 'latitud', 'longitud']])
            else:
                # Aquí se encontró una viabilidad para esas coordenadas
                ticket = viabilidad_data['ticket'].iloc[0]
                st.write(f"✔️ Viabilidad encontrada para el Ticket: {ticket}")

                # Llamar a la función para mostrar el formulario con los datos de la viabilidad
                mostrar_formulario(viabilidad_data.iloc[0])
        else:
            st.error("❌ No se encontraron coordenadas en el clic.")


def mostrar_formulario(click_data):
    """Muestra el formulario para editar los datos de la viabilidad y guarda los cambios en la base de datos."""

    # Extraer los datos
    ticket = click_data["ticket"]
    latitud = click_data["latitud"]
    longitud = click_data["longitud"]
    provincia = click_data.get("provincia", "N/D")
    municipio = click_data.get("municipio", "N/D")
    poblacion = click_data.get("poblacion", "N/D")
    vial = click_data.get("vial", "N/D")
    numero = click_data.get("numero", "N/D")
    letra = click_data.get("letra", "N/D")
    cp = click_data.get("cp", "N/D")
    comentario = click_data.get("comentario", "N/D")
    fecha_viabilidad = click_data.get("fecha_viabilidad", "N/D")
    cto_cercana = click_data.get("cto_cercana", "N/D")
    comentarios_comercial = click_data.get("comentarios_comercial", "N/D")

    # Crear un diseño en columnas
    col1, col2, col3 = st.columns([1, 1, 1])  # Aseguramos que las columnas tengan un tamaño similar
    with col1:
        # Ticket y Latitud/Longitud
        st.text_input("🎟️ Ticket", value=ticket, disabled=True, key="ticket_input")
    with col2:
        st.text_input("📍 Latitud", value=latitud, disabled=True, key="latitud_input")
    with col3:
        st.text_input("📍 Longitud", value=longitud, disabled=True, key="longitud_input")

    # Segunda fila con Provincia, Municipio y Población
    col4, col5, col6 = st.columns([1, 1, 1])
    with col4:
        st.text_input("📍 Provincia", value=provincia, disabled=True, key="provincia_input")
    with col5:
        st.text_input("🏙️ Municipio", value=municipio, disabled=True, key="municipio_input")
    with col6:
        st.text_input("👥 Población", value=poblacion, disabled=True, key="poblacion_input")

    # Tercera fila con Vial, Número, Letra y CP
    col7, col8, col9, col10 = st.columns([2, 1, 1, 1])
    with col7:
        st.text_input("🚦 Vial", value=vial, disabled=True, key="vial_input")
    with col8:
        st.text_input("🔢 Número", value=numero, disabled=True, key="numero_input")
    with col9:
        st.text_input("🔠 Letra", value=letra, disabled=True, key="letra_input")
    with col10:
        st.text_input("📮 Código Postal", value=cp, disabled=True, key="cp_input")

    # Cuarta fila con Comentarios
    col11 = st.columns(1)[0]  # Columna única para comentarios
    with col11:
        st.text_area("💬 Comentarios", value=comentario, disabled=True, key="comentario_input")

    # Quinta fila con Fecha y Cto Cercana
    col12, col13 = st.columns([1, 1])
    with col12:
        st.text_input("📅 Fecha Viabilidad", value=fecha_viabilidad, disabled=True, key="fecha_viabilidad_input")
    with col13:
        st.text_input("🔌 Cto Cercana", value=cto_cercana, disabled=True, key="cto_cercana_input")

    # Sexta fila con Comentarios Comerciales
    col14 = st.columns(1)[0]  # Columna única para comentarios
    with col14:
        st.text_area("📝 Comentarios Comerciales", value=comentarios_comercial, disabled=True, key="comentarios_comercial_input")

    # Campos para completar
    col15, col16, col17 = st.columns([1, 1, 1])
    with col15:
        apartment_id = st.text_input("🏠 Apartment_id", value="", key="apartment_id_input")
        olt = st.text_input("⚡ OLT", value="", key="olt_input")
    with col16:
        cto_admin = st.text_input("⚙️ Cto Admin", value="", key="cto_admin_input")
    with col17:
        id_cto = st.text_input("🔧 ID Cto", value="", key="id_cto_input")

    # Nueva fila para Municipio Admin
    col18 = st.columns(1)[0]  # Columna única para el municipio admin
    with col18:
        municipio_admin = st.text_input("🌍 Municipio Admin", value="", key="municipio_admin_input")

    # Fila para "Es Serviciable?"
    col19, col20 = st.columns([1, 1])
    with col19:
        serviciable = st.selectbox("🔍 ¿Es Serviciable?", ["Sí", "No"], index=0, key="serviciable_input")
    with col20:
        coste = st.number_input("💰 Coste", value=0.0, step=0.01, key="coste_input")

    # Fila final para Comentarios Internos
    col21 = st.columns(1)[0]  # Columna única para comentarios internos
    with col21:
        comentarios_internos = st.text_area("📄 Comentarios Internos", value="", key="comentarios_internos_input")

    # Si el administrador guarda los cambios
    if st.button(f"💾 Guardar cambios para el Ticket {ticket}"):
        try:
            # Conectar a la base de datos (usuarios.db)
            conn = sqlite3.connect("data/usuarios.db")
            cursor = conn.cursor()

            # Sentencia UPDATE para guardar los cambios basados en el ticket
            query = """
                UPDATE viabilidades
                SET apartment_id = ?, olt = ?, cto_admin = ?, id_cto = ?, municipio_admin = ?, serviciable = ?, 
                    coste = ?, comentarios_internos = ?
                WHERE ticket = ?
            """
            # Ejecutar la sentencia con los valores proporcionados en el formulario
            cursor.execute(query, (
                apartment_id, olt, cto_admin, id_cto, municipio_admin, serviciable,
                coste, comentarios_internos, ticket
            ))

            # 📢 Consultar el correo del comercial asociado al ticket:
            cursor.execute("""
                SELECT email 
                FROM usuarios
                WHERE username = (SELECT usuario FROM viabilidades WHERE ticket = ?)
            """, (ticket,))
            email_comercial = cursor.fetchone()

            # Verificar si se encontró el correo
            if email_comercial:
                destinatario_comercial = email_comercial[0]
            else:
                st.error("❌ No se encontró el correo del comercial correspondiente.")
                destinatario_comercial = "psvpasuva@gmail.com"  # Correo predeterminado

            # Preparar el contenido del correo
            descripcion_viabilidad = (
                f"📢 La viabilidad del ticket {ticket} ha sido completada.<br><br>"
                f"📌 **Comentarios Internos**: {comentarios_comercial}<br>"
                f"📍 **Municipio**: {municipio_admin}<br>"
                f"💰 **Coste**: {coste}€<br>"
                f"🔍 **Es Serviciable**: {serviciable}<br>"
                f"⚙️ **CTO Admin**: {cto_admin}<br>"
                f"🏠 **Apartment ID**: {apartment_id}<br><br>"
                f"ℹ️ Por favor, revise los detalles de la viabilidad y asegúrese de que toda la información sea correcta. "
                f"Si tiene alguna pregunta o necesita realizar alguna modificación, no dude en ponerse en contacto con el equipo de administración."
            )

            # Enviar el correo al comercial
            correo_viabilidad_administracion(destinatario_comercial, ticket, descripcion_viabilidad)

            # Confirmar los cambios en la base de datos
            conn.commit()
            conn.close()

            # Mostrar mensaje de éxito
            st.success(f"✅ Los cambios para el Ticket {ticket} han sido guardados correctamente.")
            st.info(f"📧 Se ha enviado una notificación al comercial sobre la viabilidad completada.")

        except Exception as e:
            st.error(f"❌ Hubo un error al guardar los cambios: {e}")

def obtener_apartment_ids_existentes(cursor):
    cursor.execute("SELECT apartment_id FROM datos_uis")
    return {row[0] for row in cursor.fetchall()}

# Función principal de la app (Dashboard de administración)
def admin_dashboard():
    """Panel del administrador."""

    # Personalizar la barra lateral
    st.sidebar.title("📊 Panel de Administración")


    # Sidebar con opción de menú más moderno
    with st.sidebar:
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
                    <div>Rol: Administrador</div>
                    """, unsafe_allow_html=True)
        st.sidebar.markdown(f"¡Bienvenido, **{st.session_state['username']}**!")
        st.sidebar.markdown("---")

        opcion = option_menu(
            menu_title=None,  # Título del menú oculto
            options=["Home", "Ver Datos", "Ofertas Comerciales", "Viabilidades", "Cargar Nuevos Datos",
                     "Generador de informes", "Trazabilidad y logs", "Gestionar Usuarios",
                     "Control de versiones"],
            icons=["house", "graph-up", "bar-chart", "check-circle", "upload",
                   "file-earmark-text", "journal-text", "people", "arrow-clockwise"],  # Íconos de Bootstrap
            menu_icon="list",
            default_index=0,
            styles={
                "container": {"padding": "0px","background-color":"#262730"},  # Sin fondo ni márgenes
                "icon": {"color": "#ffffff", "font-size": "18px"},  # Íconos oscuros
                "nav-link": {
                    "color": "#ffffff", "font-size": "16px", "text-align": "left", "margin": "0px"
                },  # Texto en negro sin margen extra
                "nav-link-selected": {
                    "background-color": "#0073e6", "color": "white"
                },  # Opción seleccionada resaltada en azul
            }
        )

        # Registrar la selección de la opción en trazabilidad
        log_trazabilidad(st.session_state["username"], "Selección de opción", f"El admin seleccionó la opción '{opcion}'.")

        # Botón de Cerrar sesión en la barra lateral
        with st.sidebar:
            if st.button("Cerrar sesión"):
                detalles = f"El administrador {st.session_state.get('username', 'N/A')} cerró sesión."
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

    # Opción: Visualizar datos de la tabla datos_uis
    if opcion == "Home":
        home_page()
    elif opcion == "Ver Datos":
        st.header("📊 Visualizar y gestionar datos (Datos UIS)")
        st.info("ℹ️ En esta sección puedes visualizar los datos en bruto de AMS, filtrar los datos por etiquetas, columnas, buscar (lupa de la tabla)"
                "elementos concretos de la tabla y descargar los datos filtrados en formato excel o csv. Organiza y elige las etiquetas rojas en función de "
                "como prefieras visualizar el contenido de la tabla.")

        if "df" in st.session_state:
            del st.session_state["df"]

        with st.spinner("Cargando datos..."):
            try:
                conn = sqlite3.connect("data/usuarios.db")
                query_tables = "SELECT name FROM sqlite_master WHERE type='table';"
                tables = pd.read_sql(query_tables, conn)
                if 'datos_uis' not in tables['name'].values:
                    st.error("❌ La tabla 'datos_uis' no se encuentra en la base de datos.")
                    conn.close()
                    return
                query = "SELECT * FROM datos_uis"
                data = pd.read_sql(query, conn)
                conn.close()
                if data.empty:
                    st.error("❌ No se encontraron datos en la base de datos.")
                    return
            except Exception as e:
                st.error(f"❌ Error al cargar datos de la base de datos: {e}")
                return

        for col in data.select_dtypes(include=["object"]).columns:
            data[col] = data[col].replace({'true': True, 'false': False})
            data[col] = safe_convert_to_numeric(data[col])

        if data.columns.duplicated().any():
            st.warning("¡Se encontraron columnas duplicadas! Se eliminarán las duplicadas.")
            data = data.loc[:, ~data.columns.duplicated()]

        st.session_state["df"] = data
        columnas = st.multiselect("Filtra las columnas a mostrar", data.columns.tolist(),
                                  default=data.columns.tolist())
        st.dataframe(data[columnas], use_container_width=True)

        download_format = st.radio("Selecciona el formato de descarga:", ["Excel", "CSV"])
        if download_format == "Excel":
            towrite = io.BytesIO()
            with pd.ExcelWriter(towrite, engine='xlsxwriter') as writer:
                data[columnas].to_excel(writer, index=False, sheet_name='Datos')
            towrite.seek(0)
            with st.spinner("Preparando archivo Excel..."):
                st.download_button(
                    label="📥 Descargar Excel",
                    data=towrite,
                    file_name="datos.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        elif download_format == "CSV":
            csv = data[columnas].to_csv(index=False).encode()
            with st.spinner("Preparando archivo CSV..."):
                st.download_button(
                    label="📥 Descargar CSV",
                    data=csv,
                    file_name="datos.csv",
                    mime="text/csv"
                )

    # Opción: Visualizar datos de la tabla ofertas_comercial y comercial_rafa
    elif opcion == "Ofertas Comerciales":
        st.header("📊 Visualizar Ofertas Comerciales")
        st.info(
            "ℹ️ En esta sección puedes visualizar las ofertas registradas por los comerciales, filtrar los datos por etiquetas, columnas, buscar (lupa de la tabla)"
            "elementos concretos de la tabla y descargar los datos filtrados en formato excel o csv. Organiza y elige las etiquetas rojas en función de "
            "como prefieras visualizar el contenido de la tabla.")

        if "df" in st.session_state:
            del st.session_state["df"]

        with st.spinner("⏳ Cargando ofertas comerciales..."):
            try:
                conn = sqlite3.connect("data/usuarios.db")  # Conexión a la base de datos correcta

                # Consultar ambas tablas
                query_ofertas_comercial = "SELECT * FROM ofertas_comercial"
                query_comercial_rafa = "SELECT * FROM comercial_rafa"  # Cambiar si tienes un nombre diferente en esta tabla

                # Cargar los datos de ambas tablas
                ofertas_comercial_data = pd.read_sql(query_ofertas_comercial, conn)
                comercial_rafa_data = pd.read_sql(query_comercial_rafa, conn)

                # Cerrar conexión
                conn.close()

                # Comprobar si ambas tablas contienen datos
                if ofertas_comercial_data.empty and comercial_rafa_data.empty:
                    st.error("❌ No se encontraron ofertas realizadas por los comerciales.")
                    return

                # Filtrar comercial_rafa para solo mostrar registros con datos en la columna 'serviciable'
                comercial_rafa_data_filtrada = comercial_rafa_data[comercial_rafa_data['serviciable'].notna()]

                # Unir ambos DataFrames si hay datos en la tabla 'comercial_rafa' filtrados
                if not comercial_rafa_data_filtrada.empty:
                    combined_data = pd.concat([ofertas_comercial_data, comercial_rafa_data_filtrada], ignore_index=True)
                else:
                    # Si no hay datos en la tabla 'comercial_rafa' para mostrar, solo usamos ofertas_comercial_data
                    combined_data = ofertas_comercial_data

            except Exception as e:
                st.error(f"❌ Error al cargar datos de la base de datos: {e}")
                return

        # Si la tabla combinada está vacía, mostrar un mensaje
        if combined_data.empty:
            st.warning(
                "⚠️ No se encontraron ofertas comerciales finalizadas.")
            return

        # Eliminar columnas duplicadas si las hay
        if combined_data.columns.duplicated().any():
            st.warning("¡Se encontraron columnas duplicadas! Se eliminarán las duplicadas.")
            combined_data = combined_data.loc[:, ~combined_data.columns.duplicated()]

        # Guardar en sesión de Streamlit para mostrar en la tabla
        st.session_state["df"] = combined_data

        columnas = st.multiselect("Filtra las columnas a mostrar", combined_data.columns.tolist(),
                                  default=combined_data.columns.tolist())
        st.dataframe(combined_data[columnas], use_container_width=True)

        download_format = st.radio("Selecciona el formato de descarga:", ["Excel", "CSV"], key="oferta_download")

        # Opción de descarga en Excel
        if download_format == "Excel":
            towrite = io.BytesIO()
            with pd.ExcelWriter(towrite, engine='xlsxwriter') as writer:
                combined_data[columnas].to_excel(writer, index=False, sheet_name='Ofertas')
            towrite.seek(0)
            with st.spinner("Preparando archivo Excel..."):
                st.download_button(
                    label="📥 Descargar Excel",
                    data=towrite,
                    file_name="ofertas_comerciales.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

        # Opción de descarga en CSV
        elif download_format == "CSV":
            csv = combined_data[columnas].to_csv(index=False).encode()
            with st.spinner("Preparando archivo CSV..."):
                st.download_button(
                    label="📥 Descargar CSV",
                    data=csv,
                    file_name="ofertas_comerciales.csv",
                    mime="text/csv"
                )

        # Desplegable para ofertas con imagen
        offers_with_image = []
        for idx, row in combined_data.iterrows():
            fichero_imagen = row.get("fichero_imagen", None)
            if fichero_imagen and isinstance(fichero_imagen, str) and os.path.exists(fichero_imagen):
                offers_with_image.append((row["apartment_id"], fichero_imagen))

        if offers_with_image:
            st.markdown("### Descarga de imágenes de ofertas")

            # Desplegable para seleccionar una oferta
            option = st.selectbox(
                "Selecciona el Apartment ID de la oferta para descargar su imagen:",
                ["-- Seleccione --"] + [offer[0] for offer in offers_with_image]
            )

            if option != "-- Seleccione --":
                # Buscar la oferta seleccionada
                selected_offer = next((offer for offer in offers_with_image if offer[0] == option), None)
                if selected_offer:
                    fichero_imagen = selected_offer[1]
                    st.image(fichero_imagen, width=200)

                    # Determinar el tipo de imagen
                    mime = "image/jpeg"
                    if fichero_imagen.lower().endswith(".png"):
                        mime = "image/png"
                    elif fichero_imagen.lower().endswith((".jpg", ".jpeg")):
                        mime = "image/jpeg"

                    # Enlace de descarga individual
                    with open(fichero_imagen, "rb") as file:
                        file_data = file.read()
                    st.download_button(
                        label="Descargar imagen",
                        data=file_data,
                        file_name=os.path.basename(fichero_imagen),
                        mime=mime
                    )

            # Botón para descargar todas las imágenes en un archivo ZIP
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w") as zip_file:
                for apt_id, img_path in offers_with_image:
                    zip_file.write(img_path, arcname=os.path.basename(img_path))
            zip_buffer.seek(0)

            st.download_button(
                label="Descargar todas las imágenes",
                data=zip_buffer,
                file_name="imagenes_ofertas.zip",
                mime="application/zip"
            )

    # Opción: Viabilidades (En construcción)
    elif opcion == "Viabilidades":
        st.header("✔️ Viabilidades")
        st.info(
            "ℹ️ En esta sección puedes consultar y completar los tickets de viabilidades según el comercial, filtrar los datos por etiquetas, columnas, buscar (lupa de la tabla)"
            "elementos concretos de la tabla y descargar los datos filtrados en formato excel o csv. Organiza y elige las etiquetas rojas en función de "
            "como prefieras visualizar el contenido de la tabla. Elige la viabilidad que quieras estudiar en el plano y completa los datos necesarios en el formulario"
            " que se despliega en la partes inferior. Una vez guardadas tus modificaciones, podrás refrescar la tabla de la derecha para que veas los nuevos datos.")
        viabilidades_seccion()

    # Opción: Generar Informes
    elif opcion == "Generador de informes":
        st.header("📑 Generador de Informes")
        st.info("🏗️ ZONA EN CONSTRUCCIÓN")
        st.info("ℹ️ Aquí puedes generar informes basados en los datos disponibles.")
        log_trazabilidad(st.session_state["username"], "Generar Informe", "El admin accedió al generador de informes.")

        # Selección de tipo de informe
        informe_tipo = st.selectbox("Selecciona el tipo de informe:",
                                    ["Informe de Datos UIS", "Informe de Ofertas Comerciales",
                                     "Informe de Viabilidades"])

        # Filtros comunes para todos los informes
        st.sidebar.subheader("Filtros de Información")

        df_filtrado = st.session_state.get("df", pd.DataFrame())
        columnas_disponibles = df_filtrado.columns.tolist() if not df_filtrado.empty else []

        filtro_columnas = st.multiselect("Selecciona las columnas para filtrar en Datos UIS:",
                                         columnas_disponibles) if columnas_disponibles else []

        # Informe de Datos UIS
        if informe_tipo == "Informe de Datos UIS":
            st.write("Generando informe para los datos UIS...")

            if "provincia" in df_filtrado.columns:
                provincias = st.selectbox("Selecciona la provincia:",
                                          ["Todas"] + df_filtrado.provincia.unique().tolist())
            if "fecha" in df_filtrado.columns:
                df_filtrado['fecha'] = pd.to_datetime(df_filtrado['fecha'], errors='coerce', format='%d.%m.%Y')
                fecha_inicio = st.date_input("Fecha de inicio:", pd.to_datetime("2022-01-01"))
                fecha_fin = st.date_input("Fecha de fin:", pd.to_datetime("2025-12-31"))
                fecha_inicio = pd.to_datetime(fecha_inicio)
                fecha_fin = pd.to_datetime(fecha_fin)
            if filtro_columnas:
                for columna in filtro_columnas:
                    valor_filtro = st.text_input(f"Filtra por {columna}:")
                    if valor_filtro:
                        df_filtrado = df_filtrado[
                            df_filtrado[columna].astype(str).str.contains(valor_filtro, case=False)]
            if "provincia" in df_filtrado.columns and provincias != "Todas":
                df_filtrado = df_filtrado[df_filtrado["provincia"] == provincias]
            if "fecha" in df_filtrado.columns:
                df_filtrado = df_filtrado[df_filtrado["fecha"].between(fecha_inicio, fecha_fin)]

        # Informe de Ofertas Comerciales
        elif informe_tipo == "Informe de Ofertas Comerciales":
            st.write("Generando informe para las ofertas comerciales...")
            ofertas_filtradas = st.session_state.get("df", pd.DataFrame())
            columnas_ofertas = ofertas_filtradas.columns.tolist() if not ofertas_filtradas.empty else []
            filtro_columnas_ofertas = st.multiselect("Selecciona las columnas para filtrar en Ofertas Comerciales:",
                                                     columnas_ofertas) if columnas_ofertas else []

            if "provincia" in ofertas_filtradas.columns:
                provincias_ofertas = st.selectbox("Selecciona la provincia para ofertas:",
                                                  ["Todas"] + ofertas_filtradas.provincia.unique().tolist())
            if "fecha" in ofertas_filtradas.columns:
                ofertas_filtradas['fecha'] = pd.to_datetime(ofertas_filtradas['fecha'], errors='coerce')
                fecha_inicio_oferta = st.date_input("Fecha de inicio para ofertas:", pd.to_datetime("2022-01-01"))
                fecha_fin_oferta = st.date_input("Fecha de fin para ofertas:", pd.to_datetime("2025-12-31"))
                fecha_inicio_oferta = pd.to_datetime(fecha_inicio_oferta)
                fecha_fin_oferta = pd.to_datetime(fecha_fin_oferta)
            if filtro_columnas_ofertas:
                for columna in filtro_columnas_ofertas:
                    valor_filtro_oferta = st.text_input(f"Filtra por {columna}:")
                    if valor_filtro_oferta:
                        ofertas_filtradas = ofertas_filtradas[
                            ofertas_filtradas[columna].astype(str).str.contains(valor_filtro_oferta, case=False)]
            if "provincia" in ofertas_filtradas.columns and provincias_ofertas != "Todas":
                ofertas_filtradas = ofertas_filtradas[ofertas_filtradas["provincia"] == provincias_ofertas]
            if "fecha" in ofertas_filtradas.columns:
                ofertas_filtradas = ofertas_filtradas[
                    ofertas_filtradas["fecha"].between(fecha_inicio_oferta, fecha_fin_oferta)]

        # Informe de Viabilidades
        elif informe_tipo == "Informe de Viabilidades":
            st.write("Generando informe para las viabilidades...")
            viabilidades_df = st.session_state.get("viabilidades_df", pd.DataFrame())
            columnas_viabilidades = viabilidades_df.columns.tolist() if not viabilidades_df.empty else []
            filtro_columnas_viabilidades = st.multiselect("Selecciona las columnas para filtrar en Viabilidades:",
                                                          columnas_viabilidades) if columnas_viabilidades else []

            if filtro_columnas_viabilidades:
                for columna in filtro_columnas_viabilidades:
                    valor_filtro_viabilidad = st.text_input(f"Filtra por {columna}:")
                    if valor_filtro_viabilidad:
                        viabilidades_df = viabilidades_df[
                            viabilidades_df[columna].astype(str).str.contains(valor_filtro_viabilidad, case=False)]

            # Filtro por fechas en viabilidades
            if "fecha_viabilidad" in viabilidades_df.columns:
                fecha_inicio_viabilidad = st.date_input("Fecha de inicio de viabilidad:", pd.to_datetime("2022-01-01"))
                fecha_fin_viabilidad = st.date_input("Fecha de fin de viabilidad:", pd.to_datetime("2025-12-31"))
                viabilidades_df['fecha_viabilidad'] = pd.to_datetime(viabilidades_df['fecha_viabilidad'],
                                                                     errors='coerce')
                viabilidades_df = viabilidades_df[
                    viabilidades_df['fecha_viabilidad'].between(fecha_inicio_viabilidad, fecha_fin_viabilidad)]

        # Personalización del Informe
        st.sidebar.subheader("Personalización del Informe")
        encabezado_titulo = st.sidebar.text_input("Título del Informe:", "Informe de Datos")
        mensaje_intro = st.sidebar.text_area("Mensaje Introductorio:",
                                             "Este informe contiene datos filtrados según tus criterios.")
        pie_de_pagina = st.sidebar.text_input("Pie de Página:", "Firma: Tu Empresa S.A.")
        fecha_generacion = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if st.button("Generar Informe", key="generar_informe"):
            if informe_tipo == "Informe de Datos UIS":
                if not df_filtrado.empty:
                    towrite = io.BytesIO()
                    with pd.ExcelWriter(towrite, engine='xlsxwriter') as writer:
                        df_filtrado.to_excel(writer, index=False, sheet_name='Informe Datos UIS')
                        worksheet = writer.sheets['Informe Datos UIS']
                        worksheet.write('A1', encabezado_titulo)
                        worksheet.write('A2', mensaje_intro)
                        worksheet.write('A3', f"Fecha de generación: {fecha_generacion}")
                        worksheet.write(len(df_filtrado) + 3, 0, pie_de_pagina)
                    towrite.seek(0)
                    st.download_button(
                        label="📥 Descargar Informe de Datos UIS en Excel",
                        data=towrite,
                        file_name="informe_datos_uis.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                    pdf_buffer = generar_pdf(df_filtrado, encabezado_titulo, mensaje_intro, fecha_generacion,
                                             pie_de_pagina)
                    st.download_button(
                        label="📥 Descargar Informe de Datos UIS en PDF",
                        data=pdf_buffer,
                        file_name="informe_datos_uis.pdf",
                        mime="application/pdf"
                    )
                    log_trazabilidad(st.session_state["username"], "Generar Informe",
                                     "El admin generó un informe de Datos UIS.")
                else:
                    st.error("❌ No se han encontrado datos que coincidan con los filtros para generar el informe.")
            elif informe_tipo == "Informe de Ofertas Comerciales":
                if not ofertas_filtradas.empty:
                    towrite = io.BytesIO()
                    with pd.ExcelWriter(towrite, engine='xlsxwriter') as writer:
                        ofertas_filtradas.to_excel(writer, index=False, sheet_name='Informe Ofertas Comerciales')
                        worksheet = writer.sheets['Informe Ofertas Comerciales']
                        worksheet.write('A1', encabezado_titulo)
                        worksheet.write('A2', mensaje_intro)
                        worksheet.write('A3', f"Fecha de generación: {fecha_generacion}")
                        worksheet.write(len(ofertas_filtradas) + 3, 0, pie_de_pagina)
                    towrite.seek(0)
                    st.download_button(
                        label="📥 Descargar Informe de Ofertas Comerciales en Excel",
                        data=towrite,
                        file_name="informe_ofertas_comerciales.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                    pdf_buffer = generar_pdf(ofertas_filtradas, encabezado_titulo, mensaje_intro, fecha_generacion,
                                             pie_de_pagina)
                    st.download_button(
                        label="📥 Descargar Informe de Ofertas Comerciales en PDF",
                        data=pdf_buffer,
                        file_name="informe_ofertas_comerciales.pdf",
                        mime="application/pdf"
                    )
                    log_trazabilidad(st.session_state["username"], "Generar Informe",
                                     "El admin generó un informe de Ofertas Comerciales.")
                else:
                    st.error(
                        "❌ No se han encontrado ofertas comerciales que coincidan con los filtros para generar el informe.")
            elif informe_tipo == "Informe de Viabilidades":
                if not viabilidades_df.empty:
                    towrite = io.BytesIO()
                    with pd.ExcelWriter(towrite, engine='xlsxwriter') as writer:
                        viabilidades_df.to_excel(writer, index=False, sheet_name='Informe Viabilidades')
                        worksheet = writer.sheets['Informe Viabilidades']
                        worksheet.write('A1', encabezado_titulo)
                        worksheet.write('A2', mensaje_intro)
                        worksheet.write('A3', f"Fecha de generación: {fecha_generacion}")
                        worksheet.write(len(viabilidades_df) + 3, 0, pie_de_pagina)
                    towrite.seek(0)
                    st.download_button(
                        label="📥 Descargar Informe de Viabilidades en Excel",
                        data=towrite,
                        file_name="informe_viabilidades.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                    pdf_buffer = generar_pdf(viabilidades_df, encabezado_titulo, mensaje_intro, fecha_generacion,
                                             pie_de_pagina)
                    st.download_button(
                        label="📥 Descargar Informe de Viabilidades en PDF",
                        data=pdf_buffer,
                        file_name="informe_viabilidades.pdf",
                        mime="application/pdf"
                    )
                    log_trazabilidad(st.session_state["username"], "Generar Informe",
                                     "El admin generó un informe de Viabilidades.")
                else:
                    st.error(
                        "❌ No se han encontrado viabilidades que coincidan con los filtros para generar el informe.")

    # Opción: Gestionar Usuarios
    elif opcion == "Gestionar Usuarios":
        st.header("👥 Gestionar Usuarios")
        st.info(
            "ℹ️ Aquí puedes gestionar los usuarios registrados. Crea, edita o elimina usuarios en función de tus necesidades. "
            "El usuario afectado recibirá una notificación por correo electrónico con la información asociada a la acción que realices.")

        log_trazabilidad(st.session_state["username"], "Gestionar Usuarios",
                         "El admin accedió a la sección de gestión de usuarios.")

        usuarios = cargar_usuarios()
        if usuarios:
            # Usamos una columna para la tabla
            col1, col2 = st.columns([2, 2])  # La columna izquierda será más grande

            with col1:
                st.subheader("Lista de Usuarios")
                df_usuarios = pd.DataFrame(usuarios, columns=["ID", "Nombre", "Rol", "Email"])
                st.dataframe(df_usuarios)

            with col2:
                # Columna derecha para el formulario de "Agregar Nuevo Usuario"
                st.subheader("Agregar Nuevo Usuario")
                nombre = st.text_input("Nombre del Usuario")
                rol = st.selectbox("Selecciona el Rol",
                                   ["admin", "supervisor", "comercial", "comercial_jefe", "comercial_rafa"])
                email = st.text_input("Email del Usuario")
                password = st.text_input("Contraseña", type="password")

                if st.button("Agregar Usuario"):
                    if nombre and password and email:
                        agregar_usuario(nombre, rol, password, email)
                    else:
                        st.error("Por favor, completa todos los campos.")

            # Formularios de "Editar Usuario" y "Eliminar Usuario" fuera de las columnas
            st.subheader("Editar Usuario")
            usuario_id = st.number_input("ID del Usuario a Editar", min_value=1, step=1)

            if usuario_id:
                conn = obtener_conexion()
                cursor = conn.cursor()
                cursor.execute("SELECT username, role, email FROM usuarios WHERE id = ?", (usuario_id,))
                usuario = cursor.fetchone()
                conn.close()

                if usuario:
                    nuevo_nombre = st.text_input("Nuevo Nombre", value=usuario[0])
                    nuevo_rol = st.selectbox("Nuevo Rol",
                                             ["admin", "supervisor", "comercial", "comercial_rafa", "comercial_jefe"],
                                             index=["admin", "supervisor", "comercial", "comercial_rafa",
                                                    "comercial_jefe"].index(usuario[1]))
                    nuevo_email = st.text_input("Nuevo Email", value=usuario[2])
                    nueva_contraseña = st.text_input("Nueva Contraseña", type="password")

                    if st.button("Guardar Cambios"):
                        editar_usuario(usuario_id, nuevo_nombre, nuevo_rol, nueva_contraseña, nuevo_email)
                else:
                    st.error("Usuario no encontrado.")

            st.subheader("Eliminar Usuario")
            eliminar_id = st.number_input("ID del Usuario a Eliminar", min_value=1, step=1)

            if eliminar_id:
                if st.button("Eliminar Usuario"):
                    eliminar_usuario(eliminar_id)


    # Opción: Cargar Nuevos Datos
    elif opcion == "Cargar Nuevos Datos":
        st.header("📤 Cargar Nuevos Datos")
        st.info(
            "ℹ️ Aquí puedes cargar un archivo Excel o CSV para reemplazar los datos existentes en la base de datos a una versión mas moderna. ¡ATENCIÓN! ¡Se eliminarán todos los datos actuales!")
        log_trazabilidad(
            st.session_state["username"],
            "Cargar Nuevos Datos",
            "El admin accedió a la sección de carga de nuevos datos y se procederá a reemplazar el contenido de la tabla."
        )

        uploaded_file = st.file_uploader("Selecciona un archivo Excel o CSV", type=["xlsx", "csv"])

        if uploaded_file is not None:
            try:
                with st.spinner("Cargando archivo..."):
                    if uploaded_file.name.endswith(".xlsx"):
                        data = pd.read_excel(uploaded_file)
                    elif uploaded_file.name.endswith(".csv"):
                        data = pd.read_csv(uploaded_file)

                columnas_requeridas = [
                    "id_ams", "apartment_id", "address_id", "provincia", "municipio", "poblacion",
                    "vial", "numero", "parcela_catastral", "letra", "cp", "site_operational_state",
                    "apartment_operational_state", "cto_id", "olt", "cto", "LATITUD", "LONGITUD",
                    "cto_con_proyecto", "COMERCIAL", "ZONA", "FECHA", "SERVICIABLE", "MOTIVO", "contrato_uis"
                ]

                columnas_faltantes = [col for col in columnas_requeridas if col not in data.columns]

                if columnas_faltantes:
                    st.error(
                        f"❌ El archivo no contiene las siguientes columnas requeridas: {', '.join(columnas_faltantes)}"
                    )
                else:
                    data_filtrada = data[columnas_requeridas].copy()
                    # Convertir LATITUD y LONGITUD a float, reemplazando comas por puntos
                    data_filtrada["LATITUD"] = data_filtrada["LATITUD"].astype(str).str.replace(",", ".").astype(float)
                    data_filtrada["LONGITUD"] = data_filtrada["LONGITUD"].astype(str).str.replace(",", ".").astype(
                        float)

                    st.write("Datos filtrados correctamente. Procediendo a reemplazar los datos en la base de datos...")
                    conn = obtener_conexion()
                    cursor = conn.cursor()

                    # Borramos todos los registros de la tabla
                    cursor.execute("DELETE FROM datos_uis")
                    # Reiniciamos el ID autoincremental
                    cursor.execute("DELETE FROM sqlite_sequence WHERE name='datos_uis'")
                    conn.commit()

                    # Preparamos los datos para la inserción
                    insert_values = []
                    for index, row in data_filtrada.iterrows():
                        insert_values.append((
                            row["id_ams"],
                            row["apartment_id"],
                            row["address_id"],
                            row["provincia"],
                            row["municipio"],
                            row["poblacion"],
                            row["vial"],
                            row["numero"],
                            row["parcela_catastral"],
                            row["letra"],
                            row["cp"],
                            row["site_operational_state"],
                            row["apartment_operational_state"],
                            row["cto_id"],
                            row["olt"],
                            row["cto"],
                            row["LATITUD"],
                            row["LONGITUD"],
                            row["cto_con_proyecto"],
                            row["COMERCIAL"],
                            row["ZONA"],
                            row["FECHA"],
                            row["SERVICIABLE"],
                            row["MOTIVO"],
                            row["contrato_uis"]
                        ))

                    # Insertamos todos los registros en un solo lote
                    cursor.executemany("""
                        INSERT INTO datos_uis (
                            id_ams, apartment_id, address_id, provincia, municipio, poblacion, vial, numero, 
                            parcela_catastral, letra, cp, site_operational_state, apartment_operational_state, 
                            cto_id, olt, cto, LATITUD, LONGITUD, cto_con_proyecto, COMERCIAL, ZONA, FECHA, 
                            SERVICIABLE, MOTIVO, contrato_uis
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, insert_values)

                    conn.commit()
                    conn.close()

                    st.success(f"Datos reemplazados exitosamente. Total registros cargados: {len(insert_values)}")
                    log_trazabilidad(
                        st.session_state["username"],
                        "Cargar Nuevos Datos",
                        f"El admin reemplazó los datos existentes con {len(insert_values)} nuevos registros."
                    )
            except Exception as e:
                st.error(f"❌ Error al cargar el archivo: {e}")

    # Opción: Trazabilidad y logs
    elif opcion == "Trazabilidad y logs":
        st.header("📜 Trazabilidad y logs")
        st.info("ℹ️ Aquí se pueden visualizar los logs y la trazabilidad de las acciones realizadas. Puedes utilizar las etiquetas rojas para filtrar la tabla y "
                "descargar los datos relevantes en formato excel y csv.")
        log_trazabilidad(st.session_state["username"], "Visualización de Trazabilidad",
                         "El admin visualizó la sección de trazabilidad y logs.")

        with st.spinner("Cargando trazabilidad..."):
            try:
                conn = sqlite3.connect("data/usuarios.db")
                query = "SELECT usuario_id, accion, detalles, fecha FROM trazabilidad"
                trazabilidad_data = pd.read_sql(query, conn)
                conn.close()
                if trazabilidad_data.empty:
                    st.info("No hay registros de trazabilidad para mostrar.")
                else:
                    if trazabilidad_data.columns.duplicated().any():
                        st.warning("¡Se encontraron columnas duplicadas! Se eliminarán las duplicadas.")
                        trazabilidad_data = trazabilidad_data.loc[:, ~trazabilidad_data.columns.duplicated()]

                    columnas = st.multiselect("Selecciona las columnas a mostrar", trazabilidad_data.columns.tolist(),
                                              default=trazabilidad_data.columns.tolist())
                    st.dataframe(trazabilidad_data[columnas], use_container_width=True)

                    download_format = st.radio("Selecciona el formato de descarga:", ["Excel", "CSV"],
                                               key="trazabilidad_download")
                    if download_format == "Excel":
                        towrite = io.BytesIO()
                        with pd.ExcelWriter(towrite, engine='xlsxwriter') as writer:
                            trazabilidad_data[columnas].to_excel(writer, index=False, sheet_name='Trazabilidad')
                        towrite.seek(0)
                        with st.spinner("Preparando archivo Excel..."):
                            st.download_button(
                                label="📥 Descargar Excel",
                                data=towrite,
                                file_name="trazabilidad.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
                    elif download_format == "CSV":
                        csv = trazabilidad_data[columnas].to_csv(index=False).encode()
                        with st.spinner("Preparando archivo CSV..."):
                            st.download_button(
                                label="📥 Descargar CSV",
                                data=csv,
                                file_name="trazabilidad.csv",
                                mime="text/csv"
                            )
            except Exception as e:
                st.error(f"❌ Error al cargar la trazabilidad: {e}")

    elif opcion == "Control de versiones":
        log_trazabilidad(st.session_state["username"], "Control de versiones", "El admin accedió a la sección de control de versiones.")
        mostrar_control_versiones()

# Función para leer y mostrar el control de versiones
def mostrar_control_versiones():
    try:
        # Leer el archivo version.txt
        with open("modules/version.txt", "r", encoding="utf-8") as file:
            versiones = file.readlines()

        # Mostrar el encabezado de la sección
        st.subheader("🔄 Control de versiones")
        st.info("ℹ️ Aquí puedes ver el historial de cambios y versiones de la aplicación. Cada entrada incluye el número de versión y una breve descripción de lo que se ha actualizado o modificado.")
        # Formato para mostrar las versiones con diseño más elegante

        # Mostrar las versiones en formato de lista bonita
        for version in versiones:
            version_info = version.strip().split(" - ")
            if len(version_info) == 2:
                st.markdown(
                    f"<div style='background-color: #f7f7f7; padding: 15px; border-radius: 8px; margin-bottom: 15px;'>"
                    f"<h4 style='color: #4CAF50; font-size: 18px;'>{version_info[0]}</h4>"
                    f"<p style='font-size: 14px; color: #666;'>{version_info[1]}</p>"
                    f"</div>", unsafe_allow_html=True
                )
            else:
                st.markdown(
                    f"<div style='background-color: #f7f7f7; padding: 15px; border-radius: 8px; margin-bottom: 15px;'>"
                    f"<h4 style='color: #4CAF50; font-size: 18px;'>{version_info[0]}</h4>"
                    f"<p style='font-size: 14px; color: #666;'>Sin descripción disponible.</p>"
                    f"</div>", unsafe_allow_html=True)

        # Añadir una pequeña nota técnica para el admin con una fuente diferenciada
        st.markdown("<br><i style='font-size: 14px; color: #888;'>Nota técnica: Esta sección muestra el historial completo de cambios aplicados al sistema. Asegúrese de revisar las versiones anteriores para comprender las mejoras y correcciones implementadas.</i>", unsafe_allow_html=True)

    except FileNotFoundError:
        st.error("El archivo `version.txt` no se encuentra en el sistema.")
    except Exception as e:
        st.error(f"Ha ocurrido un error al cargar el control de versiones: {e}")

#HOME Y GRAFICOS ASOCIADOS
# Función para crear el gráfico interactivo de Serviciabilidad
def create_serviciable_graph(cursor):
    cursor.execute("""
        SELECT serviciable, COUNT(*) 
        FROM datos_uis 
        GROUP BY serviciable
    """)
    data = cursor.fetchall()
    df = pd.DataFrame(data, columns=["serviciable", "count"])

    # Crear gráfico interactivo de barras con Plotly
    fig = px.bar(df, x="serviciable", y="count", title="Distribución de Serviciabilidad",
                 labels={"serviciable": "Serviciable", "count": "Cantidad"},
                 color="serviciable", color_discrete_sequence=px.colors.qualitative.Set2)
    fig.update_layout(barmode='group', height=300)
    return fig

# Función para crear el gráfico interactivo de Incidencias por Provincia
def create_incidencias_graph(cursor):
    cursor.execute("""
        SELECT provincia, COUNT(*) 
        FROM ofertas_comercial
        WHERE incidencia IS NOT NULL
        GROUP BY provincia
    """)
    data = cursor.fetchall()
    df = pd.DataFrame(data, columns=["provincia", "count"])

    # Crear gráfico interactivo de barras con Plotly
    fig = px.bar(df, x="provincia", y="count", title="Incidencias por Provincia",
                 labels={"provincia": "Provincia", "count": "Cantidad"},
                 color="provincia", color_discrete_sequence=px.colors.qualitative.Pastel)
    fig.update_layout(barmode='group', height=300)
    fig.update_xaxes(tickangle=45)  # Rotar las etiquetas de los ejes X
    return fig

# Función para crear el gráfico interactivo de Motivos de Serviciabilidad
def create_motivos_serviciabilidad_graph(cursor):
    cursor.execute("""
        SELECT motivo_serviciable, COUNT(*) 
        FROM ofertas_comercial
        GROUP BY motivo_serviciable
    """)
    data = cursor.fetchall()
    df = pd.DataFrame(data, columns=["motivo_serviciable", "count"])

    # Crear gráfico interactivo de barras con Plotly
    fig = px.bar(df, x="motivo_serviciable", y="count", title="Motivos de Serviciabilidad",
                 labels={"motivo_serviciable": "Motivo", "count": "Cantidad"},
                 color="motivo_serviciable", color_discrete_sequence=px.colors.qualitative.Dark24)
    fig.update_layout(barmode='group', height=300)
    fig.update_xaxes(tickangle=45)  # Rotar las etiquetas de los ejes X
    return fig

# Gráfico de la distribución geográfica de los apartamentos (basado en latitud y longitud)
def create_geographic_distribution_graph(cursor):
    cursor.execute("""
        SELECT latitud, longitud 
        FROM datos_uis
    """)
    data = cursor.fetchall()
    df = pd.DataFrame(data, columns=["latitud", "longitud"])

    # Crear gráfico interactivo de dispersión en el mapa con Plotly
    fig = px.scatter_geo(df, lat="latitud", lon="longitud", title="Distribución Geográfica de los Apartamentos",
                         scope="world", height=400)
    return fig

# Gráfico de Incidencias por Mes
def create_incidencias_by_month_graph(cursor):
    cursor.execute("""
        SELECT strftime('%Y-%m', fecha), COUNT(*) 
        FROM ofertas_comercial
        WHERE incidencia IS NOT NULL
        GROUP BY strftime('%Y-%m', fecha)
    """)
    data = cursor.fetchall()
    df = pd.DataFrame(data, columns=["Mes", "Cantidad"])

    # Crear gráfico interactivo de líneas con Plotly
    fig = px.line(df, x="Mes", y="Cantidad", title="Incidencias por Mes",
                  labels={"Mes": "Mes", "Cantidad": "Número de Incidencias"})
    fig.update_layout(height=300)
    return fig

# Gráfico de Costes de Viabilidades
def create_coste_viabilidad_graph(cursor):
    cursor.execute("""
        SELECT coste 
        FROM viabilidades
    """)
    data = cursor.fetchall()
    df = pd.DataFrame(data, columns=["coste"])

    # Crear gráfico interactivo de histograma con Plotly
    fig = px.histogram(df, x="coste", title="Distribución de Costes de Viabilidad",
                        labels={"coste": "Coste"}, nbins=20)
    fig.update_layout(height=300)
    return fig

# Gráfico Promedio de Coste de Viabilidad por Provincia
def create_avg_cost_by_province_graph(cursor):
    cursor.execute("""
        SELECT provincia, AVG(coste) 
        FROM viabilidades
        GROUP BY provincia
    """)
    data = cursor.fetchall()
    df = pd.DataFrame(data, columns=["provincia", "avg_cost"])

    # Crear gráfico interactivo de barras con Plotly
    fig = px.bar(df, x="provincia", y="avg_cost", title="Promedio de Coste de Viabilidad por Provincia",
                 labels={"provincia": "Provincia", "avg_cost": "Promedio de Coste"})
    fig.update_layout(height=300)
    return fig

# Gráfico Número de Incidencias por Cliente
def create_incidencias_by_cliente_graph(cursor):
    cursor.execute("""
        SELECT nombre_cliente, COUNT(*) 
        FROM ofertas_comercial
        WHERE incidencia IS NOT NULL
        GROUP BY nombre_cliente
        ORDER BY COUNT(*) DESC
        LIMIT 10
    """)
    data = cursor.fetchall()
    df = pd.DataFrame(data, columns=["nombre_cliente", "incidencias_count"])

    # Crear gráfico interactivo de barras con Plotly
    fig = px.bar(df, x="nombre_cliente", y="incidencias_count", title="Top 10 Clientes con Más Incidencias",
                 labels={"nombre_cliente": "Cliente", "incidencias_count": "Número de Incidencias"})
    fig.update_layout(height=300)
    fig.update_xaxes(tickangle=45)  # Rotar etiquetas de ejes X
    return fig

# Gráfico Distribución de Tipos de Vivienda
def create_tipo_vivienda_distribution_graph(cursor):
    cursor.execute("""
        SELECT Tipo_Vivienda, COUNT(*) 
        FROM comercial_rafa
        GROUP BY Tipo_Vivienda
    """)
    data = cursor.fetchall()
    df = pd.DataFrame(data, columns=["Tipo_Vivienda", "count"])

    # Crear gráfico interactivo de barras con Plotly
    fig = px.bar(df, x="Tipo_Vivienda", y="count", title="Distribución de Tipos de Vivienda",
                 labels={"Tipo_Vivienda": "Tipo de Vivienda", "count": "Cantidad"})
    fig.update_layout(height=300)
    return fig

# Gráfico de Tendencia de Cambio de Estado Operacional por Provincia
def create_operational_state_trend_graph(cursor):
    cursor.execute("""
        SELECT strftime('%Y-%m', fecha) AS month, provincia, COUNT(*) 
        FROM datos_uis
        WHERE apartment_operational_state IS NOT NULL
        GROUP BY month, provincia
    """)
    data = cursor.fetchall()
    df = pd.DataFrame(data, columns=["Mes", "Provincia", "Count"])

    # Crear gráfico interactivo de líneas con Plotly
    fig = px.line(df, x="Mes", y="Count", color="Provincia", title="Tendencia de Cambio de Estado Operacional por Provincia",
                  labels={"Mes": "Mes", "Count": "Cantidad de Cambios", "Provincia": "Provincia"})
    fig.update_layout(height=300)
    return fig

# Gráfico de Viabilidades por Municipio
def create_viabilities_by_municipio_graph(cursor):
    cursor.execute("""
        SELECT municipio, COUNT(*) 
        FROM viabilidades
        GROUP BY municipio
    """)
    data = cursor.fetchall()
    df = pd.DataFrame(data, columns=["municipio", "count"])

    # Crear gráfico interactivo de barras con Plotly
    fig = px.bar(df, x="municipio", y="count", title="Viabilidades por Municipio",
                 labels={"municipio": "Municipio", "count": "Cantidad de Viabilidades"})
    fig.update_layout(height=300)
    fig.update_xaxes(tickangle=45)  # Rotar etiquetas de ejes X
    return fig

# Gráfico de Distribución de Incidencias por Tipo de Incidencia
def create_incidencias_by_tipo_graph(cursor):
    cursor.execute("""
        SELECT incidencia, COUNT(*) 
        FROM ofertas_comercial
        WHERE incidencia IS NOT NULL
        GROUP BY incidencia
    """)
    data = cursor.fetchall()
    df = pd.DataFrame(data, columns=["incidencia", "count"])

    # Crear gráfico interactivo de barras con Plotly
    fig = px.bar(df, x="incidencia", y="count", title="Distribución de Incidencias por Tipo de Incidencia",
                 labels={"incidencia": "Tipo de Incidencia", "count": "Cantidad"})
    fig.update_layout(height=300)
    return fig

# Función principal de la página
def home_page():
    st.title("Resumen de datos relevantes")
    st.info("🏗️ ZONA EN CONSTRUCCIÓN")

    # Obtener la conexión y el cursor
    conn = obtener_conexion()
    cursor = conn.cursor()

    try:
        # Mostrar resúmenes y gráficos
        st.header("Resumen de Datos")

        # Organizar los gráficos en columnas
        col1, col2, col3 = st.columns(3)

        # Gráfico de Serviciabilidad
        with col1:
            st.plotly_chart(create_serviciable_graph(cursor))

        # Gráfico de Incidencias por Provincia
        with col2:
            st.plotly_chart(create_incidencias_graph(cursor))

        # Gráfico de Motivos de Serviciabilidad
        with col3:
            st.plotly_chart(create_motivos_serviciabilidad_graph(cursor))

        # Gráfico de Incidencias por Mes
        with col1:
            st.plotly_chart(create_incidencias_by_month_graph(cursor))

        # Gráfico de Costes de Viabilidad
        with col2:
            st.plotly_chart(create_coste_viabilidad_graph(cursor))

        # Gráfico de Distribución Geográfica
        with col3:
            st.plotly_chart(create_geographic_distribution_graph(cursor))
        # Gráfico Promedio de Coste de Viabilidad por Provincia
        with col1:
            st.plotly_chart(create_avg_cost_by_province_graph(cursor))

        # Gráfico de Número de Incidencias por Cliente
        with col2:
            st.plotly_chart(create_incidencias_by_cliente_graph(cursor))

        # Gráfico de Distribución de Tipos de Vivienda
        with col3:
            st.plotly_chart(create_tipo_vivienda_distribution_graph(cursor))

        # Gráfico de Tendencia de Cambio de Estado Operacional por Provincia
        with col1:
            st.plotly_chart(create_operational_state_trend_graph(cursor))

        # Gráfico de Viabilidades por Municipio
        with col2:
            st.plotly_chart(create_viabilities_by_municipio_graph(cursor))

        # Distribución de Incidencias por Tipo de Incidencia**
        with col3:
            st.plotly_chart(create_incidencias_by_tipo_graph(cursor))

    except Exception as e:
        st.error(f"Hubo un error al cargar los gráficos: {e}")
        print(f"Error al generar los gráficos: {e}")
    finally:
        conn.close()  # No olvides cerrar la conexión al final
#######

if __name__ == "__main__":
    admin_dashboard()
