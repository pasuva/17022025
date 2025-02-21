import zipfile

from folium.plugins import Geocoder
import folium
import streamlit as st
import pandas as pd
import io  # Necesario para trabajar con flujos de bytes
import sqlite3
import datetime
import bcrypt
from folium.plugins import MarkerCluster
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import os  # Para trabajar con archivos en el sistema
import base64  # Para codificar la imagen en base64
import streamlit as st

# Función de trazabilidad
from datetime import datetime as dt  # Para evitar conflicto con datetime

from streamlit_folium import st_folium


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
            cursor.execute("SELECT id, username, role FROM usuarios")
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
def agregar_usuario(username, rol, password):
    conn = obtener_conexion()
    cursor = conn.cursor()
    hashed_pw = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    try:
        cursor.execute("INSERT INTO usuarios (username, password, role) VALUES (?, ?, ?)", (username, hashed_pw, rol))
        conn.commit()
        st.success(f"Usuario '{username}' creado con éxito.")
        log_trazabilidad(st.session_state["username"], "Agregar Usuario",
                         f"El admin agregó al usuario '{username}' con rol '{rol}'.")
    except sqlite3.IntegrityError:
        st.error(f"El usuario '{username}' ya existe.")
    finally:
        conn.close()


# Función para editar un usuario existente
def editar_usuario(id, username, rol, password):
    conn = obtener_conexion()
    cursor = conn.cursor()
    hashed_pw = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode() if password else None

    if password:
        cursor.execute("UPDATE usuarios SET username = ?, role = ?, password = ? WHERE id = ?",
                       (username, rol, hashed_pw, id))
    else:
        cursor.execute("UPDATE usuarios SET username = ?, role = ? WHERE id = ?", (username, rol, id))

    conn.commit()
    conn.close()
    st.success(f"Usuario con ID {id} actualizado correctamente.")
    log_trazabilidad(st.session_state["username"], "Editar Usuario", f"El admin editó al usuario con ID {id}.")


# Función para eliminar un usuario
def eliminar_usuario(id):
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM usuarios WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    st.success(f"Usuario con ID {id} eliminado correctamente.")
    log_trazabilidad(st.session_state["username"], "Eliminar Usuario", f"El admin eliminó al usuario con ID {id}.")


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
        st.dataframe(viabilidades_df, use_container_width=True)

        # Añadir un botón de refresco para actualizar la tabla
        if st.button("🔄 Refrescar Tabla"):
            st.rerun()  # Utiliza st.rerun() en lugar de st.experimental_rerun()

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
            # Conectar a la base de datos
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

            # Confirmar los cambios y cerrar la conexión
            conn.commit()
            conn.close()

            # Mostrar mensaje de éxito
            st.success(f"✅ Los cambios para el Ticket {ticket} han sido guardados correctamente.")

        except Exception as e:
            st.error(f"❌ Hubo un error al guardar los cambios: {e}")



# Función principal de la app (Dashboard de administración)
def admin_dashboard():
    """Panel del administrador."""
    st.set_page_config(page_title="Panel de Administración", page_icon="📊", layout="wide")

    # Personalizar la barra lateral
    st.sidebar.title("📊 Panel de Administración")
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

    # Opciones de navegación con iconos
    opcion = st.sidebar.radio(
        "Selecciona una opción:",
        ("📈 Ver Datos", "📊 Ofertas Comerciales", "✔️ Viabilidades", "📤 Cargar Nuevos Datos", "📑 Generador de informes",
         "📜 Trazabilidad y logs", "👥 Gestionar Usuarios", "⚙️ Ajustes"),
        index=0,
        key="menu",
    )

    # Registrar la selección de la opción en trazabilidad
    log_trazabilidad(st.session_state["username"], "Selección de opción", f"El admin seleccionó la opción '{opcion}'.")

    # Botón de Cerrar sesión en la barra lateral
    with st.sidebar:
        if st.button("Cerrar sesión"):
            log_trazabilidad(st.session_state["username"], "Cierre sesión",
                             f"El admin {st.session_state['username']} cerró sesión.")
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.success("✅ Has cerrado sesión correctamente. Redirigiendo al login...")
            st.rerun()

    # Opción: Visualizar datos de la tabla datos_uis
    if opcion == "📈 Ver Datos":
        st.header("📊 Visualizar y gestionar datos (Datos UIS)")
        st.write("Aquí puedes cargar y gestionar la base de datos de datos_uis.")

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
        st.write("Filtra las columnas del dataframe:")
        columnas = st.multiselect("Selecciona las columnas a mostrar", data.columns.tolist(),
                                  default=data.columns.tolist())
        st.dataframe(data[columnas], use_container_width=True)

        st.subheader("Selecciona el formato para la descarga:")
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

    # Opción: Visualizar datos de la tabla ofertas_comercial
    elif opcion == "📊 Ofertas Comerciales":
        st.header("📊 Visualizar Ofertas Comerciales")
        st.write("Aquí puedes ver las ofertas comerciales registradas.")

        if "df" in st.session_state:
            del st.session_state["df"]

        with st.spinner("Cargando ofertas comerciales..."):
            try:
                conn = sqlite3.connect("data/usuarios.db")
                query_tables = "SELECT name FROM sqlite_master WHERE type='table';"
                tables = pd.read_sql(query_tables, conn)
                if 'ofertas_comercial' not in tables['name'].values:
                    st.error("❌ La tabla 'ofertas_comercial' no se encuentra en la base de datos.")
                    conn.close()
                    return
                query = "SELECT * FROM ofertas_comercial"
                data = pd.read_sql(query, conn)
                conn.close()
                if data.empty:
                    st.error("❌ No se encontraron ofertas comerciales en la base de datos.")
                    return
            except Exception as e:
                st.error(f"❌ Error al cargar ofertas comerciales de la base de datos: {e}")
                return

        if data.columns.duplicated().any():
            st.warning("¡Se encontraron columnas duplicadas! Se eliminarán las duplicadas.")
            data = data.loc[:, ~data.columns.duplicated()]

        st.session_state["df"] = data
        st.write("Filtra las columnas del dataframe:")
        columnas = st.multiselect("Selecciona las columnas a mostrar", data.columns.tolist(),
                                  default=data.columns.tolist())
        st.dataframe(data[columnas], use_container_width=True)

        st.subheader("Selecciona el formato para la descarga:")
        download_format = st.radio("Selecciona el formato de descarga:", ["Excel", "CSV"], key="oferta_download")
        if download_format == "Excel":
            towrite = io.BytesIO()
            with pd.ExcelWriter(towrite, engine='xlsxwriter') as writer:
                data[columnas].to_excel(writer, index=False, sheet_name='Ofertas')
            towrite.seek(0)
            with st.spinner("Preparando archivo Excel..."):
                st.download_button(
                    label="📥 Descargar Excel",
                    data=towrite,
                    file_name="ofertas_comerciales.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        elif download_format == "CSV":
            csv = data[columnas].to_csv(index=False).encode()
            with st.spinner("Preparando archivo CSV..."):
                st.download_button(
                    label="📥 Descargar CSV",
                    data=csv,
                    file_name="ofertas_comerciales.csv",
                    mime="text/csv"
                )

        # Desplegable para ofertas con imagen
        offers_with_image = []
        for idx, row in data.iterrows():
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
    elif opcion == "✔️ Viabilidades":
        st.header("✔️ Viabilidades")
        st.write("Esta sección está en construcción. Pronto podrás consultar las viabilidades aquí.")
        viabilidades_seccion()

    # Opción: Generar Informes
    elif opcion == "📑 Generador de informes":
        st.header("📑 Generador de Informes")
        st.write("Aquí puedes generar informes basados en los datos disponibles.")
        log_trazabilidad(st.session_state["username"], "Generar Informe", "El admin accedió al generador de informes.")

        # Selección de tipo de informe
        informe_tipo = st.selectbox("Selecciona el tipo de informe:",
                                    ["Informe de Datos UIS", "Informe de Ofertas Comerciales"])

        # Filtros comunes para ambos informes
        st.sidebar.subheader("Filtros de Información")

        df_filtrado = st.session_state.get("df", pd.DataFrame())
        columnas_disponibles = df_filtrado.columns.tolist() if not df_filtrado.empty else []

        filtro_columna = st.selectbox("Selecciona la columna para filtrar en Datos UIS:",
                                      columnas_disponibles) if columnas_disponibles else None

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
            if filtro_columna and st.text_input(f"Filtra por {filtro_columna}:"):
                valor_filtro = st.text_input(f"Filtra por {filtro_columna}:")
                df_filtrado = df_filtrado[
                    df_filtrado[filtro_columna].astype(str).str.contains(valor_filtro, case=False)]
            if "provincia" in df_filtrado.columns and provincias != "Todas":
                df_filtrado = df_filtrado[df_filtrado["provincia"] == provincias]
            if "fecha" in df_filtrado.columns:
                df_filtrado = df_filtrado[df_filtrado["fecha"].between(fecha_inicio, fecha_fin)]

        elif informe_tipo == "Informe de Ofertas Comerciales":
            st.write("Generando informe para las ofertas comerciales...")
            ofertas_filtradas = st.session_state.get("df", pd.DataFrame())
            columnas_ofertas = ofertas_filtradas.columns.tolist() if not ofertas_filtradas.empty else []
            filtro_columna_ofertas = st.selectbox("Selecciona la columna para filtrar en Ofertas Comerciales:",
                                                  columnas_ofertas) if columnas_ofertas else None
            if "provincia" in ofertas_filtradas.columns:
                provincias_ofertas = st.selectbox("Selecciona la provincia para ofertas:",
                                                  ["Todas"] + ofertas_filtradas.provincia.unique().tolist())
            if "fecha" in ofertas_filtradas.columns:
                ofertas_filtradas['fecha'] = pd.to_datetime(ofertas_filtradas['fecha'], errors='coerce')
                fecha_inicio_oferta = st.date_input("Fecha de inicio para ofertas:", pd.to_datetime("2022-01-01"))
                fecha_fin_oferta = st.date_input("Fecha de fin para ofertas:", pd.to_datetime("2025-12-31"))
                fecha_inicio_oferta = pd.to_datetime(fecha_inicio_oferta)
                fecha_fin_oferta = pd.to_datetime(fecha_fin_oferta)
            if filtro_columna_ofertas and st.text_input(f"Filtra por {filtro_columna_ofertas}:"):
                valor_filtro_oferta = st.text_input(f"Filtra por {filtro_columna_ofertas}:")
                ofertas_filtradas = ofertas_filtradas[
                    ofertas_filtradas[filtro_columna_ofertas].astype(str).str.contains(valor_filtro_oferta, case=False)]
            if "provincia" in ofertas_filtradas.columns and provincias_ofertas != "Todas":
                ofertas_filtradas = ofertas_filtradas[ofertas_filtradas["provincia"] == provincias_ofertas]
            if "fecha" in ofertas_filtradas.columns:
                ofertas_filtradas = ofertas_filtradas[
                    ofertas_filtradas["fecha"].between(fecha_inicio_oferta, fecha_fin_oferta)]

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

    # Opción: Gestionar Usuarios
    elif opcion == "👥 Gestionar Usuarios":
        st.header("👥 Gestionar Usuarios")
        st.write("Aquí puedes gestionar los usuarios registrados.")
        log_trazabilidad(st.session_state["username"], "Gestionar Usuarios",
                         "El admin accedió a la sección de gestión de usuarios.")

        usuarios = cargar_usuarios()
        if usuarios:
            st.subheader("Lista de Usuarios")
            df_usuarios = pd.DataFrame(usuarios, columns=["ID", "Nombre", "Rol"])
            st.dataframe(df_usuarios)

        st.subheader("Agregar Nuevo Usuario")
        nombre = st.text_input("Nombre del Usuario")
        rol = st.selectbox("Selecciona el Rol", ["admin", "supervisor", "comercial"])
        password = st.text_input("Contraseña", type="password")
        if st.button("Agregar Usuario"):
            if nombre and password:
                agregar_usuario(nombre, rol, password)
            else:
                st.error("Por favor, completa todos los campos.")

        st.subheader("Editar Usuario")
        usuario_id = st.number_input("ID del Usuario a Editar", min_value=1, step=1)
        if usuario_id:
            conn = obtener_conexion()
            cursor = conn.cursor()
            cursor.execute("SELECT username, role FROM usuarios WHERE id = ?", (usuario_id,))
            usuario = cursor.fetchone()
            conn.close()
            if usuario:
                nuevo_nombre = st.text_input("Nuevo Nombre", value=usuario[0])
                nuevo_rol = st.selectbox("Nuevo Rol", ["admin", "supervisor", "comercial"],
                                         index=["admin", "supervisor", "comercial"].index(usuario[1]))
                nueva_contraseña = st.text_input("Nueva Contraseña", type="password")
                if st.button("Guardar Cambios"):
                    editar_usuario(usuario_id, nuevo_nombre, nuevo_rol, nueva_contraseña)
            else:
                st.error("Usuario no encontrado.")

        st.subheader("Eliminar Usuario")
        eliminar_id = st.number_input("ID del Usuario a Eliminar", min_value=1, step=1)
        if eliminar_id:
            if st.button("Eliminar Usuario"):
                eliminar_usuario(eliminar_id)

    # Opción: Cargar Nuevos Datos
    elif opcion == "📤 Cargar Nuevos Datos":
        st.header("📤 Cargar Nuevos Datos")
        st.write("Aquí puedes cargar un archivo Excel o CSV para agregar nuevos datos a la base de datos.")
        log_trazabilidad(st.session_state["username"], "Cargar Nuevos Datos",
                         "El admin accedió a la sección de carga de nuevos datos.")

        uploaded_file = st.file_uploader("Selecciona un archivo Excel o CSV", type=["xlsx", "csv"])

        if uploaded_file is not None:
            try:
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

                data_filtrada = data[columnas_requeridas] if all(
                    col in data.columns for col in columnas_requeridas) else None

                if data_filtrada is not None:
                    st.write("Datos filtrados correctamente. Procediendo a cargar en la base de datos...")
                    conn = obtener_conexion()
                    cursor = conn.cursor()

                    for index, row in data_filtrada.iterrows():
                        cursor.execute("""SELECT * FROM datos_uis WHERE apartment_id = ?""", (row['apartment_id'],))
                        if not cursor.fetchone():
                            latitud = float(row["LATITUD"].replace(",", "."))
                            longitud = float(row["LONGITUD"].replace(",", "."))
                            cursor.execute("""INSERT INTO datos_uis (id_ams, apartment_id, address_id, provincia, 
                                              municipio, poblacion, vial, numero, parcela_catastral, letra, cp, 
                                              site_operational_state, apartment_operational_state, cto_id, olt, 
                                              cto, LATITUD, LONGITUD, cto_con_proyecto, COMERCIAL, ZONA, FECHA, 
                                              SERVICIABLE, MOTIVO, contrato_uis) 
                                              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                           (row["id_ams"], row["apartment_id"], row["address_id"], row["provincia"],
                                            row["municipio"], row["poblacion"], row["vial"], row["numero"],
                                            row["parcela_catastral"], row["letra"], row["cp"],
                                            row["site_operational_state"],
                                            row["apartment_operational_state"], row["cto_id"], row["olt"], row["cto"],
                                            latitud, longitud, row["cto_con_proyecto"], row["COMERCIAL"], row["ZONA"],
                                            row["FECHA"], row["SERVICIABLE"], row["MOTIVO"], row["contrato_uis"]))
                    conn.commit()
                    conn.close()
                    st.success("Datos cargados exitosamente.")
                    log_trazabilidad(st.session_state["username"], "Cargar Nuevos Datos",
                                     "El admin cargó nuevos datos al sistema.")
                else:
                    st.error("❌ El archivo no contiene las columnas requeridas o está mal formateado.")
            except Exception as e:
                st.error(f"❌ Error al cargar el archivo: {e}")

    # Opción: Trazabilidad y logs
    elif opcion == "📜 Trazabilidad y logs":
        st.header("📜 Trazabilidad y logs")
        st.write("Aquí se pueden visualizar los logs y la trazabilidad de las acciones realizadas.")
        log_trazabilidad(st.session_state["username"], "Visualización de Trazabilidad",
                         "El admin visualizó la sección de trazabilidad y logs.")

        with st.spinner("Cargando trazabilidad..."):
            try:
                conn = sqlite3.connect("data/usuarios.db")
                query = "SELECT * FROM trazabilidad"
                trazabilidad_data = pd.read_sql(query, conn)
                conn.close()
                if trazabilidad_data.empty:
                    st.info("No hay registros de trazabilidad para mostrar.")
                else:
                    if trazabilidad_data.columns.duplicated().any():
                        st.warning("¡Se encontraron columnas duplicadas! Se eliminarán las duplicadas.")
                        trazabilidad_data = trazabilidad_data.loc[:, ~trazabilidad_data.columns.duplicated()]

                    st.write("Filtra las columnas del dataframe:")
                    columnas = st.multiselect("Selecciona las columnas a mostrar", trazabilidad_data.columns.tolist(),
                                              default=trazabilidad_data.columns.tolist())
                    st.dataframe(trazabilidad_data[columnas], use_container_width=True)

                    st.subheader("Selecciona el formato para la descarga:")
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

    elif opcion == "⚙️ Ajustes":
        st.header("⚙️ Ajustes")
        st.write("Aquí puedes configurar los ajustes de la aplicación.")
        log_trazabilidad(st.session_state["username"], "Ajustes", "El admin accedió a la sección de ajustes.")


if __name__ == "__main__":
    admin_dashboard()
