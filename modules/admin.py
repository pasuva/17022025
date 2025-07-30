import zipfile, folium, sqlite3, datetime, bcrypt, os, sqlitecloud, io
import pandas as pd
import plotly.express as px
import streamlit as st
from modules.notificaciones import correo_viabilidad_administracion, correo_usuario, correo_nuevas_zonas_comercial, correo_envio_presupuesto_manual, correo_nueva_version
from datetime import datetime as dt  # Para evitar conflicto con datetime
from streamlit_option_menu import option_menu
from datetime import datetime
from streamlit_cookies_controller import CookieController  # Se importa localmente
from folium.plugins import MarkerCluster, Geocoder
from streamlit_folium import st_folium
import plotly.graph_objects as go
from rapidfuzz import fuzz
from st_aggrid import AgGrid, GridOptionsBuilder, DataReturnMode, GridUpdateMode
from io import BytesIO

from branca.element import Template, MacroElement

import warnings
warnings.filterwarnings("ignore", category=UserWarning)

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
    """Carga y cachea los datos de las tablas 'datos_uis', 'comercial_rafa'."""
    conn = obtener_conexion()

    # Consulta de datos_uis
    query_datos_uis = """
        SELECT apartment_id, latitud, longitud, provincia, municipio, poblacion, cto_con_proyecto, serviciable,
               vial, numero, letra, cp, cto_id, cto, site_operational_state, apartment_operational_state, zona
        FROM datos_uis
    """
    datos_uis = pd.read_sql(query_datos_uis, conn)

    # Consulta de comercial_rafa
    query_rafa = """
        SELECT apartment_id, serviciable, Contrato, provincia, municipio, poblacion,
               motivo_serviciable, incidencia, motivo_incidencia, nombre_cliente,
               telefono, direccion_alternativa, observaciones, comercial, comentarios
        FROM comercial_rafa
    """
    comercial_rafa_df = pd.read_sql(query_rafa, conn)

    conn.close()
    #return datos_uis, ofertas_df, comercial_rafa_df
    return datos_uis, comercial_rafa_df

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

    query_comercial_rafa = """
        SELECT * 
        FROM comercial_rafa
        WHERE provincia = ?
    """
    comercial_rafa_df = pd.read_sql(query_comercial_rafa, conn, params=(provincia,))

    conn.close()
    return datos_uis, comercial_rafa_df


def mapa_seccion():
    """Muestra un mapa interactivo con los datos de serviciabilidad y ofertas,
       con un filtro siempre visible por Apartment ID."""

    # 🔍 FILTRO OPCIONAL SIEMPRE VISIBLE: Apartment ID
    apartment_search = st.text_input("🔍 Buscar por Apartment ID (opcional)")

    col1, col2, col3 = st.columns(3)

    # —— Si se busca por ID, cargamos todos sin filtrar y aislamos ese registro
    if apartment_search:
        datos_uis, comercial_rafa_df = cargar_datos_uis()
        datos_filtrados = datos_uis[datos_uis["apartment_id"].astype(str) == apartment_search]
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
            datos_uis, comercial_rafa_df = cargar_datos_por_provincia(provincia_sel)

        if datos_uis.empty:
            st.error("❌ No se encontraron datos para la provincia seleccionada.")
            return

        # 🔹 Filtros de Municipio
        municipios = sorted(datos_uis['municipio'].dropna().unique())
        municipio_sel = col2.selectbox("Municipio", ["Todas"] + municipios)
        datos_filtrados = datos_uis if municipio_sel == "Todas" else datos_uis[datos_uis["municipio"] == municipio_sel]
        comercial_rafa_filtradas = comercial_rafa_df if municipio_sel == "Todas" else comercial_rafa_df[comercial_rafa_df["municipio"] == municipio_sel]

        # 🔹 Filtros de Población
        poblaciones = sorted(datos_filtrados['poblacion'].dropna().unique())
        poblacion_sel = col3.selectbox("Población", ["Todas"] + poblaciones)
        if poblacion_sel != "Todas":
            datos_filtrados = datos_filtrados[datos_filtrados["poblacion"] == poblacion_sel]
            comercial_rafa_filtradas = comercial_rafa_filtradas[comercial_rafa_filtradas["poblacion"] == poblacion_sel]

    # 🔹 Filtramos datos sin coordenadas y convertimos tipos
    datos_filtrados = datos_filtrados.dropna(subset=['latitud', 'longitud'])
    datos_filtrados[['latitud', 'longitud']] = datos_filtrados[['latitud', 'longitud']].astype(float)
    if datos_filtrados.empty:
        st.warning("⚠️ No hay datos que cumplan los filtros seleccionados.")
        return

    # 🔹 Unificar la información comercial de ambas fuentes
    ofertas_combinadas = pd.concat([comercial_rafa_filtradas], ignore_index=True)
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

            # Asegura que ningún valor sea None antes de aplicar strip y lower
            serv_uis = (str(row.get("serviciable") or "")).strip().lower()
            serv_oferta = (serviciable_dict.get(apt_id) or "").strip().lower()
            contrato = (contrato_dict.get(apt_id) or "").strip().lower()
            incidencia = (incidencia_dict.get(apt_id) or "").strip().lower()

            if incidencia == "sí":
                marker_color = 'purple'
            elif serv_oferta == "no":
                marker_color = 'red'
            elif serv_uis == "si":
                marker_color = 'green'
            elif contrato == "sí" and serv_uis != "si":
                marker_color = 'orange'
            elif contrato == "no interesado" and serv_uis != "si":
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
        legend = """
                    {% macro html() %}
                    <div style="
                        position: fixed; 
                        bottom: 20px; left: 0px; width: 190px; 
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
                    </div>
                    {% endmacro %}
                    """

        macro = MacroElement()
        macro._template = Template(legend)
        m.get_root().add_child(macro)
        map_data = st_folium(m, height=500, use_container_width=True)
        selected_apartment = map_data.get("last_object_clicked_tooltip")
        if selected_apartment:
            mostrar_info_apartamento(selected_apartment,
                                     datos_filtrados,
                                     comercial_rafa_df)

def mostrar_info_apartamento(apartment_id, datos_df, comercial_rafa_df):
    """ Muestra la información del apartamento clicado, junto con un campo para comentarios.
        Se actualiza el campo 'comentarios' en la tabla (comercial_rafa) donde se encuentre el registro.
    """
    st.subheader(f"🏠 **Información del Apartament ID {apartment_id}**")

    # Obtener los datos de cada DataFrame usando el apartment_id
    datos_info = datos_df[datos_df["apartment_id"] == apartment_id]
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
            st.dataframe(df_uis.style.set_table_styles([{'selector': 'thead th', 'props': [('background-color', '#f1f1f1'), ('font-weight', 'bold')]},{'selector': 'tbody td', 'props': [('padding', '10px')]},]))
    else:
        with col1:
            st.warning("❌ **No se encontraron datos para el apartamento en `datos_uis`.**")

    # Tabla de Datos Comerciales (prioridad a ofertas_info, luego comercial_rafa_info)
    fuente = None
    tabla_objetivo = None  # Variable para determinar qué tabla actualizar.
    if not comercial_rafa_info.empty:
        fuente = comercial_rafa_info
        tabla_objetivo = "comercial_rafa"
    else:
        with col2:
            st.warning("❌ **No se encontraron datos para el apartamento en `comercial_rafa`.**")

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
            st.dataframe(df_comercial.style.set_table_styles([{'selector': 'thead th', 'props': [('background-color', '#f1f1f1'), ('font-weight', 'bold')]},{'selector': 'tbody td', 'props': [('padding', '10px')]},]))

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
    # ✅ Agregamos columna que indica si tiene presupuesto asociado
    try:
        conn = obtener_conexion()
        presupuestos_df = pd.read_sql("SELECT DISTINCT ticket FROM presupuestos_viabilidades", conn)
        conn.close()

        viabilidades_df['tiene_presupuesto'] = viabilidades_df['ticket'].isin(presupuestos_df['ticket'])

    except Exception as e:
        #st.warning(f"No se pudo verificar si hay presupuestos: {e}")
        viabilidades_df['tiene_presupuesto'] = False

    def highlight_duplicates(val):
        if isinstance(val, str) and val in viabilidades_df[viabilidades_df['is_duplicate']]['apartment_id'].values:
            return 'background-color: yellow'
        return ''

    # Interfaz: columnas para mapa y tabla
    col1, col2 = st.columns([3, 3])

    with col2:

        # Reordenamos para que 'ticket' quede primero
        cols = viabilidades_df.columns.tolist()
        if 'ticket' in cols:
            cols.remove('ticket')
            cols = ['ticket'] + cols
        df_reordered = viabilidades_df[cols]

        # Preparamos la configuración con filtros y anchos
        gb = GridOptionsBuilder.from_dataframe(df_reordered)
        gb.configure_default_column(
            filter=True,
            floatingFilter=True,
            sortable=True,
            resizable=True,
            minWidth=100,  # ancho mínimo
            flex=1  # reparte espacio extra
        )
        # (Opcional) Para resaltar duplicados en apartment_id sin pandas styling:
        dup_ids = viabilidades_df.loc[viabilidades_df['is_duplicate'], 'apartment_id'].unique().tolist()
        gb.configure_column(
            'apartment_id',
            cellStyle={
                'function': f"if (value && {dup_ids}.includes(value)) return {{'backgroundColor':'yellow'}}"
            }
        )
        gridOptions = gb.build()

        AgGrid(
            df_reordered,
            gridOptions=gridOptions,
            enable_enterprise_modules=False,
            update_mode=GridUpdateMode.NO_UPDATE,
            data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
            fit_columns_on_grid_load=False,
            height=400,
            theme='alpine-dark'
        )

        if st.session_state.get("selected_ticket"):
            selected_viabilidad = \
            viabilidades_df[viabilidades_df["ticket"] == st.session_state["selected_ticket"]].iloc[0]
        # Orden y renombrado de columnas
        orden_columnas_excel = [
            "ticket", "usuario", "nuevapromocion", "resultado", "justificacion",
            "coste", "zona_estudio", "contratos", "latitud", "longitud",
            "provincia", "municipio", "poblacion", "vial", "numero", "letra",
            "cp", "olt", "cto_admin", "id_cto", "fecha_viabilidad",
            "apartment_id", "nombre_cliente", "telefono", "comentarios_internos"
        ]

        nombres_excel = {
            "usuario": "SOLICITANTE",
            "nuevapromocion": "Nueva Promoción",
            "zona_estudio": "UUII",
            "coste": "PRESUPUESTO",
            "nombre_cliente": "nombre cliente",
            "comentarios_internos": "comentarios internos",
            "fecha_viabilidad": "fecha viabilidad",
            "apartment_id": "apartment id"
        }

        # Limpiar y preparar DataFrame
        df_export = viabilidades_df.copy()

        # Duplicar filas por múltiples apartment_id
        def expand_apartments(df):
            rows = []
            for _, row in df.iterrows():
                ids = str(row.get("apartment_id", "")).split(",")
                for apt in ids:
                    new_row = row.copy()
                    new_row["apartment_id"] = apt.strip()
                    rows.append(new_row)
            return pd.DataFrame(rows)

        df_export = expand_apartments(df_export)

        # Filtrar columnas existentes y reordenar
        columnas_presentes = [col for col in orden_columnas_excel if col in df_export.columns]
        df_export = df_export[columnas_presentes]

        # Renombrar columnas para Excel
        df_export = df_export.rename(columns=nombres_excel)

        # Convertir a Excel en memoria
        output = BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            df_export.to_excel(writer, index=False, sheet_name="Viabilidades")
        output.seek(0)

        # Botones lado a lado
        # Botones alineados a los extremos
        col_b1, _, col_b2 = st.columns([1, 2.3, 1])  # Usamos una columna vacía en medio para separar

        with col_b1:
            if st.button("🔄 Refrescar Tabla"):
                st.rerun()

        with col_b2:
            st.download_button(
                label="📥 Descargar Excel",
                data=output,
                file_name="viabilidades_export.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    with col1:

        def draw_map(df, center, zoom):
            m = folium.Map(location=center, zoom_start=zoom,
                           tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
                           attr="Google")
            marker_cluster = MarkerCluster().add_to(m)

            for _, row in df.iterrows():
                popup = f"🏠 {row['ticket']} - 📍 {row['latitud']}, {row['longitud']}"

                serviciable = str(row.get('serviciable', '')).strip()
                apartment_id = str(row.get('apartment_id', '')).strip()
                tiene_presupuesto = row.get('tiene_presupuesto', False)

                # 🎯 Prioridad del color:
                # 1. Si tiene presupuesto → naranja
                # 2. Si no es serviciable → rojo
                # 3. Si es serviciable y tiene apartment_id → verde
                # 4. Otro caso → azul

                if tiene_presupuesto:
                    marker_color = 'orange'
                elif serviciable == "No":
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
        legend = """
                            {% macro html() %}
                            <div style="
                                position: fixed; 
                                bottom: 20px; left: 0px; width: 150px; 
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
                            <i style="color:green;">●</i> Serviciado<br>
                            <i style="color:red;">●</i> No serviciable<br>
                            <i style="color:orange;">●</i> Presupuesto Sí<br>
                            <i style="color:black;">●</i> No interesado<br>
                            <i style="color:purple;">●</i> Incidencia<br>
                            <i style="color:blue;">●</i> Sin estudio<br>
                            </div>
                            {% endmacro %}
                            """

        macro = MacroElement()
        macro._template = Template(legend)
        m_to_show.get_root().add_child(macro)
        map_output = st_folium(m_to_show, height=500, width=700, key="main_map",
                               returned_objects=["last_object_clicked"])

        # ⬇️ NUEVO BLOQUE: detectar clic en el mapa
        if map_output and map_output.get("last_object_clicked"):
            clicked_lat = map_output["last_object_clicked"]["lat"]
            clicked_lng = map_output["last_object_clicked"]["lng"]

            # Buscar el punto más cercano en el DataFrame (tolerancia ajustable)
            tolerance = 0.0001  # aproximadamente 11m
            match = viabilidades_df[
                (viabilidades_df["latitud"].between(clicked_lat - tolerance, clicked_lat + tolerance)) &
                (viabilidades_df["longitud"].between(clicked_lng - tolerance, clicked_lng + tolerance))
                ]

            if not match.empty:
                clicked_ticket = match.iloc[0]["ticket"]
                if clicked_ticket != st.session_state.get("selected_ticket"):
                    st.session_state["selected_ticket"] = clicked_ticket
                    st.rerun()

    # Mostrar formulario debajo
    if st.session_state["selected_ticket"]:
        st.markdown("---")
        st.subheader(f"📝 Formulario para Ticket: {st.session_state['selected_ticket']}")
        mostrar_formulario(selected_viabilidad)

        if st.session_state.get("selected_ticket"):
            st.markdown("---")
            st.subheader(f"Subir y Enviar Presupuesto para Ticket {st.session_state['selected_ticket']}")

            archivo = st.file_uploader("📁 Sube el archivo Excel del presupuesto", type=["xlsx"])

            if archivo:
                st.success("✅ Archivo cargado correctamente.")

                proyecto = st.text_input("🔖 Proyecto / Nombre del presupuesto",
                                         value=f"Ticket {st.session_state['selected_ticket']}")
                mensaje = st.text_area("📝 Mensaje para los destinatarios",
                                       value="Adjunto presupuesto para su revisión.")

                # Define los destinatarios disponibles
                destinatarios_posibles = {
                    "Rafa Sanz": "rafasanz9@gmail.com",
                    "Juan AsturPhone": "admin@asturphone.com",
                    "Correo para pruebas": "patricia@verdetuoperador.com"
                }

                seleccionados = st.multiselect("👥 Selecciona destinatarios", list(destinatarios_posibles.keys()))

                if seleccionados and st.button("🚀 Enviar presupuesto por correo"):
                    try:
                        archivo_bytes = archivo.read()
                        nombre_archivo = archivo.name

                        for nombre in seleccionados:
                            correo = destinatarios_posibles[nombre]

                            # Enviar correo
                            correo_envio_presupuesto_manual(
                                destinatario=correo,
                                proyecto=proyecto,
                                mensaje_usuario=mensaje,
                                archivo_bytes=archivo_bytes,
                                nombre_archivo=nombre_archivo
                            )

                            # Registrar envío en la BBDD
                            try:
                                conn = obtener_conexion()
                                cursor = conn.cursor()
                                cursor.execute("""
                                    INSERT INTO envios_presupuesto_viabilidad (ticket, destinatario, proyecto, fecha_envio, archivo_nombre)
                                    VALUES (?, ?, ?, ?, ?)
                                """, (
                                    st.session_state["selected_ticket"],
                                    correo,
                                    proyecto,
                                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    nombre_archivo
                                ))
                                conn.commit()
                                conn.close()
                            except Exception as db_error:
                                st.warning(
                                    f"⚠️ Correo enviado a {correo}, pero no se registró en la base de datos: {db_error}")

                        # ✅ Marcar en la base de datos que se ha enviado
                        try:
                            conn = obtener_conexion()
                            cursor = conn.cursor()
                            cursor.execute("""
                                UPDATE viabilidades
                                SET presupuesto_enviado = 1
                                WHERE ticket = ?
                            """, (st.session_state["selected_ticket"],))
                            conn.commit()
                            conn.close()
                            st.info("🗂️ Se ha registrado en la BBDD que el presupuesto ha sido enviado.")
                        except Exception as db_error:
                            st.warning(
                                f"⚠️ El correo fue enviado, pero hubo un error al actualizar la BBDD: {db_error}")

                        st.success("✅ Presupuesto enviado correctamente.")
                    except Exception as e:
                        st.error(f"❌ Error al enviar el presupuesto: {e}")

    with st.expander("📜 Historial de Envíos de Presupuesto"):
        try:
            conn = obtener_conexion()
            df_historial = pd.read_sql_query("""
                SELECT fecha_envio, destinatario, proyecto, archivo_nombre
                FROM envios_presupuesto_viabilidad
                WHERE ticket = ?
                ORDER BY datetime(fecha_envio) DESC
            """, conn, params=(st.session_state["selected_ticket"],))
            conn.close()

            if df_historial.empty:
                st.info("No se han registrado envíos de presupuesto aún.")
            else:
                df_historial["fecha_envio"] = pd.to_datetime(df_historial["fecha_envio"]).dt.strftime("%d/%m/%Y %H:%M")
                st.dataframe(df_historial, use_container_width=True)

        except Exception as e:
            st.error(f"❌ Error al cargar el historial de envíos: {e}")

    DB_URL = "sqlitecloud://ceafu04onz.g6.sqlite.cloud:8860/usuarios.db?apikey=Qo9m18B9ONpfEGYngUKm99QB5bgzUTGtK7iAcThmwvY"

    with st.expander("📤 Subir Excel de Viabilidades para actualizar base de datos"):
        uploaded_file = st.file_uploader("Selecciona un archivo Excel (.xlsx)", type=["xlsx"])

        if uploaded_file is not None:
            try:
                # Leer Excel en DataFrame
                df = pd.read_excel(io.BytesIO(uploaded_file.read()))

                # Normalizar latitud, longitud y coste
                for col in ["latitud", "longitud", "PRESUPUESTO"]:
                    if col in df.columns:
                        df[col] = df[col].astype(str).str.replace(",", ".").astype(float)

                # Mapeo Excel → BD
                mapa_columnas = {
                    "ticket": "ticket",
                    "SOLICITANTE": "usuario",
                    "Nueva Promoción": "nuevapromocion",
                    "RESULTADO": "resultado",
                    "JUSTIFICACIÓN": "justificacion",
                    "PRESUPUESTO": "coste",
                    "UUII": "zona_estudio",
                    "CONTRATOS": "contratos",
                    "latitud": "latitud",
                    "longitud": "longitud",
                    "provincia": "provincia",
                    "municipio": "municipio",
                    "poblacion": "poblacion",
                    "vial": "vial",
                    "numero": "numero",
                    "letra": "letra",
                    "cp": "cp",
                    "olt": "olt",
                    "cto_admin": "cto_admin",
                    "id_cto": "id_cto",
                    "fecha_viabilidad": "fecha_viabilidad",
                    "apartment_id": "apartment_id",
                    "nombre_cliente": "nombre_cliente",
                    "telefono": "telefono",
                    "comentarios_internos": "comentarios_internos",
                    "ESTADO": "estado",
                    "comentarios_comercial": "comentarios_comercial"
                }

                # Renombrar columnas válidas
                df = df.rename(columns={col: mapa_columnas[col] for col in df.columns if col in mapa_columnas})

                # Conectar a la base de datos
                conn = sqlitecloud.connect(DB_URL)
                cursor = conn.cursor()

                # Obtener columnas existentes en la tabla viabilidades
                cursor.execute("PRAGMA table_info(viabilidades);")
                columnas_bd = {row[1] for row in cursor.fetchall()}

                insertados = 0
                errores = []

                for _, fila in df.iterrows():
                    datos_validos = {col: fila[col] for col in fila.index if col in columnas_bd and pd.notna(fila[col])}

                    if not datos_validos:
                        continue

                    columnas_sql = ", ".join(datos_validos.keys())
                    placeholders = ", ".join(["?"] * len(datos_validos))
                    valores = list(datos_validos.values())

                    sql = f"INSERT OR REPLACE INTO viabilidades ({columnas_sql}) VALUES ({placeholders})"

                    try:
                        cursor.execute(sql, valores)
                        insertados += 1
                    except Exception as e:
                        errores.append(f"❌ Error al insertar ticket {fila.get('ticket')}: {e}")

                conn.commit()
                conn.close()

                # Mostrar resultados al usuario
                st.success(f"✅ Registros insertados correctamente: {insertados}")
                if errores:
                    st.error(f"❌ Se encontraron {len(errores)} errores durante la inserción.")
                    for e in errores:
                        st.write(e)

                # Comparar columnas esperadas y recibidas
                columnas_excel_original = set(mapa_columnas.keys())
                columnas_recibidas = set(df.columns)
                columnas_omitidas = columnas_excel_original - columnas_recibidas
                columnas_no_existentes = [col for col in df.columns if col not in columnas_bd]

                if columnas_omitidas:
                    st.warning("⚠️ Columnas esperadas en Excel pero que no llegaron:")
                    for c in columnas_omitidas:
                        st.write(f" - {c}")

                if columnas_no_existentes:
                    st.warning("⚠️ Columnas en Excel ignoradas porque no existen en la base de datos:")
                    for c in columnas_no_existentes:
                        st.write(f" - {c}")

            except Exception as e:
                st.error(f"❌ Error al procesar el archivo: {e}")


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

    with st.form(key="form_viabilidad"):
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

        # Comentarios comerciales editables
        col14 = st.columns(1)[0]
        with col14:
            comentarios_comercial = st.text_area(
                "📝 Comentarios Comerciales",
                value=click_data.get("comentarios_comercial", ""),
                key="comentarios_comercial_input"
            )

        col_nueva1, col_nueva2 = st.columns([1, 1])
        with col_nueva1:
            opciones_promocion = ["SI", "NO"]
            nueva_promocion_val = click_data.get("nuevapromocion", "NO")

            if nueva_promocion_val not in opciones_promocion:
                nueva_promocion_val = "NO"  # valor por defecto si el dato no está o es inválido

            nueva_promocion = st.selectbox(
                "🏗️ Nueva Promoción",
                opciones_promocion,
                index=opciones_promocion.index(nueva_promocion_val),
                key="nueva_promocion_input"
            )
        with col_nueva2:
            contratos = st.text_input(
                "📑 Contratos",
                value=click_data.get("contratos", ""),
                key="contratos_input"
            )

        col_nueva3, col_nueva4 = st.columns([1, 1])
        with col_nueva3:
            opciones_resultado = ["NO", "OK", "PDTE. INFORMACION RAFA", "SERVICIADO", "SOBRECOSTE"]
            resultado_val = click_data.get("resultado", "")

            if resultado_val not in opciones_resultado:
                resultado_val = opciones_resultado[0]  # asignar la primera opción como valor por defecto

            resultado = st.selectbox(
                "✅ Resultado",
                opciones_resultado,
                index=opciones_resultado.index(resultado_val),
                key="resultado_input"
            )
        with col_nueva4:
            opciones_justificacion = [
                "ZONA SUBVENCIONADA",
                "INVIABLE",
                "MAS PREVENTA",
                "RESERVADA WHL",
                "PDTE. RAFA FIN DE OBRA"
            ]

            justificacion_val = click_data.get("justificacion", opciones_justificacion[
                0])  # si no hay, poner la primera opción por defecto

            # Para evitar error si el valor en BD no está en las opciones, hacemos un fallback seguro:
            if justificacion_val not in opciones_justificacion:
                justificacion_val = opciones_justificacion[0]

            justificacion = st.selectbox(
                "📌 Justificación",
                opciones_justificacion,
                index=opciones_justificacion.index(justificacion_val),
                key="justificacion_input"
            )

        # Fila 1: apartment_id, direccion_id, olt
        col15, col16, col17 = st.columns([1, 1, 1])
        with col15:
            apartment_id_raw = click_data.get("apartment_id", "") or ""
            apartment_id_input = st.text_area(
                "🏠 Apartment_id (separa con comas)",
                value=apartment_id_raw,
                key="apartment_id_input"
            )

            # Limpiar y parsear IDs
            apartment_ids = [aid.strip() for aid in apartment_id_input.split(",") if aid.strip()]
            if apartment_ids:
                tags_html = " ".join(
                    f'<span style="display:inline-block; background:#3b82f6; color:white; padding:3px 8px; border-radius:12px; margin:2px;">{aid}</span>'
                    for aid in apartment_ids
                )
                st.markdown(f"**Apartment IDs detectados:** {tags_html}", unsafe_allow_html=True)
            else:
                st.markdown("⚠️ No se han detectado Apartment IDs.")

        with col16:
            direccion_id = st.text_input(
                "📍 Dirección ID",
                value=click_data.get("direccion_id", ""),
                key="direccion_id_input"
            )

        with col17:
            default_olt = next(
                (op for op in opciones_olt if op.startswith(f"{click_data.get('olt', '')} -")),
                opciones_olt[0]
            )
            opcion_olt = st.selectbox("⚡ OLT", opciones_olt, index=opciones_olt.index(default_olt), key="olt_input")
            olt = opcion_olt  # Guardar como texto completo

        # Fila 2: cto_admin, municipio_admin, id_cto
        col18, col19, col20 = st.columns([1, 1, 1])
        with col18:
            cto_admin = st.text_input("⚙️ Cto Admin", value=click_data.get("cto_admin", ""), key="cto_admin_input")
        with col19:
            municipio_admin = st.text_input("🌍 Municipio Admin", value=click_data.get("municipio_admin", ""),
                                            key="municipio_admin_input")
        with col20:
            id_cto = st.text_input("🔧 ID Cto", value=click_data.get("id_cto", ""), key="id_cto_input")

        # Fila 3: serviciable, coste, comentarios_internos
        col21, col22, col23 = st.columns([1, 1, 2])
        with col21:
            serviciable_val = click_data.get("serviciable", "Sí")
            index_serviciable = 0 if serviciable_val == "Sí" else 1
            serviciable = st.selectbox("🔍 ¿Es Serviciable?", ["Sí", "No"], index=index_serviciable,
                                       key="serviciable_input")
        with col22:
            coste = st.number_input(
                "💰 Coste",
                value=float(click_data.get("coste", 0.0)),
                step=0.01,
                key="coste_input"
            )
        with col23:
            comentarios_internos = st.text_area(
                "📄 Comentarios Internos",
                value=click_data.get("comentarios_internos", ""),
                key="comentarios_internos_input"
            )

        # Fila 4: zona_estudio, estado
        col24, col25 = st.columns([1, 1])
        with col24:
            zona_estudio = st.text_input(
                "🗺️ Zona de estudio",
                value=click_data.get("zona_estudio", ""),
                key="zona_estudio_input"
            )
        with col25:
            opciones_estado = [
                "Presupuesto enviado",
                "Aceptado",
                "Rechazado",
                "Cerrar",
                "Pasado a zona de estudio"
            ]
            estado_val = click_data.get("estado", "Presupuesto enviado")
            index_estado = opciones_estado.index(estado_val) if estado_val in opciones_estado else 0
            estado = st.selectbox(
                "📌 Estado",
                opciones_estado,
                index=index_estado,
                key="estado_input"
            )

        submit = st.form_submit_button(f"💾 Guardar cambios para el Ticket {ticket}")

    if submit:
        try:
            conn = obtener_conexion()
            cursor = conn.cursor()

            apartment_id_clean = ",".join(apartment_ids)  # Guardamos limpio, sin espacios sobrantes

            cursor.execute("""
                UPDATE viabilidades
                SET apartment_id = ?, direccion_id = ?, olt = ?, cto_admin = ?, id_cto = ?, municipio_admin = ?, serviciable = ?, 
                    coste = ?, comentarios_comercial = ?, comentarios_internos = ?, zona_estudio = ?, estado = ?,
                    nuevapromocion = ?, resultado = ?, justificacion = ?, contratos = ?
                WHERE ticket = ?
            """, (
                apartment_id_clean, direccion_id, olt, cto_admin, id_cto, municipio_admin,
                serviciable, coste, comentarios_comercial, comentarios_internos,
                zona_estudio, estado,
                nueva_promocion, resultado, justificacion, contratos,
                ticket
            ))

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

            cursor.execute("""
                SELECT email
                FROM usuarios
                WHERE role = 'comercial_jefe'
            """)
            jefes = cursor.fetchall()
            for fila in jefes:
                destinatarios.append(fila[0])

            descripcion_viabilidad = (
                f"📢 La viabilidad del ticket {ticket} ha sido completada.<br><br>"
                f"📌 Comentarios a comerciales: {comentarios_comercial}<br>"
                f"📍 Municipio: {municipio_admin}<br>"
                f"💰 Coste: {coste}€<br>"
                f"🔍 Es Serviciable: {serviciable}<br>"
                f"🏠 Apartment ID: {apartment_id_clean}<br>"
                f"📍 Dirección ID: {direccion_id}<br><br>"
                f"ℹ️ Por favor, revise los detalles de la viabilidad y asegúrese de que toda la información sea correcta. "
                f"Si tiene alguna pregunta o necesita realizar alguna modificación, no dude en ponerse en contacto con el equipo de administración."
            )

            for destinatario in set(destinatarios):
                correo_viabilidad_administracion(destinatario, ticket, descripcion_viabilidad)

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
            <div class="user-info">Rol: Administrador</div>
            <div class="welcome-msg">¡Bienvenido, <strong>{username}</strong>!</div>
            <hr>
            """.replace("{username}", st.session_state['username']), unsafe_allow_html=True)

        opcion = option_menu(
            menu_title=None,
            options=[
                "Home", "Ver Datos", "Ofertas Comerciales", "Viabilidades",
                "Mapa UUIIs", "Cargar Nuevos Datos", "Generar Informe",
                "Trazabilidad y logs", "Gestionar Usuarios", "Control de versiones"
            ],
            icons=[
                "house", "graph-up", "bar-chart", "check-circle", "globe", "upload",
                "file-earmark-text", "journal-text", "people", "arrow-clockwise"
            ],
            menu_icon="list",
            default_index=0,
            styles={
                "container": {
                    "padding": "0px",
                    "background-color": "#F0F7F2",  # Coincide con secondaryBackgroundColor
                    "border-radius": "0px",
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
                    "background-color": "#66B032",  # Verde principal de marca
                    "color": "white",  # Contraste
                    "font-weight": "bold"
                }
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

        sub_seccion = option_menu(
            menu_title=None,  # Sin título encima del menú
            options=["Visualizar Datos UIS", "Seguimiento de Contratos"],
            icons=["table", "file-earmark-spreadsheet"],  # Puedes cambiar iconos
            default_index=0,
            orientation="horizontal",  # horizontal para que quede tipo pestañas arriba
            styles={
                "container": {
                    "padding": "0!important",
                    "margin": "0px",
                    "background-color": "#F0F7F2",
                    "border-radius": "0px",
                    "max-width":"none"
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
        if sub_seccion == "Visualizar Datos UIS":
            st.info("ℹ️ Aquí puedes visualizar, filtrar y descargar los datos UIS en formato Excel.")

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
            columnas = data.columns.tolist()

            #st.dataframe(data[columnas], use_container_width=True)
            # Construimos las opciones de AgGrid
            gb = GridOptionsBuilder.from_dataframe(data[columnas])
            gb.configure_default_column(
                filter=True,
                floatingFilter=True,  # muestro el input de filtro directamente bajo el header
                sortable=True,
                resizable=True,
                minWidth=120,  # ancho mínimo en px
                flex=1  # reparte espacio sobrante equitativamente
            )
            gridOptions = gb.build()

            # Muestro la tabla con AgGrid en lugar de st.dataframe
            AgGrid(
                data[columnas],
                gridOptions=gridOptions,
                enable_enterprise_modules=False,
                update_mode=GridUpdateMode.NO_UPDATE,
                data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
                fit_columns_on_grid_load=True,
                height=500,
                theme='alpine-dark'
            )

            # 🔽 Botón de descarga en Excel
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
        elif sub_seccion == "Seguimiento de Contratos":
            st.info("ℹ️ Aquí puedes cargar contratos, mapear columnas, guardar en BD y sincronizar con datos UIS.")
            # -----------------------------------------------------------
            # NUEVO: Seguimiento de contratos
            # -----------------------------------------------------------
            # Mapeo de columnas del Excel a la BD
            column_mapping = {
                'Nº CONTRATO': 'num_contrato',
                'CLIENTE': 'cliente',
                'DIRECCIÓN O COORDENADAS': 'coordenadas',
                'ESTADO': 'estado',
                'Fecha contrato': 'fecha_contrato',
                'Fecha petición ADAMO': 'fecha_peticion_adamo',
                '¿Quién solicita a ADAMO?': 'quien_solicita_a_adamo',
                'FECHA INSTALACIÓN': 'fecha_instalacion',
                'ID': 'apartment_id'
            }

            uploaded = st.file_uploader(
                label="Carga tu archivo de contratos",
                type=["xlsx", "xls", "csv"],
                help="El archivo debe tener columnas: " + ", ".join(column_mapping.keys())
            )

            if uploaded:
                try:
                    df = pd.read_csv(uploaded) if uploaded.name.lower().endswith('.csv') else pd.read_excel(uploaded)
                    df.rename(columns=column_mapping, inplace=True)

                    # Convertir fechas a texto
                    for date_col in ['fecha_contrato', 'fecha_peticion_adamo', 'fecha_instalacion']:
                        if date_col in df.columns:
                            try:
                                df[date_col] = pd.to_datetime(df[date_col]).dt.strftime('%Y-%m-%d')
                            except Exception:
                                df[date_col] = df[date_col].astype(str)

                    st.success(f"✅ Archivo cargado y columnas mapeadas correctamente. Total filas: {len(df)}")

                    if st.button("💾 Guardar seguimiento en base de datos"):
                        with st.spinner("Guardando datos en la base de datos..."):
                            conn = obtener_conexion()
                            cur = conn.cursor()

                            # Crear tabla si no existe
                            cur.execute(
                                '''CREATE TABLE IF NOT EXISTS seguimiento_contratos (
                                    id INTEGER PRIMARY KEY,
                                    num_contrato TEXT,
                                    cliente TEXT,
                                    coordenadas TEXT,
                                    estado TEXT,
                                    fecha_contrato TEXT,
                                    fecha_peticion_adamo TEXT,
                                    quien_solicita_a_adamo TEXT,
                                    fecha_instalacion TEXT,
                                    apartment_id TEXT
                                )'''
                            )

                            # Borrar registros anteriores
                            cur.execute("SELECT COUNT(*) FROM seguimiento_contratos")
                            count_old = cur.fetchone()[0]
                            if count_old > 0:
                                cur.execute("DELETE FROM seguimiento_contratos")
                                conn.commit()
                                cur.execute("DELETE FROM sqlite_sequence WHERE name='seguimiento_contratos'")
                                conn.commit()
                                st.info(
                                    f"ℹ️ Se han borrado {count_old} registros anteriores y reiniciado el contador de IDs.")

                            # Insertar nuevas filas con padding en apartment_id
                            total = len(df)
                            progress = st.progress(0)
                            insert_sql = '''INSERT INTO seguimiento_contratos (
                                        num_contrato, cliente, coordenadas, estado, fecha_contrato,
                                        fecha_peticion_adamo, quien_solicita_a_adamo, fecha_instalacion, apartment_id
                                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)'''
                            for i, row in df.iterrows():
                                ap_id = row['apartment_id']
                                try:
                                    ap_id_int = int(ap_id)
                                    padded_id = 'P' + str(ap_id_int).zfill(10)
                                except (ValueError, TypeError):
                                    padded_id = None
                                cur.execute(insert_sql, (
                                    row['num_contrato'], row['cliente'], row['coordenadas'], row['estado'],
                                    row['fecha_contrato'], row['fecha_peticion_adamo'], row['quien_solicita_a_adamo'],
                                    row['fecha_instalacion'], padded_id
                                ))
                                progress.progress((i + 1) / total)

                            conn.commit()

                            # 1. Actualizar estado
                            with obtener_conexion() as conn:
                                cur = conn.cursor()
                                update_estado_sql = """
                                    UPDATE datos_uis
                                    SET estado = (
                                        SELECT sc.estado
                                        FROM seguimiento_contratos sc
                                        WHERE sc.apartment_id = datos_uis.apartment_id
                                        AND sc.estado IS NOT NULL
                                        LIMIT 1
                                    )
                                    WHERE apartment_id IN (
                                        SELECT apartment_id FROM seguimiento_contratos WHERE estado IS NOT NULL
                                    )
                                """
                                cur.execute(update_estado_sql)
                                updated_estado = cur.rowcount
                                conn.commit()

                            # 2. Actualizar contrato_uis
                            with obtener_conexion() as conn:
                                cur = conn.cursor()
                                update_contrato_sql = """
                                    UPDATE datos_uis
                                    SET contrato_uis = (
                                        SELECT sc.num_contrato
                                        FROM seguimiento_contratos sc
                                        WHERE sc.apartment_id = datos_uis.apartment_id
                                        AND sc.num_contrato IS NOT NULL
                                        LIMIT 1
                                    )
                                    WHERE apartment_id IN (
                                        SELECT apartment_id FROM seguimiento_contratos WHERE num_contrato IS NOT NULL
                                    )
                                """
                                cur.execute(update_contrato_sql)
                                updated_contratos = cur.rowcount
                                conn.commit()

                            # 3. Marcar como 'serviciable = SI' si estado es FINALIZADO
                            with obtener_conexion() as conn:
                                cur = conn.cursor()
                                update_serviciable_sql = """
                                    UPDATE datos_uis
                                    SET serviciable = 'SI'
                                    WHERE apartment_id IN (
                                        SELECT apartment_id
                                        FROM seguimiento_contratos
                                        WHERE TRIM(UPPER(estado)) = 'FINALIZADO'
                                        AND apartment_id IS NOT NULL
                                    )
                                """
                                cur.execute(update_serviciable_sql)
                                updated_serviciables = cur.rowcount
                                conn.commit()

                        # Dar feedback al usuario
                        st.success(f"✅ Registros insertados correctamente en 'seguimiento_contratos'.")
                        if updated_estado > 0:
                            st.info(f"🔄 {updated_estado} registros actualizados con estado.")
                        else:
                            st.warning("⚠️ No se actualizó ninguna fila con estado. Revisa los datos.")

                        if updated_contratos > 0:
                            st.info(f"📝 {updated_contratos} registros actualizados con contrato_uis.")
                        else:
                            st.warning("⚠️ No se actualizó ninguna fila con contrato_uis.")

                        if updated_serviciables > 0:
                            st.info(f"✅ {updated_serviciables} viviendas marcadas como serviciables.")
                        else:
                            st.warning("⚠️ No se marcó ninguna vivienda como serviciable.")

                except Exception as e:
                    st.error(f"❌ Error procesando el archivo: {e}")

            if st.checkbox("Mostrar registros existentes en la base de datos", key="view_existing_contracts_contratos"):
                with st.spinner("Cargando registros de contratos..."):
                    try:
                        conn = obtener_conexion()
                        existing = pd.read_sql("SELECT * FROM seguimiento_contratos", conn)
                        conn.close()
                        if existing.empty:
                            st.warning("⚠️ No hay registros en 'seguimiento_contratos'.")
                        else:
                            cols = st.multiselect("Filtra columnas a mostrar", existing.columns, default=existing.columns,
                                                  key="cols_existing")
                            st.dataframe(existing[cols], use_container_width=True)
                    except Exception as e:
                        st.error(f"❌ Error al cargar registros existentes: {e}")

    # Opción: Visualizar datos de la tabla comercial_rafa
    elif opcion == "Ofertas Comerciales":
        sub_seccion = option_menu(
            menu_title=None,
            options=["Ver Ofertas", "Certificación"],
            icons=["table", "file-earmark-check"],
            orientation="horizontal",
            styles={
                "container": {
                    "padding": "0px",
                    "margin": "0px",
                    "max-width":"none",
                    "background-color": "#F0F7F2",
                    "border-radius": "0px"
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
                    "font-weight": "bold",
                }
            })
        if sub_seccion == "Ver Ofertas":
            st.info("ℹ️ En esta sección puedes visualizar las ofertas registradas por los comerciales.")

            if "df" in st.session_state:
                del st.session_state["df"]

            with st.spinner("⏳ Cargando ofertas comerciales..."):
                try:
                    conn = obtener_conexion()
                    # Consultar ambas tablas
                    query_comercial_rafa = "SELECT * FROM comercial_rafa"

                    comercial_rafa_data = pd.read_sql(query_comercial_rafa, conn)
                    conn.close()

                    if comercial_rafa_data.empty:
                        st.error("❌ No se encontraron ofertas realizadas por los comerciales.")
                        return

                    # Filtrar comercial_rafa para mostrar registros con datos en 'serviciable'
                    comercial_rafa_data_filtrada = comercial_rafa_data[comercial_rafa_data['serviciable'].notna()]

                    # Unir ambas tablas en un solo DataFrame
                    if not comercial_rafa_data_filtrada.empty:
                        combined_data = pd.concat([comercial_rafa_data_filtrada], ignore_index=True)

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

            columnas = combined_data.columns.tolist()

            # Configuramos AgGrid con filtros en cabecera y anchos amplios
            gb = GridOptionsBuilder.from_dataframe(combined_data[columnas])
            gb.configure_default_column(
                filter=True,
                floatingFilter=True,
                sortable=True,
                resizable=True,
                minWidth=120,  # ancho mínimo
                flex=1  # reparte espacio extra
            )
            gridOptions = gb.build()

            AgGrid(
                combined_data[columnas],
                gridOptions=gridOptions,
                enable_enterprise_modules=False,
                update_mode=GridUpdateMode.NO_UPDATE,
                data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
                fit_columns_on_grid_load=False,
                height=500,
                theme='alpine-dark'
            )

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

            # 🔽 Solo descarga Excel, sin radio
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

                # Ver los Apartment IDs disponibles
            st.markdown("##### Eliminar Oferta Comercial")

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

                        # Ejecutar la eliminación en ambas tablas (comercial_rafa)
                        query_delete_comercial = f"DELETE FROM comercial_rafa WHERE apartment_id = '{selected_apartment_id}'"

                        # Ejecutar las consultas
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
                st.markdown("##### Descarga de imágenes de ofertas")

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
        elif sub_seccion == "Certificación":
            # Nueva sección: Generar Certificación Completa

            with st.spinner("⏳ Cargando y procesando datos..."):
                try:
                    conn = obtener_conexion()
                    if conn is None:
                        st.error("❌ No se pudo establecer conexión con la base de datos.")
                        st.stop()

                    # Paso 1: Cargar ofertas unificadas con info de datos_uis
                    query_completa = """
                    SELECT 
                        ofertas_unificadas.*,
                        datos.cto_id,
                        datos.olt,
                        datos.cto
                    FROM (
                        SELECT * FROM comercial_rafa WHERE contrato IS NULL OR LOWER(TRIM(contrato)) != 'pendiente'
                    ) AS ofertas_unificadas
                    LEFT JOIN datos_uis datos ON ofertas_unificadas.apartment_id = datos.apartment_id
                    """
                    df_ofertas = pd.read_sql(query_completa, conn)

                    # Paso 2: Calcular resumen por CTO
                    query_ctos = """
                    WITH visitas AS (
                        SELECT DISTINCT apartment_id
                        FROM (
                            SELECT apartment_id FROM comercial_rafa
                        )
                    )
                    SELECT
                        d.cto,
                        COUNT(DISTINCT d.apartment_id) AS total_apartments_en_cto,
                        SUM(CASE WHEN v.apartment_id IS NOT NULL THEN 1 ELSE 0 END) AS apartments_visitados
                    FROM datos_uis d
                    LEFT JOIN visitas v ON d.apartment_id = v.apartment_id
                    WHERE d.cto IS NOT NULL
                    GROUP BY d.cto
                    ORDER BY total_apartments_en_cto DESC
                    """
                    cursor = conn.cursor()
                    cursor.execute(query_ctos)
                    rows = cursor.fetchall()
                    cursor.close()
                    conn.close()

                    df_ctos = pd.DataFrame(rows, columns=["cto", "Total Apartments en CTO", "Apartments Visitados"])

                    # Paso 3: Unir la tabla de ofertas con el resumen por CTO
                    df_final = df_ofertas.merge(df_ctos, how="left", on="cto")

                    if df_final.empty:
                        st.warning("⚠️ No se encontraron datos para mostrar.")
                        st.stop()

                    # ——— Categorías enriquecidas y unificadas para observaciones ———
                    categorias = {
                        "Cliente con otro operador": [
                            "movistar", "adamo", "digi", "vodafone", "orange", "jazztel",
                            "euskaltel", "netcan", "o2", "yoigo", "masmovil", "másmóvil",
                            "otro operador", "no se quiere cambiar",
                            "con el móvil se arreglan", "datos ilimitados de su móvil",
                            "se apaña con los datos", "se apaña con el móvil",
                        ],
                        "Segunda residencia / vacía / cerrada": [
                            "segunda residencia", "casa vacía", "casa cerrada", "vacacional",
                            "deshabitada", "abandonada", "cabaña cerrada", "nave cerrada",
                            "campo de fútbol", "pabellón cerrado", "cerrada", "cerrado", "abandonado", "abandonada",
                            "Casa en ruinas", "Cabaña en ruinas", "No hay nadie", "Casa secundaria?", "No viven",
                            "guardar el coche"
                        ],
                        "No interesado / no necesita fibra": [
                            "no quiere", "no le interesa", "no interesado",
                            "no contratar", "decide no contratar", "hablado con el cliente decide",
                            "anciano", "persona mayor",
                            "sin internet", "no necesita fibra", "no necesita internet",
                            "no necesitan fibra", "consultorio médico", "estación de tren",
                            "nave", "ganado", "ganadería", "almacén", "cese de actividad",
                            "negocio cerrado", "bolería cerrada", "casa deshabitada",
                            "casa en obras", "en obras", "obras", "estación de tren", "ermita",
                            "estabulación", "estabulacion", "prao", "prado", "no vive nadie", "consultorio",
                            "patatas", "almacen", "ya no viven", "hace tiempo", "no estan en casa", "no están en casa", "no tiene interes",
                            "no tiene interés", "casa a vender", "casa a la venta" "boleria cerrada", "bolera cerrada", "NO ESTA INTERESADA",
                            "HABLADO CON SU HERMANA ME COMENTA Q DE MOMENTO NO ESTA INTERESADA"
                        ],
                        "Pendiente / seguimiento": [
                            "pendiente visita", "pendiente", "dejado contacto", "dejada info",
                            "dejado folleto", "presentada oferta", "hablar con hijo",
                            "volver más adelante", "quedar", "me llamará", "pasar mas adelante", "Lo tiene que pensar", "Dejada oferta",
                            "Explicada la oferta"
                        ],
                        "Cliente Verde": [
                            "contratado con verde", "cliente de verde", "ya es cliente de verde", "verde", "otro comercial"
                        ],
                        "Reformas / obra": [
                            "reforma", "obra", "reformando", "rehabilitando", "en obras"
                        ],
                        "Venta / Contrato realizado": [
                            "venta realizada", "vendido", "venta hecha",
                            "contrata fibra", "contrato solo fibra", "contrata tarifa", "contrata",
                            "contrata fibra 1000", "contrata tarifa avanza"
                        ],
                        "Sin observaciones": [
                            ""
                        ]
                    }

                    def clasificar_observacion(texto):
                        # 1) Si no es string o está vacío -> Sin observaciones
                        if not isinstance(texto, str) or texto.strip() == "":
                            return "Sin observaciones"
                        txt = texto.lower()

                        # 2) Match exacto por substring
                        for cat, claves in categorias.items():
                            for clave in claves:
                                if clave and clave in txt:
                                    return cat

                        # 3) Fuzzy matching
                        for cat, claves in categorias.items():
                            for clave in claves:
                                if clave and fuzz.partial_ratio(clave, txt) > 85:
                                    return cat

                        return "Otros / sin clasificar"

                    df_final["Categoría Observación"] = df_final["observaciones"].apply(clasificar_observacion)

                    st.info("ℹ️ Se muestran automaticamente clasificadas por categorias, todas las observaciones realizadas por los comerciales. Aquellas que no logran corresponder a una categoria "
                            "concreta, aparecen sin clasificar.")
                    # ——————————————————————————————

                    st.session_state["df"] = df_final

                    columnas = st.multiselect(
                        "📊 Selecciona las columnas a mostrar:",
                        df_final.columns.tolist(),
                        default=df_final.columns.tolist()
                    )
                    st.dataframe(df_final[columnas], use_container_width=True)

                    # Exportar a Excel
                    output = BytesIO()
                    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                        df_final.to_excel(writer, index=False, sheet_name="Certificación")
                        workbook = writer.book
                        worksheet = writer.sheets["Certificación"]

                        header_format = workbook.add_format({
                            "bold": True, "text_wrap": True, "valign": "top",
                            "fg_color": "#D7E4BC", "border": 1
                        })
                        normal_format = workbook.add_format({
                            "text_wrap": False, "valign": "top", "border": 1
                        })

                        # Encabezados
                        for col_num, val in enumerate(df_final.columns):
                            worksheet.write(0, col_num, val, header_format)

                        # Filas
                        for row in range(1, len(df_final) + 1):
                            for col in range(len(df_final.columns)):
                                v = df_final.iat[row - 1, col]
                                worksheet.write(row, col, "" if pd.isna(v) else v, normal_format)

                    st.download_button(
                        label="📥 Obtener certificación",
                        data=output.getvalue(),
                        file_name="certificacion_ofertas.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )

                except Exception as e:
                    st.error(f"❌ Error al generar la certificación completa: {e}")

    # Opción: Viabilidades (En construcción)
    elif opcion == "Viabilidades":
        st.header("Viabilidades")
        st.info(
            "ℹ️ En esta sección puedes consultar y completar los tickets de viabilidades según el comercial, filtrar los datos por etiquetas, columnas, buscar (lupa de la tabla)"
            "elementos concretos de la tabla y descargar los datos filtrados en formato excel o csv. Organiza y elige las etiquetas rojas en función de "
            "como prefieras visualizar el contenido de la tabla. Elige la viabilidad que quieras estudiar en el plano y completa los datos necesarios en el formulario"
            " que se despliega en la partes inferior. Una vez guardadas tus modificaciones, podrás refrescar la tabla de la derecha para que veas los nuevos datos.")
        viabilidades_seccion()

        # Opción: Viabilidades (En construcción)
    elif opcion == "Mapa UUIIs":
        st.info(
            "ℹ️ En esta sección puedes ver todos los datos cruzados entre ams y las ofertas de los comerciales, así como su estado actual. Ten en cuenta que tienes dos tipos de filtros "
            "diferentes. Puedes buscar por Aparment ID y de forma independiente puedes buscar por Provincia, Municipio y Población. En el caso de haber utilizado el Apartment ID y querer usar "
            "luego la otra opción de filtro, no te olvides de borrar el contenido de Aparrment ID del campo correspondiente para que se reactiven el resto de filtros.")
        mapa_seccion()

    # Opción: Generar Informes
    elif opcion == "Generar Informe":
        st.header("Generar Informe")
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

    elif opcion == "Gestionar Usuarios":
        sub_seccion = option_menu(
            menu_title=None,
            options=["Listado de usuarios", "Agregar usuarios", "Editar/eliminar usuarios"],
            icons=["people", "person-plus", "pencil-square"],
            default_index=0,
            orientation="horizontal",
            styles={
                "container": {
                    "padding": "0!important",
                    "margin": "0px",
                    "background-color": "#F0F7F2",
                    "border-radius": "0px",
                    "max-width": "none"
                },
                "icon": {
                    "color": "#2C5A2E",
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
                    "background-color": "#66B032",
                    "color": "white",
                    "font-weight": "bold"
                }
            }
        )

        log_trazabilidad(st.session_state["username"], "Gestionar Usuarios", "Accedió a la gestión de usuarios.")

        # Cargar usuarios para todas las subsecciones
        usuarios = cargar_usuarios()
        df_usuarios = pd.DataFrame(usuarios, columns=["ID", "Nombre", "Rol", "Email"]) if usuarios else pd.DataFrame()

        # 🧾 SUBSECCIÓN: Listado de usuarios
        if sub_seccion == "Listado de usuarios":
            st.info("ℹ️ Desde esta sección puedes consultar usuarios registrados en el sistema.")
            if not df_usuarios.empty:
                st.dataframe(df_usuarios, use_container_width=True, height=420)
            else:
                st.warning("No hay usuarios registrados.")

        # ➕ SUBSECCIÓN: Agregar usuarios
        elif sub_seccion == "Agregar usuarios":
            st.info("ℹ️ Desde esta sección puedes agregar nuevos usuarios al sistema.")
            nombre = st.text_input("Nombre del Usuario")
            rol = st.selectbox("Rol", ["admin", "supervisor", "comercial", "comercial_jefe", "comercial_rafa"])
            email = st.text_input("Email del Usuario")
            password = st.text_input("Contraseña", type="password")

            if st.button("Agregar Usuario"):
                if nombre and password and email:
                    agregar_usuario(nombre, rol, password, email)
                    st.success("✅ Usuario agregado correctamente.")
                else:
                    st.error("❌ Por favor, completa todos los campos.")

        # ✏️ SUBSECCIÓN: Editar/Eliminar usuarios
        elif sub_seccion == "Editar/eliminar usuarios":
            st.info("ℹ️ Edita el usuario que quieras del sistema.")
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
                                             ["admin", "supervisor", "comercial", "comercial_jefe", "comercial_rafa"],
                                             index=["admin", "supervisor", "comercial", "comercial_jefe",
                                                    "comercial_rafa"].index(usuario[1]))
                    nuevo_email = st.text_input("Nuevo Email", value=usuario[2])
                    nueva_contraseña = st.text_input("Nueva Contraseña", type="password")

                    if st.button("Guardar Cambios"):
                        editar_usuario(usuario_id, nuevo_nombre, nuevo_rol, nueva_contraseña, nuevo_email)
                        st.success("✅ Usuario editado correctamente.")
                else:
                    st.error("❌ Usuario no encontrado.")

            st.info("ℹ️ Elimina el usuario que quieras del sistema.")
            eliminar_id = st.number_input("ID del Usuario a Eliminar", min_value=1, step=1)
            if eliminar_id and st.button("Eliminar Usuario"):
                eliminar_usuario(eliminar_id)
                st.success("✅ Usuario eliminado correctamente.")

    elif opcion == "Cargar Nuevos Datos":
        st.header("Cargar Nuevos Datos")
        st.info(
            "ℹ️ Aquí puedes cargar un archivo Excel o CSV para reemplazar los datos existentes en la base de datos a una versión más moderna. "
            "¡ATENCIÓN! ¡Se eliminarán todos los datos actuales! Ten en cuenta que si realizas esta acción cualquier actualización realizada en la aplicación sobre "
            "la tabla de datos también quedará eliminada. Se recomienda recargar el excel de seguimiento de contratos en el caso de que esta carga de datos no tenga "
            "todas las columnas actualizadas."
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
                    "apartment_operational_state", "cto_id", "olt", "cto", "lat", "lng",
                    "cto_con_proyecto", "CERTIFICABLE", "COMERCIAL", "ZONA", "FECHA", "SERVICIABLE", "MOTIVO", "contrato_uis"
                ]
                columnas_faltantes = [col for col in columnas_requeridas if col not in data.columns]
                if columnas_faltantes:
                    st.error(
                        f"❌ El archivo no contiene las siguientes columnas requeridas: {', '.join(columnas_faltantes)}"
                    )
                else:
                    data_filtrada = data[columnas_requeridas].copy()
                    # Usar campos 'lat' y 'lng' del Excel para llenar LATITUD y LONGITUD
                    data_filtrada["LATITUD"] = data["lat"].astype(str).str.replace(",", ".").astype(float).round(7)
                    data_filtrada["LONGITUD"] = data["lng"].astype(str).str.replace(",", ".").astype(float).round(7)

                    # --- Leer datos antiguos antes de borrar ---
                    conn = obtener_conexion()
                    df_antiguos = pd.read_sql("SELECT * FROM datos_uis", conn)
                    st.write(
                        "✅ Datos filtrados correctamente. Procediendo a reemplazar los datos en la base de datos..."
                    )

                    cursor = conn.cursor()
                    # Eliminamos todos los registros de la tabla y reiniciamos el ID autoincremental
                    cursor.execute("DELETE FROM datos_uis")
                    cursor.execute("DELETE FROM sqlite_sequence WHERE name='datos_uis'")
                    conn.commit()
                    total_registros = len(data_filtrada)
                    insert_values = data_filtrada.values.tolist()
                    progress_bar = st.progress(0)
                    chunk_size = 500
                    num_chunks = (total_registros + chunk_size - 1) // chunk_size
                    query = """
                        INSERT INTO datos_uis (
                            id_ams, apartment_id, address_id, provincia, municipio, poblacion, vial, numero, 
                            parcela_catastral, letra, cp, site_operational_state, apartment_operational_state, 
                            cto_id, olt, cto, LATITUD, LONGITUD, cto_con_proyecto, CERTIFICABLE, COMERCIAL, ZONA, FECHA, 
                            SERVICIABLE, MOTIVO, contrato_uis
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    for i in range(num_chunks):
                        chunk = insert_values[i * chunk_size: (i + 1) * chunk_size]
                        cursor.executemany(query, chunk)
                        conn.commit()
                        progress_bar.progress(min((i + 1) / num_chunks, 1.0))

                    # --- Aquí añadimos la comparación y envío de correos ---
                    df_nuevos = data_filtrada
                    # Detectamos nuevos apartment_id
                    apt_antiguos = set(df_antiguos['apartment_id'].unique())
                    apt_nuevos = set(df_nuevos['apartment_id'].unique())
                    nuevos_apartment_id = apt_nuevos - apt_antiguos
                    df_nuevos_filtrados = df_nuevos[df_nuevos['apartment_id'].isin(nuevos_apartment_id)]
                    resumen = df_nuevos_filtrados.groupby('COMERCIAL').agg(
                        total_nuevos=('apartment_id', 'count'),
                        poblaciones_nuevas=('poblacion', lambda x: ', '.join(sorted(x.unique())))
                    ).reset_index()
                    for _, row in resumen.iterrows():
                        comercial = row["COMERCIAL"]
                        total_nuevos = row["total_nuevos"]
                        poblaciones_nuevas = row["poblaciones_nuevas"]
                        cursor.execute("SELECT email FROM usuarios WHERE username = ?", (comercial,))
                        resultado = cursor.fetchone()
                        if resultado:
                            email = resultado[0]
                            correo_nuevas_zonas_comercial(
                                destinatario=email,
                                nombre_comercial=comercial,
                                total_nuevos=total_nuevos,
                                poblaciones_nuevas=poblaciones_nuevas
                            )
                            st.write(f"📧 Notificación enviada a {comercial} ({email})")
                        else:
                            st.warning(f"⚠️ No se encontró email para el comercial: {comercial}")
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

    # Opción: Trazabilidad y logs
    elif opcion == "Trazabilidad y logs":
        st.header("Trazabilidad y logs")
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

                    # ✅ Solo botón de descarga Excel
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
        INNER JOIN comercial_rafa o 
            ON d.apartment_id = o.apartment_id
    """
    total_visitados = ejecutar_consulta(query_visitados)

    # 🔹 3️⃣ Cantidad de ventas (visitados donde contrato = 'Sí')
    query_ventas = """
        SELECT COUNT(DISTINCT d.apartment_id)
        FROM datos_uis d
        INNER JOIN comercial_rafa o 
            ON d.apartment_id = o.apartment_id
        WHERE LOWER(o.contrato) = 'sí'
    """
    total_ventas = ejecutar_consulta(query_ventas)

    # 🔹 4️⃣ Cantidad de incidencias (donde incidencia = 'Sí')
    query_incidencias = """
        SELECT COUNT(DISTINCT d.apartment_id)
        FROM datos_uis d
        INNER JOIN comercial_rafa o 
            ON d.apartment_id = o.apartment_id
        WHERE LOWER(o.incidencia) = 'sí'
    """
    total_incidencias = ejecutar_consulta(query_incidencias)

    # 🔹 5️⃣ Cantidad de viviendas no serviciables (donde serviciable = 'No')
    query_no_serviciables = """
        SELECT COUNT(DISTINCT apartment_id)
        FROM comercial_rafa
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

    # 🔹 VIABILIDADES: Cálculo y resumen textual
    conn = obtener_conexion()
    query_viabilidades = """
           SELECT 
               CASE 
                   WHEN LOWER(serviciable) = 'sí' THEN 'sí'
                   WHEN LOWER(serviciable) = 'no' THEN 'no'
                   ELSE 'desconocido'
               END AS serviciable,
               COUNT(*) as total
           FROM viabilidades
           WHERE STRFTIME('%Y-%m-%d', fecha_viabilidad) BETWEEN ? AND ?
           GROUP BY serviciable
       """
    df_viabilidades = pd.read_sql_query(query_viabilidades, conn, params=(fecha_inicio, fecha_fin))
    conn.close()

    total_viabilidades = df_viabilidades['total'].sum()
    total_serviciables = df_viabilidades[df_viabilidades['serviciable'] == 'sí']['total'].sum() if 'sí' in \
                                                                                                          df_viabilidades[
                                                                                                              'serviciable'].values else 0
    total_no_serviciables_v = df_viabilidades[df_viabilidades['serviciable'] == 'no']['total'].sum() if 'no' in \
                                                                                                               df_viabilidades[
                                                                                                                   'serviciable'].values else 0

    porcentaje_viables = (total_serviciables / total_viabilidades * 100) if total_viabilidades > 0 else 0
    porcentaje_no_viables = (total_no_serviciables_v / total_viabilidades * 100) if total_viabilidades > 0 else 0

    resumen_viabilidades = f"""
       <div style="text-align: justify;">
       Además, durante el mismo periodo se registraron <strong>{total_viabilidades}</strong> viabilidades realizadas. De estas, <strong>{total_serviciables}</strong> fueron consideradas <strong>serviciables</strong> (<strong>{porcentaje_viables:.2f}%</strong>) y <strong>{total_no_serviciables_v}</strong> fueron <strong>no serviciables</strong> (<strong>{porcentaje_no_viables:.2f}%</strong>). Las restantes, son viabilidades aun en estudio.
       </div>
       <br>
       """

    st.markdown(resumen_viabilidades, unsafe_allow_html=True)

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
        # Conexión a la base de datos
        conn = sqlitecloud.connect(
            "sqlitecloud://ceafu04onz.g6.sqlite.cloud:8860/usuarios.db?apikey=Qo9m18B9ONpfEGYngUKm99QB5bgzUTGtK7iAcThmwvY"
        )
        cursor = conn.cursor()

        st.subheader("Control de versiones")
        st.info("ℹ️ Aquí puedes ver el historial de cambios y versiones de la aplicación. Cada entrada incluye el número de versión y una breve descripción de lo que se ha actualizado o modificado.")

        # --- FORMULARIO PARA NUEVA VERSIÓN ---
        with st.form("form_nueva_version"):
            nueva_version = st.text_input("Versión (ej. v1.1.0)")
            descripcion = st.text_area("Descripción de la versión")
            enviar = st.form_submit_button("Agregar nueva versión")

            if enviar:
                if not nueva_version.strip() or not descripcion.strip():
                    st.error("Por favor completa todos los campos.")
                else:
                    fecha = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    # Insertar en base de datos
                    cursor.execute(
                        "INSERT INTO versiones (version, descripcion, fecha) VALUES (?, ?, ?)",
                        (nueva_version.strip(), descripcion.strip(), fecha)
                    )
                    conn.commit()

                    # Obtener todos los emails de usuarios para notificación
                    cursor.execute("SELECT email FROM usuarios")
                    usuarios = cursor.fetchall()

                    for (email,) in usuarios:
                        correo_nueva_version(email, nueva_version.strip(), descripcion.strip())

                    st.success("Versión agregada y notificaciones enviadas.")
                    st.rerun()  # Recarga para mostrar la nueva versión

        # --- LISTADO DE VERSIONES ---
        cursor.execute("SELECT version, descripcion, fecha FROM versiones ORDER BY id DESC")
        versiones = cursor.fetchall()

        if not versiones:
            st.warning("No hay versiones registradas todavía.")
        else:
            for version, descripcion, fecha in versiones:
                st.markdown(
                    f"<div style='background-color: #f7f7f7; padding: 10px; margin-bottom: 10px;'>"
                    f"<p style='font-size: 14px; color: #666; margin: 0;'>"
                    f"<strong style='color: #4CAF50; font-size: 16px;'>{version}</strong> "
                    f"<em style='color: #999; font-size: 12px;'>({fecha})</em> - {descripcion}</p>"
                    f"</div>", unsafe_allow_html=True
                )

        st.markdown(
            "<br><i style='font-size: 14px; color: #888;'>"
            "Nota técnica: Esta sección muestra el historial completo de cambios aplicados al sistema. "
            "Asegúrese de revisar las versiones anteriores para comprender las mejoras y correcciones implementadas."
            "</i>", unsafe_allow_html=True
        )

        conn.close()

    except Exception as e:
        st.error(f"Ha ocurrido un error al cargar el control de versiones: {e}")

# Función para crear el gráfico interactivo de Serviciabilidad
def create_serviciable_graph():
    # Conectar y obtener datos de la primera tabla
    conn = obtener_conexion()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM comercial_rafa WHERE serviciable = 'Sí';")
    datos_uis_count = cursor.fetchone()[0]  # Obtener el valor numérico
    conn.close()

    # Conectar y obtener datos de la segunda tabla
    conn = obtener_conexion()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM comercial_rafa WHERE serviciable = 'No';")
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
        FROM comercial_rafa
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
    conn = obtener_conexion()
    cursor = conn.cursor()

    cursor.execute("SELECT Tipo_Vivienda, COUNT(*) FROM comercial_rafa GROUP BY Tipo_Vivienda;")
    comercial_rafa_data = cursor.fetchall()  # Obtener todos los resultados
    conn.close()

    # Convertir los datos de ambas tablas en DataFrames
    df_comercial_rafa = pd.DataFrame(comercial_rafa_data, columns=["Tipo_Vivienda", "Count_comercial_rafa"])

    # Reemplazar los valores nulos o vacíos con "Asignado - No visitado" en la tabla comercial_rafa
    # Usamos `fillna` para poner 'Asignado - No visitado' en los tipos de vivienda que no tengan datos en la tabla comercial_rafa
    df_comercial_rafa['Tipo_Vivienda'] = df_comercial_rafa['Tipo_Vivienda'].fillna('Asignado - No visitado')

    df = df_comercial_rafa.copy()

    # Si hay valores en 'Count_comercial_rafa' como 0, los cambiamos a 'Asignado - No visitado'
    df['Tipo_Vivienda'] = df['Tipo_Vivienda'].apply(
        lambda x: 'Asignado - No visitado' if x == 0 else x
    )

    # Crear gráfico de barras con Plotly
    fig = px.bar(df, x="Tipo_Vivienda", y=["Count_comercial_rafa"],
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
