import zipfile, folium, sqlite3, datetime, bcrypt, os, sqlitecloud, io
import pandas as pd
import plotly.express as px
import streamlit as st
from modules.notificaciones import correo_viabilidad_administracion, correo_usuario
from datetime import datetime as dt  # Para evitar conflicto con datetime
from streamlit_option_menu import option_menu
from datetime import datetime
from streamlit_cookies_controller import CookieController  # Se importa localmente
from folium.plugins import MarkerCluster, Geocoder
from streamlit_folium import st_folium
import plotly.graph_objects as go

cookie_name = "my_app"

# Función para obtener conexión a la base de datos
def obtener_conexion():
    """Retorna una nueva conexión a la base de datos."""
    try:
        conn = sqlitecloud.connect(
            "sqlitecloud://ceafu04onz.g6.sqlite.cloud:8860/usuarios.db?apikey=Qo9m18B9ONpfEGYngUKm99QB5bgzUTGtK7iAcThmwvY")
        return conn
    except sqlite3.Error as e:
        print(f"Error al conectar con la base de datos: {e}")
        return None

def log_trazabilidad(usuario, accion, detalles):
    """Inserta un registro en la tabla de trazabilidad."""
    try:
        conn = obtener_conexion()
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

# Función para convertir a numérico y manejar excepciones
def safe_convert_to_numeric(col):
    try:
        return pd.to_numeric(col)
    except ValueError:
        return col  # Si ocurre un error, regresamos la columna original sin cambios

def cargar_usuarios():
    """Carga los usuarios desde la base de datos."""
    conn = obtener_conexion()
    if not conn:
        return []  # Salida temprana si la conexión falla

    try:
        with conn:  # `with` cierra automáticamente
            return conn.execute("SELECT id, username, role, email FROM usuarios").fetchall()
    except sqlite3.Error as e:
        print(f"Error al cargar los usuarios: {e}")
        return []

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
        asunto = "¡Detalles de tu cuenta actualizados!"
        mensaje = (
            f"📢 Se han realizado cambios en tu cuenta con los siguientes detalles:<br><br>"
            f"{''.join([f'<strong>{cambio}</strong><br>' for cambio in cambios])}"  # Unimos los cambios en un formato adecuado
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

def cargar_datos_uis():
    """Carga y cachea los datos de las tablas 'datos_uis', 'ofertas_comercial' y 'comercial_rafa'."""
    conn = obtener_conexion()

    # Consulta de datos_uis
    query_datos_uis = """
        SELECT apartment_id, latitud, longitud, provincia, municipio, poblacion, cto_con_proyecto, serviciable,
               vial, numero, letra, cp, cto_id, cto, site_operational_state, apartment_operational_state, zona
        FROM datos_uis
    """
    datos_uis = pd.read_sql(query_datos_uis, conn)

    # Consulta de ofertas_comercial
    query_ofertas = """
        SELECT apartment_id, serviciable, Contrato, provincia, municipio, poblacion,
               motivo_serviciable, incidencia, motivo_incidencia, nombre_cliente,
               telefono, direccion_alternativa, observaciones, comercial, comentarios
        FROM ofertas_comercial
    """
    ofertas_df = pd.read_sql(query_ofertas, conn)

    # Consulta de comercial_rafa
    query_rafa = """
        SELECT apartment_id, serviciable, Contrato, provincia, municipio, poblacion,
               motivo_serviciable, incidencia, motivo_incidencia, nombre_cliente,
               telefono, direccion_alternativa, observaciones, comercial, comentarios
        FROM comercial_rafa
    """
    comercial_rafa_df = pd.read_sql(query_rafa, conn)

    conn.close()
    return datos_uis, ofertas_df, comercial_rafa_df

def limpiar_mapa():
    """Evita errores de re-inicialización del mapa"""
    st.write("### Mapa actualizado")  # Esto forzará un refresh

def cargar_provincias():
    conn = obtener_conexion()
    query = "SELECT DISTINCT provincia FROM datos_uis"
    df = pd.read_sql(query, conn)
    conn.close()
    return sorted(df['provincia'].dropna().unique())


def cargar_datos_por_provincia(provincia):
    conn = obtener_conexion()

    query_datos_uis = """
        SELECT * 
        FROM datos_uis
        WHERE provincia = ?
    """
    datos_uis = pd.read_sql(query_datos_uis, conn, params=(provincia,))

    query_ofertas = """
        SELECT * 
        FROM ofertas_comercial
        WHERE provincia = ?
    """
    ofertas_df = pd.read_sql(query_ofertas, conn, params=(provincia,))

    query_comercial_rafa = """
        SELECT * 
        FROM comercial_rafa
        WHERE provincia = ?
    """
    comercial_rafa_df = pd.read_sql(query_comercial_rafa, conn, params=(provincia,))

    conn.close()
    return datos_uis, ofertas_df, comercial_rafa_df


def mapa_seccion():
    """Muestra un mapa interactivo con los datos de serviciabilidad y ofertas,
       con un filtro siempre visible por Apartment ID."""

    # 🔹 LEYENDA DE COLORES
    st.markdown("""
       🟢 **Serviciable** 
       🟠 **Oferta (Contrato: Sí)** 
       ⚫ **Oferta (No Interesado)** 
       🔵 **Sin Oferta** 
       🔴 **No Serviciable** 
       🟣 **Incidencia reportada** 
    """)

    # 🔍 FILTRO OPCIONAL SIEMPRE VISIBLE: Apartment ID
    apartment_search = st.text_input("🔍 Buscar por Apartment ID (opcional)")

    col1, col2, col3 = st.columns(3)

    # —— Si se busca por ID, cargamos todos sin filtrar y aislamos ese registro
    if apartment_search:
        datos_uis, ofertas_df, comercial_rafa_df = cargar_datos_uis()
        datos_filtrados = datos_uis[datos_uis["apartment_id"].astype(str) == apartment_search]
        ofertas_filtradas = ofertas_df[ofertas_df["apartment_id"].astype(str) == apartment_search]
        comercial_rafa_filtradas = comercial_rafa_df[comercial_rafa_df["apartment_id"].astype(str) == apartment_search]

        if datos_filtrados.empty:
            st.error(f"❌ No se encontró ningún Apartment ID **{apartment_search}**.")
            return

    # —— Si no, fluye tu lógica normal por provincia/municipio/población
    else:
        provincias = cargar_provincias()
        provincia_sel = col1.selectbox("Provincia", ["Selecciona una provincia"] + provincias)
        if provincia_sel == "Selecciona una provincia":
            st.warning("Selecciona una provincia para cargar los datos.")
            return

        with st.spinner("⏳ Cargando datos..."):
            datos_uis, ofertas_df, comercial_rafa_df = cargar_datos_por_provincia(provincia_sel)

        if datos_uis.empty:
            st.error("❌ No se encontraron datos para la provincia seleccionada.")
            return

        # 🔹 Filtros de Municipio
        municipios = sorted(datos_uis['municipio'].dropna().unique())
        municipio_sel = col2.selectbox("Municipio", ["Todas"] + municipios)
        datos_filtrados = datos_uis if municipio_sel == "Todas" else datos_uis[datos_uis["municipio"] == municipio_sel]
        ofertas_filtradas = ofertas_df if municipio_sel == "Todas" else ofertas_df[ofertas_df["municipio"] == municipio_sel]
        comercial_rafa_filtradas = comercial_rafa_df if municipio_sel == "Todas" else comercial_rafa_df[comercial_rafa_df["municipio"] == municipio_sel]

        # 🔹 Filtros de Población
        poblaciones = sorted(datos_filtrados['poblacion'].dropna().unique())
        poblacion_sel = col3.selectbox("Población", ["Todas"] + poblaciones)
        if poblacion_sel != "Todas":
            datos_filtrados = datos_filtrados[datos_filtrados["poblacion"] == poblacion_sel]
            ofertas_filtradas = ofertas_filtradas[ofertas_filtradas["poblacion"] == poblacion_sel]
            comercial_rafa_filtradas = comercial_rafa_filtradas[comercial_rafa_filtradas["poblacion"] == poblacion_sel]

    # 🔹 Filtramos datos sin coordenadas y convertimos tipos
    datos_filtrados = datos_filtrados.dropna(subset=['latitud', 'longitud'])
    datos_filtrados[['latitud', 'longitud']] = datos_filtrados[['latitud', 'longitud']].astype(float)
    if datos_filtrados.empty:
        st.warning("⚠️ No hay datos que cumplan los filtros seleccionados.")
        return

    # 🔹 Unificar la información comercial de ambas fuentes
    ofertas_combinadas = pd.concat([ofertas_filtradas, comercial_rafa_filtradas], ignore_index=True)
    serviciable_dict = ofertas_combinadas.set_index("apartment_id")["serviciable"].str.strip().str.lower().to_dict()
    contrato_dict    = ofertas_combinadas.set_index("apartment_id")["Contrato"].str.strip().str.lower().to_dict()
    incidencia_dict  = ofertas_combinadas.set_index("apartment_id")["incidencia"].str.strip().str.lower().to_dict()

    # 🔹 Calcular centro del mapa
    center_lat, center_lon = datos_filtrados[['latitud', 'longitud']].mean()

    limpiar_mapa()  # evita sobrecarga de mapas

    with st.spinner("⏳ Cargando mapa..."):
        m = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=12,
            max_zoom=21,
            tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
            attr="Google"
        )
        Geocoder().add_to(m)

        # Clustering
        if m.options['zoom'] >= 15:
            cluster_layer = m
        else:
            cluster_layer = MarkerCluster(maxClusterRadius=5, minClusterSize=3).add_to(m)

        # 1️⃣ Detectar duplicados
        coord_counts = {}
        for _, row in datos_filtrados.iterrows():
            coord = (row['latitud'], row['longitud'])
            coord_counts[coord] = coord_counts.get(coord, 0) + 1

        # 2️⃣ Dibujar marcadores con desplazamiento si hace falta
        for _, row in datos_filtrados.iterrows():
            apt_id = row['apartment_id']
            lat_val, lon_val = row['latitud'], row['longitud']
            popup_text = f"🏠 {apt_id} - 📍 {lat_val}, {lon_val}"

            # color según estado
            if incidencia_dict.get(apt_id, "") == "sí":
                marker_color = 'purple'
            elif serviciable_dict.get(apt_id, "") == "no":
                marker_color = 'red'
            elif str(row["serviciable"]).strip().lower() == "sí":
                marker_color = 'green'
            elif contrato_dict.get(apt_id, "") == "sí":
                marker_color = 'orange'
            elif contrato_dict.get(apt_id, "") == "no interesado":
                marker_color = 'gray'
            else:
                marker_color = 'blue'

            # aplicar offset si duplicados
            count = coord_counts[(row['latitud'], row['longitud'])]
            if count > 1:
                lat_val += count * 0.00003
                lon_val -= count * 0.00003
                coord_counts[(row['latitud'], row['longitud'])] -= 1

            folium.Marker(
                location=[lat_val, lon_val],
                popup=popup_text,
                icon=folium.Icon(color=marker_color, icon="map-marker"),
                tooltip=apt_id
            ).add_to(cluster_layer)

        # renderizar y captura de click
        map_data = st_folium(m, height=500, use_container_width=True)
        selected_apartment = map_data.get("last_object_clicked_tooltip")
        if selected_apartment:
            mostrar_info_apartamento(selected_apartment,
                                     datos_filtrados,
                                     ofertas_filtradas,
                                     comercial_rafa_df)



def mostrar_info_apartamento(apartment_id, datos_df, ofertas_df, comercial_rafa_df):
    """ Muestra la información del apartamento clickeado, junto con un campo para comentarios.
        Se actualiza el campo 'comentarios' en la tabla (ofertas_comercial o comercial_rafa) donde se encuentre el registro.
    """
    st.subheader(f"🏠 **Información del Apartament ID {apartment_id}**")

    # Obtener los datos de cada DataFrame usando el apartment_id
    datos_info = datos_df[datos_df["apartment_id"] == apartment_id]
    ofertas_info = ofertas_df[ofertas_df["apartment_id"] == apartment_id]
    comercial_rafa_info = comercial_rafa_df[comercial_rafa_df["apartment_id"] == apartment_id]

    # Layout con dos columnas para mostrar las tablas
    col1, col2 = st.columns(2)

    # Tabla de Datos Generales
    if not datos_info.empty:
        with col1:
            st.markdown("##### 🔹 **Datos Generales**")
            data_uis = {
                "Campo": ["ID Apartamento", "Provincia", "Municipio", "Población", "Calle/Vial", "Número", "Letra",
                          "Código Postal", "cto_id", "cto", "Estado del Sitio", "Estado del Apartamento",
                          "Proyecto de CTO", "Zona"],
                "Valor": [
                    datos_info.iloc[0]['apartment_id'],
                    datos_info.iloc[0]['provincia'],
                    datos_info.iloc[0]['municipio'],
                    datos_info.iloc[0]['poblacion'],
                    datos_info.iloc[0]['vial'],
                    datos_info.iloc[0]['numero'],
                    datos_info.iloc[0]['letra'],
                    datos_info.iloc[0]['cp'],
                    datos_info.iloc[0]['cto_id'],
                    datos_info.iloc[0]['cto'],
                    datos_info.iloc[0]['site_operational_state'],
                    datos_info.iloc[0]['apartment_operational_state'],
                    datos_info.iloc[0]['cto_con_proyecto'],
                    datos_info.iloc[0]['zona']
                ]
            }
            df_uis = pd.DataFrame(data_uis)
            st.dataframe(df_uis.style.set_table_styles([
                {'selector': 'thead th', 'props': [('background-color', '#f1f1f1'), ('font-weight', 'bold')]},
                {'selector': 'tbody td', 'props': [('padding', '10px')]},
            ]))
    else:
        with col1:
            st.warning("❌ **No se encontraron datos para el apartamento en `datos_uis`.**")

    # Tabla de Datos Comerciales (prioridad a ofertas_info, luego comercial_rafa_info)
    fuente = None
    tabla_objetivo = None  # Variable para determinar qué tabla actualizar.
    if not ofertas_info.empty:
        fuente = ofertas_info
        tabla_objetivo = "ofertas_comercial"  # o la variable/objeto que uses para actualizar esta tabla
    elif not comercial_rafa_info.empty:
        fuente = comercial_rafa_info
        tabla_objetivo = "comercial_rafa"
    else:
        with col2:
            st.warning("❌ **No se encontraron datos para el apartamento en `ofertas_comercial` ni en `comercial_rafa`.**")

    if fuente is not None:
        with col2:
            st.markdown("##### 🔹 **Datos Comerciales**")
            data_comercial = {
                "Campo": ["ID Apartamento", "Provincia", "Municipio", "Población", "Serviciable", "Motivo Serviciable",
                          "Incidencia", "Motivo de Incidencia", "Nombre Cliente", "Teléfono", "Dirección Alternativa",
                          "Observaciones", "Comercial", "Comentarios"],
                "Valor": [
                    fuente.iloc[0]['apartment_id'],
                    fuente.iloc[0]['provincia'],
                    fuente.iloc[0]['municipio'],
                    fuente.iloc[0]['poblacion'],
                    fuente.iloc[0]['serviciable'],
                    fuente.iloc[0].get('motivo_serviciable', 'No disponible'),
                    fuente.iloc[0].get('incidencia', 'No disponible'),
                    fuente.iloc[0].get('motivo_incidencia', 'No disponible'),
                    fuente.iloc[0].get('nombre_cliente', 'No disponible'),
                    fuente.iloc[0].get('telefono', 'No disponible'),
                    fuente.iloc[0].get('direccion_alternativa', 'No disponible'),
                    fuente.iloc[0].get('observaciones', 'No hay observaciones.'),
                    fuente.iloc[0].get('comercial', 'No disponible.'),
                    fuente.iloc[0].get('comentarios', 'No disponible.')
                ]
            }
            df_comercial = pd.DataFrame(data_comercial)
            st.dataframe(df_comercial.style.set_table_styles([
                {'selector': 'thead th', 'props': [('background-color', '#f1f1f1'), ('font-weight', 'bold')]},
                {'selector': 'tbody td', 'props': [('padding', '10px')]},
            ]))

        # Preparamos el comentario ya existente para el formulario
        # Si el campo es None o 'No disponible.' se muestra una cadena vacía para editar
        comentario_previo = fuente.iloc[0].get('comentarios') or ""
        if comentario_previo == "No disponible.":
            comentario_previo = ""

        # Campo para agregar o editar nuevos comentarios, utilizando el comentario previo como valor inicial
        nuevo_comentario = st.text_area(f"### 🔹 **Añadir/Editar Comentario u Observación de {apartment_id}**",
                                        value=comentario_previo,
                                        help="El comentario se guardará en la tabla correspondiente de la base de datos, asociado al Apartment ID elegido")
        if st.button("Guardar Comentario"):
            if not nuevo_comentario.strip():
                st.error("❌ El comentario no puede estar vacío.")
            else:
                # Actualizamos la base de datos
                resultado = guardar_comentario(apartment_id, nuevo_comentario, tabla_objetivo)
                if resultado:
                    st.success("✅ Comentario guardado exitosamente.")
                else:
                    st.error("❌ Hubo un error al guardar el comentario. Intenta nuevamente.")


def guardar_comentario(apartment_id, comentario, tabla):
    try:
        # Conexión a la base de datos (cambia la ruta o la conexión según corresponda)
        conn = obtener_conexion()
        cursor = conn.cursor()

        # Actualizar el comentario para el registro con el apartment_id dado
        query = f"UPDATE {tabla} SET comentarios = ? WHERE apartment_id = ?"
        cursor.execute(query, (comentario, apartment_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Error al actualizar la base de datos: {str(e)}")
        return False


def viabilidades_seccion():
    log_trazabilidad("Administrador", "Visualización de Viabilidades",
                     "El administrador visualizó la sección de viabilidades.")

    # Inicializamos el estado si no existe
    if "map_center" not in st.session_state:
        st.session_state["map_center"] = [43.463444, -3.790476]
    if "map_zoom" not in st.session_state:
        st.session_state["map_zoom"] = 12
    if "selected_ticket" not in st.session_state:
        st.session_state["selected_ticket"] = None

    # Cargar datos
    with st.spinner("⏳ Cargando los datos de viabilidades..."):
        try:
            conn = obtener_conexion()
            tables = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table';", conn)
            if 'viabilidades' not in tables['name'].values:
                st.error("❌ La tabla 'viabilidades' no se encuentra en la base de datos.")
                conn.close()
                return

            viabilidades_df = pd.read_sql("SELECT * FROM viabilidades", conn)
            conn.close()

            if viabilidades_df.empty:
                st.warning("⚠️ No hay viabilidades disponibles.")
                return

        except Exception as e:
            st.error(f"❌ Error al cargar los datos de la base de datos: {e}")
            return

    # Verificamos columnas necesarias
    for col in ['latitud', 'longitud', 'ticket']:
        if col not in viabilidades_df.columns:
            st.error(f"❌ Falta la columna '{col}'.")
            return

    # Agregamos columna de duplicados
    viabilidades_df['is_duplicate'] = viabilidades_df['apartment_id'].duplicated(keep=False)

    def highlight_duplicates(val):
        if isinstance(val, str) and val in viabilidades_df[viabilidades_df['is_duplicate']]['apartment_id'].values:
            return 'background-color: yellow'
        return ''

    # Interfaz: columnas para mapa y tabla
    col1, col2 = st.columns([3, 3])

    with col2:
        st.subheader("📋 Tabla de Viabilidades")

        # Reordenamos para que 'ticket' quede primero
        cols = viabilidades_df.columns.tolist()
        if 'ticket' in cols:
            cols.remove('ticket')
            cols = ['ticket'] + cols
        df_reordered = viabilidades_df[cols]

        # Mostramos tabla completa con estilo
        styled_df = df_reordered.style.applymap(highlight_duplicates, subset=['apartment_id'])
        st.dataframe(styled_df, use_container_width=True)

        # Selector de viabilidad por ticket (usando selectbox)
        selected_index = st.selectbox(
            "Selecciona una viabilidad por Ticket:",
            options=viabilidades_df["ticket"],
            index=viabilidades_df["ticket"].tolist().index(st.session_state["selected_ticket"])
            if st.session_state["selected_ticket"] in viabilidades_df["ticket"].tolist()
            else 0,
            key="viabilidad_selectbox"
        )

        # Filtramos el dataframe con el ticket seleccionado
        selected_viabilidad = viabilidades_df[viabilidades_df["ticket"] == selected_index].iloc[0]
        st.session_state["selected_ticket"] = selected_viabilidad["ticket"]
        st.session_state["map_center"] = [selected_viabilidad["latitud"], selected_viabilidad["longitud"]]
        st.session_state["map_zoom"] = 14

        if st.button("🔄 Refrescar Tabla"):
            st.rerun()

    with col1:
        st.subheader("🗺️ Mapa de Viabilidades")

        def draw_map(df, center, zoom):
            m = folium.Map(location=center, zoom_start=zoom,
                           tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
                           attr="Google")
            marker_cluster = MarkerCluster().add_to(m)

            for _, row in df.iterrows():
                popup = f"🏠 {row['ticket']} - 📍 {row['latitud']}, {row['longitud']}"

                # Obtener el valor de 'serviciable' y asegurarse de que sea una cadena.
                serviciable = row.get('serviciable')
                if serviciable is None:
                    serviciable = ""
                else:
                    serviciable = str(serviciable).strip()

                # Obtener y validar el valor de 'apartment_id'
                apartment_id = row.get('apartment_id')
                if apartment_id is None:
                    apartment_id = ""
                else:
                    apartment_id = str(apartment_id).strip()

                # Asignar el color en función de las condiciones:
                # Rojo: viabilidad categorizada como no serviciable.
                # Verde: viabilidad marcada como serviciable y que además tiene un apartment_id válido.
                # Azul: por defecto.
                if serviciable == "No":
                    marker_color = 'red'
                elif serviciable == "Sí" and apartment_id not in ["", "N/D"]:
                    marker_color = 'green'
                else:
                    marker_color = 'blue'

                folium.Marker(
                    location=[row['latitud'], row['longitud']],
                    popup=popup,
                    icon=folium.Icon(color=marker_color, icon='info-sign')
                ).add_to(marker_cluster)

            return m

        m_to_show = draw_map(viabilidades_df, st.session_state["map_center"], st.session_state["map_zoom"])
        st_folium(m_to_show, height=500, width=700, key="main_map")

    # Mostrar formulario debajo
    if st.session_state["selected_ticket"]:
        st.markdown("---")
        st.subheader(f"📝 Formulario para Ticket: {st.session_state['selected_ticket']}")
        mostrar_formulario(selected_viabilidad)


def mostrar_formulario(click_data):
    """Muestra el formulario para editar los datos de la viabilidad y guarda los cambios en la base de datos."""

    # Obtener valores de la tabla OLT
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("SELECT id_olt, nombre_olt FROM olt ORDER BY id_olt ASC")
    olts = cursor.fetchall()
    conn.close()

    # Preparar opciones del selectbox: se mostrará "id_olt - nombre_olt"
    opciones_olt = [f"{olt[0]} - {olt[1]}" for olt in olts]
    map_olt = {f"{olt[0]} - {olt[1]}": olt[0] for olt in olts}

    # Extraer los datos de click_data
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

    # Utilizar un formulario para evitar reejecuciones en cada cambio
    with st.form(key="form_viabilidad"):
        # Diseño en columnas del formulario
        col1, col2, col3 = st.columns([1, 1, 1])
        with col1:
            st.text_input("🎟️ Ticket", value=ticket, disabled=True, key="ticket_input")
        with col2:
            st.text_input("📍 Latitud", value=latitud, disabled=True, key="latitud_input")
        with col3:
            st.text_input("📍 Longitud", value=longitud, disabled=True, key="longitud_input")

        col4, col5, col6 = st.columns([1, 1, 1])
        with col4:
            st.text_input("📍 Provincia", value=provincia, disabled=True, key="provincia_input")
        with col5:
            st.text_input("🏙️ Municipio", value=municipio, disabled=True, key="municipio_input")
        with col6:
            st.text_input("👥 Población", value=poblacion, disabled=True, key="poblacion_input")

        col7, col8, col9, col10 = st.columns([2, 1, 1, 1])
        with col7:
            st.text_input("🚦 Vial", value=vial, disabled=True, key="vial_input")
        with col8:
            st.text_input("🔢 Número", value=numero, disabled=True, key="numero_input")
        with col9:
            st.text_input("🔠 Letra", value=letra, disabled=True, key="letra_input")
        with col10:
            st.text_input("📮 Código Postal", value=cp, disabled=True, key="cp_input")

        col11 = st.columns(1)[0]
        with col11:
            st.text_area("💬 Comentarios", value=comentario, disabled=True, key="comentario_input")

        col12, col13 = st.columns([1, 1])
        with col12:
            st.text_input("📅 Fecha Viabilidad", value=fecha_viabilidad, disabled=True, key="fecha_viabilidad_input")
        with col13:
            st.text_input("🔌 Cto Cercana", value=cto_cercana, disabled=True, key="cto_cercana_input")

        # Campo editable: comentarios comerciales con valor precargado (si existe)
        col14 = st.columns(1)[0]
        with col14:
            comentarios_comercial = st.text_area("📝 Comentarios Comerciales",
                                                 value=click_data.get("comentarios_comercial", ""),
                                                 key="comentarios_comercial_input")

        col15, col16, col17 = st.columns([1, 1, 1])
        with col15:
            # Campo editable: Apartment_id con valor precargado si existe
            apartment_id = st.text_input("🏠 Apartment_id",
                                         value=click_data.get("apartment_id", ""),
                                         key="apartment_id_input")
            # Para el campo OLT se determina la opción por defecto según el valor anterior
            default_olt = next((op for op in opciones_olt if op.startswith(f"{click_data.get('olt', '')} -")), opciones_olt[0])
            opcion_olt = st.selectbox("⚡ OLT", opciones_olt, index=opciones_olt.index(default_olt), key="olt_input")
            olt = map_olt[opcion_olt]  # Se guarda sólo el id_olt
        with col16:
            # Campos editables: Cto Admin y Municipio Admin con valores precargados
            cto_admin = st.text_input("⚙️ Cto Admin", value=click_data.get("cto_admin", ""), key="cto_admin_input")
            municipio_admin = st.text_input("🌍 Municipio Admin", value=click_data.get("municipio_admin", ""), key="municipio_admin_input")
        with col17:
            # Campos editables: ID Cto y seleccionable: ¿Es Serviciable?
            id_cto = st.text_input("🔧 ID Cto", value=click_data.get("id_cto", ""), key="id_cto_input")
            # Para el selectbox de serviciable se asigna por defecto según click_data
            serviciable_val = click_data.get("serviciable", "Sí")
            index_serviciable = 0 if serviciable_val == "Sí" else 1
            serviciable = st.selectbox("🔍 ¿Es Serviciable?", ["Sí", "No"], index=index_serviciable, key="serviciable_input")

        col19, col20 = st.columns([1, 1])
        with col19:
            # Campo editable: Coste con valor precargado
            coste = st.number_input("💰 Coste", value=float(click_data.get("coste", 0.0)), step=0.01, key="coste_input")
        with col20:
            # Campo editable: Comentarios Internos con valor precargado (si existe)
            comentarios_internos = st.text_area("📄 Comentarios Internos", value=click_data.get("comentarios_internos", ""), key="comentarios_internos_input")

        # Botón de envío del formulario
        submit = st.form_submit_button(f"💾 Guardar cambios para el Ticket {ticket}")

    # Procesar el formulario solo si se presiona el botón submit
    if submit:
        try:
            conn = obtener_conexion()
            cursor = conn.cursor()

            # 1️⃣ Actualizar viabilidad en la base de datos
            query = """
                UPDATE viabilidades
                SET apartment_id = ?, olt = ?, cto_admin = ?, id_cto = ?, municipio_admin = ?, serviciable = ?, 
                    coste = ?, comentarios_comercial = ?, comentarios_internos = ?
                WHERE ticket = ?
            """
            cursor.execute(query, (
                apartment_id, olt, cto_admin, id_cto, municipio_admin, serviciable,
                coste, comentarios_comercial, comentarios_internos, ticket
            ))

            # 2️⃣ Obtener el email del comercial responsable
            cursor.execute("""
                SELECT email 
                FROM usuarios
                WHERE username = (
                    SELECT usuario 
                    FROM viabilidades 
                    WHERE ticket = ?
                )
            """, (ticket,))
            email_comercial = cursor.fetchone()
            destinatarios = []

            if email_comercial:
                destinatarios.append(email_comercial[0])
            else:
                st.error("❌ No se encontró el correo del comercial correspondiente.")
                destinatarios.append("patricia@redytelcomputer.com")

            # 3️⃣ Obtener todos los emails de los comercial_jefe
            cursor.execute("""
                SELECT email
                FROM usuarios
                WHERE role = 'comercial_jefe'
            """)
            jefes = cursor.fetchall()
            for fila in jefes:
                destinatarios.append(fila[0])

            # 4️⃣ Montar descripción del correo
            descripcion_viabilidad = (
                f"📢 La viabilidad del ticket {ticket} ha sido completada.<br><br>"
                f"📌 Comentarios a comerciales: {comentarios_comercial}<br>"
                f"📍 Municipio: {municipio_admin}<br>"
                f"💰 Coste: {coste}€<br>"
                f"🔍 Es Serviciable: {serviciable}<br>"
                f"🏠 Apartment ID: {apartment_id}<br><br>"
                f"ℹ️ Por favor, revise los detalles de la viabilidad y asegúrese de que toda la información sea correcta. "
                f"Si tiene alguna pregunta o necesita realizar alguna modificación, no dude en ponerse en contacto con el equipo de administración."
            )

            # 5️⃣ Enviar correo a todos los destinatarios
            for destinatario in set(destinatarios):  # set() para evitar duplicados
                correo_viabilidad_administracion(destinatario, ticket, descripcion_viabilidad)

            # 6️⃣ Confirmaciones y cierre
            conn.commit()
            conn.close()

            st.success(f"✅ Los cambios para el Ticket {ticket} han sido guardados correctamente.")
            st.info(f"📧 Se ha enviado una notificación al comercial y a los jefes de equipo.")

        except Exception as e:
            st.error(f"❌ Error al guardar los cambios o enviar notificaciones: {e}")

def obtener_apartment_ids_existentes(cursor):
    cursor.execute("SELECT apartment_id FROM datos_uis")
    return {row[0] for row in cursor.fetchall()}

# Función principal de la app (Dashboard de administración)
def admin_dashboard():
    """Panel del administrador."""
    controller = CookieController(key="cookies")
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
            options=["Home", "Ver Datos", "Ofertas Comerciales", "Viabilidades", "Mapa UUIIs", "Cargar Nuevos Datos",
                     "Generador de informes", "Trazabilidad y logs", "Gestionar Usuarios",
                     "Control de versiones"],
            icons=["house", "graph-up", "bar-chart", "check-circle", "globe", "upload",
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

                # Establecer la expiración de las cookies en el pasado para forzar su eliminación
                controller.set(f'{cookie_name}_session_id', '', max_age=0, expires=datetime(1970, 1, 1))
                controller.set(f'{cookie_name}_username', '', max_age=0, expires=datetime(1970, 1, 1))
                controller.set(f'{cookie_name}_role', '', max_age=0, expires=datetime(1970, 1, 1))

                # Reiniciar el estado de sesión
                st.session_state["login_ok"] = False
                st.session_state["username"] = ""
                st.session_state["role"] = ""
                st.session_state["session_id"] = ""

                st.success("✅ Has cerrado sesión correctamente. Redirigiendo al login...")
                # Limpiar parámetros de la URL
                st.experimental_set_query_params()  # Limpiamos la URL (opcional, si hay parámetros en la URL)
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
                conn = obtener_conexion()
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
            "ℹ️ En esta sección puedes visualizar las ofertas registradas por los comerciales, filtrar los datos por etiquetas, "
            "columnas, buscar elementos concretos y descargar los datos en Excel o CSV."
        )

        if "df" in st.session_state:
            del st.session_state["df"]

        with st.spinner("⏳ Cargando ofertas comerciales..."):
            try:
                conn = obtener_conexion()
                # Consultar ambas tablas
                query_ofertas_comercial = "SELECT * FROM ofertas_comercial"
                query_comercial_rafa = "SELECT * FROM comercial_rafa"

                ofertas_comercial_data = pd.read_sql(query_ofertas_comercial, conn)
                comercial_rafa_data = pd.read_sql(query_comercial_rafa, conn)
                conn.close()

                if ofertas_comercial_data.empty and comercial_rafa_data.empty:
                    st.error("❌ No se encontraron ofertas realizadas por los comerciales.")
                    return

                # Filtrar comercial_rafa para mostrar registros con datos en 'serviciable'
                comercial_rafa_data_filtrada = comercial_rafa_data[comercial_rafa_data['serviciable'].notna()]

                # Unir ambas tablas en un solo DataFrame
                if not comercial_rafa_data_filtrada.empty:
                    combined_data = pd.concat([ofertas_comercial_data, comercial_rafa_data_filtrada], ignore_index=True)
                else:
                    combined_data = ofertas_comercial_data

            except Exception as e:
                st.error(f"❌ Error al cargar datos de la base de datos: {e}")
                return

        if combined_data.empty:
            st.warning("⚠️ No se encontraron ofertas comerciales finalizadas.")
            return

        # Eliminar columnas duplicadas si las hay
        if combined_data.columns.duplicated().any():
            st.warning("¡Se encontraron columnas duplicadas! Se eliminarán las duplicadas.")
            combined_data = combined_data.loc[:, ~combined_data.columns.duplicated()]

        # Guardar en sesión de Streamlit
        st.session_state["df"] = combined_data

        columnas = st.multiselect("🔎 Filtra las columnas a mostrar:", combined_data.columns.tolist(),
                                  default=combined_data.columns.tolist())

        st.dataframe(combined_data[columnas], use_container_width=True)

        seleccion_id = st.selectbox("🖼️ Selecciona un Apartment ID para ver su imagen:",
                                    combined_data["apartment_id"].unique())

        # Filtrar la oferta seleccionada
        oferta_seleccionada = combined_data[combined_data["apartment_id"] == seleccion_id]

        if not oferta_seleccionada.empty:
            imagen_url = oferta_seleccionada.iloc[0]["fichero_imagen"]

            if pd.notna(imagen_url) and imagen_url.strip() != "":
                st.image(imagen_url, caption=f"Imagen de la oferta {seleccion_id}", use_column_width=True)
            else:
                st.warning("❌ Esta oferta no tiene una imagen asociada.")

        st.subheader("📥 Descargar datos")
        download_format = st.radio("Selecciona el formato de descarga:", ["Excel", "CSV"], key="oferta_download")

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

        elif download_format == "CSV":
            csv = combined_data[columnas].to_csv(index=False).encode()
            with st.spinner("Preparando archivo CSV..."):
                st.download_button(
                    label="📥 Descargar CSV",
                    data=csv,
                    file_name="ofertas_comerciales.csv",
                    mime="text/csv"
                )

            # Ver los Apartment IDs disponibles
        st.markdown("### Eliminar Oferta Comercial")

        # Desplegable para seleccionar el Apartment ID de la oferta a eliminar
        apartment_ids = combined_data['apartment_id'].tolist()

        selected_apartment_id = st.selectbox(
            "Selecciona el Apartment ID de la oferta a eliminar:",
            ["-- Seleccione --"] + apartment_ids
        )

        # Verificar la selección
        st.write(f"Apartment ID seleccionado: {selected_apartment_id}")  # Verificación de la selección

        # Mostrar botón de eliminar solo si un Apartment ID ha sido seleccionado
        if selected_apartment_id != "-- Seleccione --":
            if st.button("Eliminar Oferta"):
                try:
                    # Conexión a la base de datos
                    conn = obtener_conexion()

                    # Ejecutar la eliminación en ambas tablas (ofertas_comercial y comercial_rafa)
                    query_delete_oferta = f"DELETE FROM ofertas_comercial WHERE apartment_id = '{selected_apartment_id}'"
                    query_delete_comercial = f"DELETE FROM comercial_rafa WHERE apartment_id = '{selected_apartment_id}'"

                    # Ejecutar las consultas
                    conn.execute(query_delete_oferta)
                    conn.execute(query_delete_comercial)

                    # Confirmar eliminación
                    conn.commit()
                    conn.close()

                    st.success(f"✅ La oferta con Apartment ID {selected_apartment_id} ha sido eliminada exitosamente.")

                except Exception as e:
                    st.error(f"❌ Error al eliminar la oferta: {e}")

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
        st.markdown("""**Leyenda:**
                     🔵 Viabilidad aún sin estudio
                     🟢 Viabilidad serviciable y con Apartment ID ya asociado
                     🔴 Viabilidad no serviciable
                    """)
        viabilidades_seccion()

        # Opción: Viabilidades (En construcción)
    elif opcion == "Mapa UUIIs":
        st.header("🌍 Mapa UUIIs")
        st.info(
            "ℹ️ En esta sección puedes ver todos los datos cruzados entre ams y las ofertas de los comerciales, así como su estado actual. Ten en cuenta que tienes dos tipos de filtros "
            "diferentes. Puedes buscar por Aparment ID y de forma independiente puedes buscar por Provincia, Municipio y Población. En el caso de haber utilizado el Apartment ID y querer usar "
            "luego la otra opción de filtro, no te olvides de borrar el contenido de Aparrment ID del campo correspondiente para que se reactiven el resto de filtros.")
        mapa_seccion()

    # Opción: Generar Informes
    elif opcion == "Generador de informes":
        st.header("📑 Generador de Informes")
        st.info("ℹ️ Aquí puedes generar informes basados en los datos disponibles.")
        log_trazabilidad(st.session_state["username"], "Generar Informe", "El admin accedió al generador de informes.")

        # Selección del periodo de tiempo en columnas
        col1, col2 = st.columns(2)
        with col1:
            fecha_inicio = st.date_input("Fecha de inicio")
        with col2:
            fecha_fin = st.date_input("Fecha de fin")
        if st.button("Generar Informe"):
            informe = generar_informe(str(fecha_inicio), str(fecha_fin))
            st.dataframe(informe)



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

    elif opcion == "Cargar Nuevos Datos":
        st.header("📤 Cargar Nuevos Datos")
        st.info(
            "ℹ️ Aquí puedes cargar un archivo Excel o CSV para reemplazar los datos existentes en la base de datos a una versión más moderna. "
            "¡ATENCIÓN! ¡Se eliminarán todos los datos actuales!"
        )
        log_trazabilidad(
            st.session_state["username"],
            "Cargar Nuevos Datos",
            "El admin accedió a la sección de carga de nuevos datos y se procederá a reemplazar el contenido de la tabla."
        )
        uploaded_file = st.file_uploader("Selecciona un archivo Excel o CSV", type=["xlsx", "csv"])
        if uploaded_file is not None:
            try:
                with st.spinner("⏳ Cargando archivo..."):
                    if uploaded_file.name.endswith(".xlsx"):
                        data = pd.read_excel(uploaded_file)
                    elif uploaded_file.name.endswith(".csv"):
                        data = pd.read_csv(uploaded_file)
                columnas_requeridas = [
                    "id_ams", "apartment_id", "address_id", "provincia", "municipio", "poblacion",
                    "vial", "numero", "parcela_catastral", "letra", "cp", "site_operational_state",
                    "apartment_operational_state", "cto_id", "olt", "cto", "LATITUD", "LONGITUD",
                    "cto_con_proyecto", "UNICO24", "COMERCIAL", "ZONA", "FECHA", "SERVICIABLE", "MOTIVO", "contrato_uis"
                ]
                columnas_faltantes = [col for col in columnas_requeridas if col not in data.columns]
                if columnas_faltantes:
                    st.error(
                        f"❌ El archivo no contiene las siguientes columnas requeridas: {', '.join(columnas_faltantes)}"
                    )
                else:
                    data_filtrada = data[columnas_requeridas].copy()
                    # Convertimos LATITUD y LONGITUD a float, reemplazando comas por puntos
                    data_filtrada["LATITUD"] = data_filtrada["LATITUD"].astype(str).str.replace(",", ".").astype(float)
                    data_filtrada["LONGITUD"] = data_filtrada["LONGITUD"].astype(str).str.replace(",", ".").astype(
                        float)
                    st.write(
                        "✅ Datos filtrados correctamente. Procediendo a reemplazar los datos en la base de datos...")
                    conn = obtener_conexion()
                    cursor = conn.cursor()
                    # Eliminamos todos los registros de la tabla y reiniciamos el ID autoincremental
                    cursor.execute("DELETE FROM datos_uis")
                    cursor.execute("DELETE FROM sqlite_sequence WHERE name='datos_uis'")
                    conn.commit()
                    total_registros = len(data_filtrada)
                    # Extraemos los valores de forma vectorizada
                    insert_values = data_filtrada.values.tolist()
                    # Barra de progreso y chunked insertion para mejorar el rendimiento
                    progress_bar = st.progress(0)
                    chunk_size = 500  # Puedes ajustar el tamaño del chunk según tu dataset
                    num_chunks = (total_registros + chunk_size - 1) // chunk_size
                    query = """
                        INSERT INTO datos_uis (
                            id_ams, apartment_id, address_id, provincia, municipio, poblacion, vial, numero, 
                            parcela_catastral, letra, cp, site_operational_state, apartment_operational_state, 
                            cto_id, olt, cto, LATITUD, LONGITUD, cto_con_proyecto, UNICO24, COMERCIAL, ZONA, FECHA, 
                            SERVICIABLE, MOTIVO, contrato_uis
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    for i in range(num_chunks):
                        chunk = insert_values[i * chunk_size: (i + 1) * chunk_size]
                        cursor.executemany(query, chunk)
                        conn.commit()
                        progress_bar.progress(min((i + 1) / num_chunks, 1.0))
                    conn.close()
                    progress_bar.progress(1.0)
                    st.success(f"🎉 Datos reemplazados exitosamente. Total registros cargados: {total_registros}")
                    progress_bar.empty()
                    log_trazabilidad(
                        st.session_state["username"],
                        "Cargar Nuevos Datos",
                        f"El admin reemplazó los datos existentes con {total_registros} nuevos registros."
                    )
            except Exception as e:
                st.error(f"❌ Error al cargar el archivo: {e}")
            except Exception as e:
                st.error(f"❌ Error al cargar el archivo: {e}")

    # Opción: Trazabilidad y logs
    elif opcion == "Trazabilidad y logs":
        st.header("📜 Trazabilidad y logs")
        st.info(
            "ℹ️ Aquí se pueden visualizar los logs y la trazabilidad de las acciones realizadas. Puedes utilizar las etiquetas rojas para filtrar la tabla y "
            "descargar los datos relevantes en formato excel y csv.")
        log_trazabilidad(st.session_state["username"], "Visualización de Trazabilidad",
                         "El admin visualizó la sección de trazabilidad y logs.")

        # Botón para vaciar la tabla
        if st.button("🗑️ Vaciar tabla y resetear IDs"):
            with st.spinner("Eliminando registros..."):
                try:
                    # Conectar a la base de datos
                    conn = obtener_conexion()
                    cursor = conn.cursor()

                    # Eliminar todos los registros de la tabla
                    cursor.execute("DELETE FROM trazabilidad")
                    # Resetear los IDs de la tabla
                    cursor.execute("VACUUM")  # Esto optimiza la base de datos y resetea los IDs autoincrementables
                    conn.commit()
                    conn.close()
                    st.success("✔️ Tabla vaciada y IDs reseteados con éxito.")
                except Exception as e:
                    st.error(f"❌ Error al vaciar la tabla: {e}")

        with st.spinner("Cargando trazabilidad..."):
            try:
                conn = obtener_conexion()
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


def generar_informe(fecha_inicio, fecha_fin):
    # Conectar a la base de datos y realizar cada consulta
    def ejecutar_consulta(query, params=None):
        # Abrir la conexión para cada consulta
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute(query, params if params else ())
        result = cursor.fetchone()
        conn.close()  # Cerrar la conexión inmediatamente después de ejecutar la consulta
        return result[0] if result else 0

    # 🔹 1️⃣ Total de asignaciones en el periodo T
    query_total = """
        SELECT COUNT(DISTINCT apartment_id) 
        FROM datos_uis
        WHERE STRFTIME('%Y-%m-%d', fecha) BETWEEN ? AND ?
    """
    total_asignaciones = ejecutar_consulta(query_total, (fecha_inicio, fecha_fin))

    # 🔹 2️⃣ Cantidad de visitas (apartment_id presente en ambas tablas, sin filtrar por fecha)
    query_visitados = """
        SELECT COUNT(DISTINCT d.apartment_id)
        FROM datos_uis d
        INNER JOIN ofertas_comercial o 
            ON d.apartment_id = o.apartment_id
    """
    total_visitados = ejecutar_consulta(query_visitados)

    # 🔹 3️⃣ Cantidad de ventas (visitados donde contrato = 'Sí')
    query_ventas = """
        SELECT COUNT(DISTINCT d.apartment_id)
        FROM datos_uis d
        INNER JOIN ofertas_comercial o 
            ON d.apartment_id = o.apartment_id
        WHERE LOWER(o.contrato) = 'sí'
    """
    total_ventas = ejecutar_consulta(query_ventas)

    # 🔹 4️⃣ Cantidad de incidencias (donde incidencia = 'Sí')
    query_incidencias = """
        SELECT COUNT(DISTINCT d.apartment_id)
        FROM datos_uis d
        INNER JOIN ofertas_comercial o 
            ON d.apartment_id = o.apartment_id
        WHERE LOWER(o.incidencia) = 'sí'
    """
    total_incidencias = ejecutar_consulta(query_incidencias)

    # 🔹 5️⃣ Cantidad de viviendas no serviciables (donde serviciable = 'No')
    query_no_serviciables = """
        SELECT COUNT(DISTINCT apartment_id)
        FROM ofertas_comercial
        WHERE LOWER(serviciable) = 'no'
    """
    total_no_serviciables = ejecutar_consulta(query_no_serviciables)

    # 🔹 6️⃣ Cálculo de porcentajes
    porcentaje_ventas = (total_ventas / total_visitados * 100) if total_visitados > 0 else 0
    porcentaje_visitas = (total_visitados / total_asignaciones * 100) if total_asignaciones > 0 else 0
    porcentaje_incidencias = (total_incidencias / total_visitados * 100) if total_visitados > 0 else 0
    porcentaje_no_serviciables = (total_no_serviciables / total_visitados * 100) if total_visitados > 0 else 0

    # 🔹 7️⃣ Crear DataFrame con los resultados
    informe = pd.DataFrame({
        'Total Asignaciones Directas': [total_asignaciones],
        'Visitados': [total_visitados],
        'Ventas': [total_ventas],
        'Incidencias': [total_incidencias],
        'Viviendas No Serviciables': [total_no_serviciables],
        '% Ventas': [porcentaje_ventas],
        '% Visitas': [porcentaje_visitas],
        '% Incidencias': [porcentaje_incidencias],
        '% Viviendas No Serviciables': [porcentaje_no_serviciables]
    })
    st.write("----------------------")
    # Crear tres columnas para los gráficos
    col1, col2, col3 = st.columns(3)

    with col1:
        labels = ['Ventas', 'Visitas']
        values = [porcentaje_ventas, porcentaje_visitas]
        fig = go.Figure(data=[go.Pie(labels=labels, values=values, hole=0.3,
                                     textinfo='percent+label',
                                     marker=dict(colors=['#66b3ff', '#ff9999']))])
        fig.update_layout(title="Distribución de Visitas y Ventas", title_x=0, plot_bgcolor='white', showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        labels_incidencias = ['Incidencias', 'Visitas']
        values_incidencias = [porcentaje_incidencias, porcentaje_visitas]
        fig_incidencias = go.Figure(data=[go.Pie(labels=labels_incidencias, values=values_incidencias, hole=0.3,
                                                 textinfo='percent+label',
                                                 marker=dict(colors=['#ff6666', '#99cc99']))])
        fig_incidencias.update_layout(title="Distribución de Visitas e Incidencias", title_x=0, plot_bgcolor='white',
                                      showlegend=False)
        st.plotly_chart(fig_incidencias, use_container_width=True)

    with col3:
        labels_serviciables = ['No Serviciables', 'Serviciables']
        values_serviciables = [porcentaje_no_serviciables, 100 - porcentaje_no_serviciables]
        fig_serviciables = go.Figure(data=[go.Bar(
            x=labels_serviciables,
            y=values_serviciables,
            text=values_serviciables,
            textposition='outside',
            marker=dict(color=['#ff6666', '#99cc99'])
        )])
        fig_serviciables.update_layout(
            title="Distribución Viviendas visitadas Serviciables/No Serviciables",
            title_x=0,
            plot_bgcolor='rgba(0, 0, 0, 0)',  # Fondo transparente
            showlegend=False,
            xaxis_title="Estado de Viviendas",
            yaxis_title="Porcentaje",
            xaxis=dict(tickangle=0),
            height=450
        )
        st.plotly_chart(fig_serviciables, use_container_width=True)

    # Resumen de los resultados
    resumen = f"""
    <div style="text-align: justify;">
    Durante el periodo analizado, que abarca desde el <strong>{fecha_inicio}</strong> hasta el <strong>{fecha_fin}</strong>, se han registrado un total de <strong>{total_asignaciones}</strong> asignaciones realizadas, lo que indica la cantidad de propiedades consideradas para asignación en este intervalo. De estas asignaciones, <strong>{total_visitados}</strong> propiedades fueron visitadas, lo que representa un <strong>{porcentaje_visitas:.2f}%</strong> del total de asignaciones. Esto refleja el grado de éxito en la conversión de asignaciones a visitas, lo que es un indicador de la efectividad de la asignación de propiedades.
    De las propiedades visitadas, <strong>{total_ventas}</strong> viviendas fueron finalmente vendidas, lo que constituye el <strong>{porcentaje_ventas:.2f}%</strong> de las propiedades visitadas. Este porcentaje es crucial, ya que nos muestra cuán efectivas han sido las visitas en convertir en ventas las oportunidades de negocio. A su vez, se han registrado <strong>{total_incidencias}</strong> incidencias durante las visitas, lo que equivale a un <strong>{porcentaje_incidencias:.2f}%</strong> de las asignaciones. Las incidencias indican problemas o dificultades encontradas en las propiedades, lo que podría afectar la decisión de los posibles compradores.
    Por otro lado, en cuanto a la calidad del inventario, <strong>{total_no_serviciables}</strong> propiedades fueron catalogadas como no serviciables, lo que representa un <strong>{porcentaje_no_serviciables:.2f}%</strong> del total de asignaciones.
    </div>
    <br>
    """
    st.markdown(resumen, unsafe_allow_html=True)

    # ─────────────────────────────────────────────
    # 🔹 Informe de Trazabilidad (Asignación y Desasignación)
    # ─────────────────────────────────────────────
    st.write("----------------------")
    query_asignaciones_trazabilidad = """
        SELECT COUNT(*) 
        FROM trazabilidad
        WHERE LOWER(accion) LIKE '%asignación%' 
          AND STRFTIME('%Y-%m-%d', fecha) BETWEEN ? AND ?
    """
    query_desasignaciones = """
        SELECT COUNT(*) 
        FROM trazabilidad
        WHERE LOWER(accion) LIKE '%desasignación%' 
          AND STRFTIME('%Y-%m-%d', fecha) BETWEEN ? AND ?
    """
    total_asignaciones_trazabilidad = ejecutar_consulta(query_asignaciones_trazabilidad, (fecha_inicio, fecha_fin))
    total_desasignaciones = ejecutar_consulta(query_desasignaciones, (fecha_inicio, fecha_fin))
    total_movimientos = total_asignaciones_trazabilidad + total_desasignaciones

    porcentaje_asignaciones = (
                total_asignaciones_trazabilidad / total_movimientos * 100) if total_movimientos > 0 else 0
    porcentaje_desasignaciones = (total_desasignaciones / total_movimientos * 100) if total_movimientos > 0 else 0

    informe_trazabilidad = pd.DataFrame({
        'Asignaciones Gestor': [total_asignaciones_trazabilidad],
        'Desasignaciones Gestor': [total_desasignaciones],
        'Total Movimientos': [total_movimientos],
        '% Asignaciones': [porcentaje_asignaciones],
        '% Desasignaciones': [porcentaje_desasignaciones]
    })

    col_t1, col_t2 = st.columns(2)
    with col_t1:
        fig_mov = go.Figure()

        fig_mov.add_trace(go.Bar(
            x=[porcentaje_asignaciones],
            y=['Asignaciones'],
            orientation='h',
            name='Asignaciones',
            marker=dict(color='#3366cc'),
            text=f"{porcentaje_asignaciones:.1f}%",
            textposition="auto",
            width=0.5  # 👈 Más fino (por defecto es 0.8)
        ))

        fig_mov.add_trace(go.Bar(
            x=[porcentaje_desasignaciones],
            y=['Desasignaciones'],
            orientation='h',
            name='Desasignaciones',
            marker=dict(color='#ff9933'),
            text=f"{porcentaje_desasignaciones:.1f}%",
            textposition="auto",
            width=0.5  # 👈 Más fino
        ))

        fig_mov.update_layout(
            title="Distribución Asignaciones/Desasignaciones realizadas por el gestor",
            xaxis_title="Porcentaje (%)",
            yaxis_title="Tipo de Movimiento",
            barmode='stack',  # Esto apila las barras
            showlegend=False,
            title_x=0,
            bargap=0.05,  # Menor espacio entre las barras
            xaxis=dict(
                range=[0, 100],  # Para que la escala vaya del 0 al 100
            ),
            yaxis=dict(
                tickmode='array',
                tickvals=['Asignaciones', 'Desasignaciones'],
                ticktext=['Asignaciones', 'Desasignaciones']
            ),
            width=400,  # Ancho del gráfico
            height=300  # Ajusta la altura aquí (por ejemplo, 300px)
        )

        st.plotly_chart(fig_mov, use_container_width=True)

    with col_t2:
        st.markdown("<div style='margin-top:40px;'>", unsafe_allow_html=True)
        st.dataframe(informe_trazabilidad)
        resumen_trazabilidad = f"""
            <div style="text-align: justify;">
            En el periodo analizado, del <strong>{fecha_inicio}</strong> al <strong>{fecha_fin}</strong>, se han registrado un total de <strong>{total_movimientos}</strong> movimientos en la trazabilidad realizados por el gestor comercial. De ellos, <strong>{total_asignaciones_trazabilidad}</strong> corresponden a asignaciones (<strong>{porcentaje_asignaciones:.2f}%</strong>) y <strong>{total_desasignaciones}</strong> a desasignaciones (<strong>{porcentaje_desasignaciones:.2f}%</strong>). 
            </div>
            <br>
            """
        st.markdown(resumen_trazabilidad, unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
    st.write("----------------------")
    return informe

# Función para leer y mostrar el control de versiones
def mostrar_control_versiones():
    try:
        # Leer el archivo version.txt
        with open("modules/version.txt", "r", encoding="utf-8") as file:
            versiones = file.readlines()

        # Mostrar el encabezado de la sección
        st.subheader("🔄 Control de versiones")
        st.info("ℹ️ Aquí puedes ver el historial de cambios y versiones de la aplicación. Cada entrada incluye el número de versión y una breve descripción de lo que se ha actualizado o modificado.")

        # Mostrar las versiones en formato de lista con número y descripción en la misma línea
        for version in versiones:
            version_info = version.strip().split(" - ")
            if len(version_info) == 2:
                st.markdown(
                    f"<div style='background-color: #f7f7f7; padding: 10px; border-radius: 8px; margin-bottom: 10px;'>"
                    f"<p style='font-size: 14px; color: #666; margin: 0;'><strong style='color: #4CAF50; font-size: 16px;'>{version_info[0]}</strong> - {version_info[1]}</p>"
                    f"</div>", unsafe_allow_html=True
                )
            else:
                st.markdown(
                    f"<div style='background-color: #f7f7f7; padding: 10px; border-radius: 8px; margin-bottom: 10px;'>"
                    f"<p style='font-size: 14px; color: #666; margin: 0;'><strong style='color: #4CAF50; font-size: 16px;'>{version_info[0]}</strong> - Sin descripción disponible.</p>"
                    f"</div>", unsafe_allow_html=True
                )

        # Nota técnica adicional para el admin
        st.markdown("<br><i style='font-size: 14px; color: #888;'>Nota técnica: Esta sección muestra el historial completo de cambios aplicados al sistema. Asegúrese de revisar las versiones anteriores para comprender las mejoras y correcciones implementadas.</i>", unsafe_allow_html=True)

    except FileNotFoundError:
        st.error("El archivo `version.txt` no se encuentra en el sistema.")
    except Exception as e:
        st.error(f"Ha ocurrido un error al cargar el control de versiones: {e}")

# Función para crear el gráfico interactivo de Serviciabilidad
def create_serviciable_graph():
    # Conectar y obtener datos de la primera tabla
    conn = obtener_conexion()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM datos_uis WHERE serviciable = 'Sí';")
    datos_uis_count = cursor.fetchone()[0]  # Obtener el valor numérico
    conn.close()

    # Conectar y obtener datos de la segunda tabla
    conn = obtener_conexion()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM ofertas_comercial WHERE serviciable = 'No';")
    ofertas_comercial_count = cursor.fetchone()[0]  # Obtener el valor numérico
    conn.close()

    # Crear DataFrame manualmente
    data = [
        {"serviciable": "Sí", "count": datos_uis_count},
        {"serviciable": "No", "count": ofertas_comercial_count}
    ]
    df = pd.DataFrame(data)

    # Crear gráfico de barras con Plotly
    fig = px.bar(df, x="serviciable", y="count", title="Distribución de Serviciabilidad",
                 labels={"serviciable": "Serviciable", "count": "Cantidad"},
                 color="serviciable", color_discrete_sequence=["green", "red"])
    fig.update_layout(barmode='group', height=400)

    return fig

# Función para crear el gráfico interactivo de Incidencias por Provincia
def create_incidencias_graph(cursor):
    cursor.execute("""
        SELECT provincia, COUNT(*) AS total_incidencias
        FROM ofertas_comercial
        WHERE incidencia = 'Sí'
        GROUP BY provincia;
    """)
    data = cursor.fetchall()
    df = pd.DataFrame(data, columns=["provincia", "count"])

    # Crear gráfico interactivo de barras con Plotly
    fig = px.bar(df, x="provincia", y="count", title="Incidencias por Provincia",
                 labels={"provincia": "Provincia", "count": "Cantidad"},
                 color="provincia", color_discrete_sequence=px.colors.qualitative.Pastel)
    fig.update_layout(barmode='group', height=400)
    fig.update_xaxes(tickangle=45)  # Rotar las etiquetas de los ejes X
    return fig

# Gráfico Distribución de Tipos de Vivienda
def create_tipo_vivienda_distribution_graph():
    # Conectar y obtener datos de la tabla ofertas_comercial
    conn = obtener_conexion()
    cursor = conn.cursor()

    cursor.execute("SELECT Tipo_Vivienda, COUNT(*) FROM ofertas_comercial GROUP BY Tipo_Vivienda;")
    ofertas_comercial_data = cursor.fetchall()  # Obtener todos los resultados
    conn.close()

    # Conectar y obtener datos de la tabla comercial_rafa
    conn = obtener_conexion()
    cursor = conn.cursor()

    cursor.execute("SELECT Tipo_Vivienda, COUNT(*) FROM comercial_rafa GROUP BY Tipo_Vivienda;")
    comercial_rafa_data = cursor.fetchall()  # Obtener todos los resultados
    conn.close()

    # Convertir los datos de ambas tablas en DataFrames
    df_ofertas_comercial = pd.DataFrame(ofertas_comercial_data, columns=["Tipo_Vivienda", "Count_ofertas_comercial"])
    df_comercial_rafa = pd.DataFrame(comercial_rafa_data, columns=["Tipo_Vivienda", "Count_comercial_rafa"])

    # Reemplazar los valores nulos o vacíos con "Asignado - No visitado" en la tabla comercial_rafa
    # Usamos `fillna` para poner 'Asignado - No visitado' en los tipos de vivienda que no tengan datos en la tabla comercial_rafa
    df_comercial_rafa['Tipo_Vivienda'] = df_comercial_rafa['Tipo_Vivienda'].fillna('Asignado - No visitado')

    # Fusionar los DataFrames por la columna 'Tipo_Vivienda'
    df = pd.merge(df_ofertas_comercial, df_comercial_rafa, on="Tipo_Vivienda", how="outer").fillna(0)

    # Si hay valores en 'Count_comercial_rafa' como 0, los cambiamos a 'Asignado - No visitado'
    df['Tipo_Vivienda'] = df['Tipo_Vivienda'].apply(
        lambda x: 'Asignado - No visitado' if x == 0 else x
    )

    # Crear gráfico de barras con Plotly
    fig = px.bar(df, x="Tipo_Vivienda", y=["Count_ofertas_comercial", "Count_comercial_rafa"],
                 title="Distribución de Tipo de Vivienda",
                 labels={"Tipo_Vivienda": "Tipo de Vivienda", "value": "Cantidad"},
                 color="Tipo_Vivienda", barmode="group", height=400)

    fig.update_layout(barmode='group', height=400)

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
    fig.update_layout(height=400)
    fig.update_xaxes(tickangle=45)  # Rotar etiquetas de ejes X
    return fig

# Función principal de la página
def home_page():
    st.title("Resumen de datos relevantes")

    # Obtener la conexión y el cursor
    conn = obtener_conexion()
    cursor = conn.cursor()

    try:
        # Organizar los gráficos en columnas
        col1, col2 = st.columns(2)

        # Gráfico de Serviciabilidad
        with col1:
            st.plotly_chart(create_serviciable_graph())

        # Gráfico de Incidencias por Provincia
        with col2:
            st.plotly_chart(create_incidencias_graph(cursor))

        # Gráfico de Distribución de Tipos de Vivienda
        with col1:
            st.plotly_chart(create_tipo_vivienda_distribution_graph())

        # Gráfico de Viabilidades por Municipio
        with col2:
            st.plotly_chart(create_viabilities_by_municipio_graph(cursor))

    except Exception as e:
        st.error(f"Hubo un error al cargar los gráficos: {e}")
    finally:
        conn.close()  # No olvides cerrar la conexión al final

if __name__ == "__main__":
    admin_dashboard()
