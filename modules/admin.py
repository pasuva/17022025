import secrets
import urllib
import zipfile, sqlite3, datetime, bcrypt, os, sqlitecloud, io
from modules.notificaciones import correo_usuario, correo_nuevas_zonas_comercial, correo_excel_control, correo_envio_presupuesto_manual, correo_nueva_version, correo_asignacion_puntos_existentes, correo_viabilidad_comercial
from datetime import datetime as dt  # Para evitar conflicto con datetime
from streamlit_option_menu import option_menu
from datetime import datetime
from streamlit_cookies_controller import CookieController
from st_aggrid import AgGrid, GridOptionsBuilder, DataReturnMode, GridUpdateMode
from io import BytesIO
from google.oauth2.service_account import Credentials
import gspread
import json
from googleapiclient.discovery import build
import warnings
import cloudinary
import cloudinary.uploader
import cloudinary.api
import ftfy

import plotly.express as px
import plotly.graph_objects as go

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

def actualizar_google_sheet_desde_db(sheet_id, sheet_name="Viabilidades"):
    try:
        # --- 1️⃣ Leer datos de la base de datos ---
        conn = obtener_conexion()
        df_db = pd.read_sql("SELECT * FROM viabilidades", conn)
        conn.close()

        if df_db.empty:
            st.warning("⚠️ No hay datos en la tabla 'viabilidades'.")
            return

        # --- 2️⃣ Expandir filas con múltiples apartment_id ---
        expanded_rows = []
        for _, row in df_db.iterrows():
            apartment_ids = str(row["apartment_id"]).split(",") if pd.notna(row["apartment_id"]) else [""]
            for apt in apartment_ids:
                new_row = row.copy()
                new_row["apartment_id"] = apt.strip()
                expanded_rows.append(new_row)
        df_db_expanded = pd.DataFrame(expanded_rows)

        # --- 3️⃣ Cargar credenciales ---
        posibles_rutas = [
            "modules/carga-contratos-verde-c5068516c7cf.json",
            "/etc/secrets/carga-contratos-verde-c5068516c7cf.json",
            os.path.join(os.path.dirname(__file__), "carga-contratos-verde-c5068516c7cf.json"),
        ]
        ruta_credenciales = next((r for r in posibles_rutas if os.path.exists(r)), None)

        if not ruta_credenciales and "GOOGLE_APPLICATION_CREDENTIALS_JSON" in os.environ:
            creds_dict = json.loads(os.environ["GOOGLE_APPLICATION_CREDENTIALS_JSON"])
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
            creds = Credentials.from_service_account_info(
                creds_dict,
                scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
            )
        elif ruta_credenciales:
            creds = Credentials.from_service_account_file(
                ruta_credenciales,
                scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
            )
        else:
            raise ValueError("❌ No se encontraron credenciales de Google Service Account.")

        # --- 4️⃣ Conexión con Google Sheets ---
        service = build("sheets", "v4", credentials=creds)
        sheet_metadata = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
        available_sheets = [s["properties"]["title"] for s in sheet_metadata.get("sheets", [])]

        if sheet_name not in available_sheets:
            st.warning(f"⚠️ La hoja '{sheet_name}' no existe. Se usará '{available_sheets[0]}' en su lugar.")
            sheet_name = available_sheets[0]

        sheet = service.spreadsheets()

        # --- 5️⃣ Leer encabezados y datos actuales ---
        result = sheet.values().get(spreadsheetId=sheet_id, range=f"{sheet_name}!1:1").execute()
        headers = result.get("values", [[]])[0]

        if not headers:
            st.toast("❌ No se encontraron encabezados en la hoja de Google Sheets.")
            return

        result_data = sheet.values().get(spreadsheetId=sheet_id, range=sheet_name).execute()
        values = result_data.get("values", [])
        df_sheet = pd.DataFrame(values[1:], columns=headers) if len(values) > 1 else pd.DataFrame(columns=headers)

        # --- 6️⃣ Mapear columnas Excel -> Base de datos ---
        excel_to_db_map = {
            "SOLICITANTE": "usuario",
            "Nueva Promoción": "nuevapromocion",
            "RESULTADO": "resultado",
            "JUSTIFICACIÓN": "justificacion",
            "PRESUPUESTO": "coste",
            "UUII": "zona_estudio",
            "CONTRATOS": "contratos",
            "RESPUESTA COMERCIAL": "respuesta_comercial"
        }

        # --- 7️⃣ Actualizar o agregar filas por apartment_id y ticket ---
        updated = 0
        added = 0
        df_sheet = df_sheet.copy()

        # Normalizar columnas clave
        if "apartment_id" not in df_sheet.columns:
            st.toast("❌ La hoja no tiene columna 'apartment_id'.")
            return
        if "ticket" not in df_sheet.columns:
            df_sheet["ticket"] = ""

        df_sheet["apartment_id"] = df_sheet["apartment_id"].astype(str).str.strip().str.upper()
        df_sheet["ticket"] = df_sheet["ticket"].astype(str).str.strip()

        for _, row_db in df_db_expanded.iterrows():
            apt_db = str(row_db.get("apartment_id", "")).strip().upper()
            ticket_db = str(row_db.get("ticket", "")).strip()
            if not ticket_db:
                continue  # ignorar filas sin ticket

            # Buscar coincidencia exacta de ticket + apartment_id
            mask = (
                    (df_sheet["ticket"] == ticket_db) &
                    (df_sheet["apartment_id"] == apt_db)
            )

            # --- Si la fila ya existe en el Sheet ---
            if mask.any():
                idx = df_sheet[mask].index[0]
                cambios_realizados = False

                # 🔹 Actualizar todas las columnas mapeadas y coincidentes
                for col in headers:
                    db_col = excel_to_db_map.get(col, col)  # Usa el mapeo si existe, sino el mismo nombre
                    if db_col in df_db_expanded.columns:
                        nuevo_valor = "" if pd.isna(row_db[db_col]) else str(row_db[db_col])
                        actual_valor = "" if pd.isna(df_sheet.at[idx, col]) else str(df_sheet.at[idx, col])
                        # Compara sin espacios y sin distinción de mayúsculas
                        if nuevo_valor.strip() != actual_valor.strip():
                            df_sheet.at[idx, col] = nuevo_valor
                            cambios_realizados = True

                if cambios_realizados:
                    updated += 1

            # --- Si la fila no existe, crearla ---
            else:
                new_row = {col: "" for col in headers}
                for col in headers:
                    db_col = excel_to_db_map.get(col, col)
                    if db_col in df_db_expanded.columns:
                        new_row[col] = "" if pd.isna(row_db[db_col]) else str(row_db[db_col])
                new_row["ticket"] = ticket_db
                new_row["apartment_id"] = apt_db
                df_sheet = pd.concat([df_sheet, pd.DataFrame([new_row])], ignore_index=True)
                added += 1

        # --- 8️⃣ Escribir datos actualizados ---
        values_out = [headers] + df_sheet.fillna("").astype(str).values.tolist()
        sheet.values().clear(spreadsheetId=sheet_id, range=sheet_name).execute()
        sheet.values().update(
            spreadsheetId=sheet_id,
            range=sheet_name,
            valueInputOption="RAW",
            body={"values": values_out}
        ).execute()

        st.toast(
            f"✅ Google Sheet '{sheet_name}' actualizado correctamente.\n"
            f"🟢 {updated} filas actualizadas.\n"
            f"🆕 {added} filas nuevas añadidas."
        )

    except Exception as e:
        st.toast(f"❌ Error al actualizar la hoja de Google Sheets: {e}")

def cargar_contratos_google():
    try:
        # --- Detectar entorno y elegir archivo de credenciales ---
        posibles_rutas = [
            "modules/carga-contratos-verde-c5068516c7cf.json",  # Render: secret file
            "/etc/secrets/carga-contratos-verde-c5068516c7cf.json",      # Otra ruta posible en Render
            os.path.join(os.path.dirname(__file__), "carga-contratos-verde-c5068516c7cf.json"),  # Local
        ]

        ruta_credenciales = None
        for r in posibles_rutas:
            if os.path.exists(r):
                ruta_credenciales = r
                break

        if not ruta_credenciales and "GOOGLE_APPLICATION_CREDENTIALS_JSON" in os.environ:
            # Si no hay archivo pero sí variable de entorno
            creds_dict = json.loads(os.environ["GOOGLE_APPLICATION_CREDENTIALS_JSON"])
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
            creds = Credentials.from_service_account_info(creds_dict, scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive"
            ])
        elif ruta_credenciales:
            print(f"🔑 Usando credenciales desde: {ruta_credenciales}")
            creds = Credentials.from_service_account_file(
                ruta_credenciales,
                scopes=[
                    "https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive"
                ]
            )
        else:
            raise ValueError("❌ No se encontraron credenciales de Google Service Account.")

        # Crear cliente
        client = gspread.authorize(creds)

        # --- Abrir la hoja de Google Sheets ---
        sheet = client.open("SEGUIMIENTO CLIENTES/CONTRATOS VERDE").worksheet("LISTADO DE ESTADO DE CONTRATOS")
        data = sheet.get_all_records()

        if not data:
            print("⚠️ Hoja cargada pero sin registros. Revisa si la primera fila tiene encabezados correctos.")
            return pd.DataFrame()

        df = pd.DataFrame(data)

        # --- Mapeo de columnas ---
        column_mapping = {
            'Nº CONTRATO': 'num_contrato',
            'APARTMENT ID': 'apartment_id',
            'CLIENTE': 'cliente',
            'COORDENADAS': 'coordenadas',
            'ESTADO': 'estado',
            'COMERCIAL': 'comercial',
            'FECHA INGRESO': 'fecha_ingreso',
            'FECHA INSTALACIÓN': 'fecha_instalacion',
            'FECHA FIN CONTRATO': 'fecha_fin_contrato',
            'FECHA INICIO CONTRATO': 'fecha_inicio_contrato',
            'COMENTARIOS': 'comentarios'
        }
        df.rename(columns=column_mapping, inplace=True)

        # --- Normalizar fechas ---
        for date_col in ['fecha_inicio_contrato', 'fecha_ingreso', 'fecha_instalacion', 'fecha_fin_contrato']:
            if date_col in df.columns:
                try:
                    df[date_col] = pd.to_datetime(df[date_col]).dt.strftime('%Y-%m-%d')
                except Exception:
                    df[date_col] = df[date_col].astype(str)

        print("✅ Datos cargados. Columnas:", df.columns.tolist(), "Total filas:", len(df))
        return df

    except Exception as e:
        print(f"❌ Error cargando contratos desde Google Sheets: {e}")
        return pd.DataFrame()

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
        st.toast(f"Usuario '{username}' creado con éxito.")
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
        st.toast(f"El usuario '{username}' ya existe.")
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

        st.toast(f"Usuario con ID {id} actualizado correctamente.")
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
        st.toast(f"Usuario con ID {id} no encontrado.")

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
        st.toast("Usuario no encontrado.")

def cargar_datos_uis():
    """Carga y cachea los datos de las tablas 'datos_uis', 'comercial_rafa'."""
    conn = obtener_conexion()

    # Consulta de datos_uis
    query_datos_uis = """
        SELECT apartment_id, latitud, longitud, provincia, municipio, poblacion, tipo_olt_rental, serviciable,
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


import folium
import pandas as pd
import numpy as np
import streamlit as st
from folium.plugins import MarkerCluster, Geocoder, Fullscreen, MousePosition, MeasureControl
from streamlit_folium import st_folium
from branca.element import Template, MacroElement
from typing import Tuple, Dict, List
import time
from functools import lru_cache


# ============================================
# FUNCIONES DE CARGUE OPTIMIZADAS
# ============================================

@st.cache_data(ttl=600, max_entries=20)
def cargar_provincias() -> List[str]:
    """Carga la lista de provincias disponibles (cache por 10 minutos)"""
    conn = obtener_conexion()
    try:
        query = "SELECT DISTINCT provincia FROM datos_uis WHERE provincia IS NOT NULL ORDER BY provincia"
        df = pd.read_sql(query, conn)
        return df['provincia'].tolist()
    finally:
        conn.close()


@st.cache_data(ttl=300, max_entries=50)
def cargar_datos_por_provincia(provincia: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Carga datos de una provincia específica con columnas esenciales"""
    conn = obtener_conexion()
    try:
        # Solo columnas necesarias para el mapa
        query_uis = f"""
            SELECT apartment_id, latitud, longitud, provincia, municipio, 
                   poblacion, vial, numero
            FROM datos_uis 
            WHERE provincia = ? 
            AND latitud IS NOT NULL 
            AND longitud IS NOT NULL
            AND latitud != 0 
            AND longitud != 0
            LIMIT 1000  -- Limitar para carga rápida
        """

        query_comercial = f"""
            SELECT apartment_id, comercial, serviciable, incidencia, contrato
            FROM comercial_rafa c
            WHERE EXISTS (
                SELECT 1 FROM datos_uis d 
                WHERE d.apartment_id = c.apartment_id 
                AND d.provincia = ?
            )
        """

        datos_uis = pd.read_sql(query_uis, conn, params=(provincia,))
        comercial_rafa = pd.read_sql(query_comercial, conn, params=(provincia,))

        # Optimizar tipos de datos
        if not datos_uis.empty and 'latitud' in datos_uis.columns and 'longitud' in datos_uis.columns:
            datos_uis[['latitud', 'longitud']] = datos_uis[['latitud', 'longitud']].astype(float)

        return datos_uis, comercial_rafa
    finally:
        conn.close()


@st.cache_data(ttl=300, max_entries=10)
def cargar_datos_limitados() -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Carga datos limitados para vista inicial rápida"""
    conn = obtener_conexion()
    try:
        # Solo primeros 500 registros para carga rápida
        query_uis = """
            SELECT apartment_id, latitud, longitud, provincia, municipio, 
                   poblacion, vial, numero
            FROM datos_uis 
            WHERE latitud IS NOT NULL 
            AND longitud IS NOT NULL
            AND latitud != 0 
            AND longitud != 0
            LIMIT 500
        """

        query_comercial = """
            SELECT apartment_id, comercial, serviciable, incidencia, contrato
            FROM comercial_rafa
            LIMIT 1000
        """

        datos_uis = pd.read_sql(query_uis, conn)
        comercial_rafa = pd.read_sql(query_comercial, conn)

        if not datos_uis.empty and 'latitud' in datos_uis.columns and 'longitud' in datos_uis.columns:
            datos_uis[['latitud', 'longitud']] = datos_uis[['latitud', 'longitud']].astype(float)

        return datos_uis, comercial_rafa
    finally:
        conn.close()


@st.cache_data(ttl=300)
def buscar_por_id(apartment_id: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Búsqueda optimizada por ID de apartment"""
    conn = obtener_conexion()
    try:
        query_uis = f"""
            SELECT apartment_id, latitud, longitud, provincia, municipio, 
                   poblacion, vial, numero
            FROM datos_uis 
            WHERE apartment_id = ? 
            AND latitud IS NOT NULL 
            AND longitud IS NOT NULL
        """

        query_comercial = f"""
            SELECT apartment_id, comercial, serviciable, incidencia, contrato
            FROM comercial_rafa
            WHERE apartment_id = ?
        """

        datos_uis = pd.read_sql(query_uis, conn, params=(apartment_id,))
        comercial_rafa = pd.read_sql(query_comercial, conn, params=(apartment_id,))

        if not datos_uis.empty and 'latitud' in datos_uis.columns and 'longitud' in datos_uis.columns:
            datos_uis[['latitud', 'longitud']] = datos_uis[['latitud', 'longitud']].astype(float)

        return datos_uis, comercial_rafa
    finally:
        conn.close()


# ============================================
# FUNCIONES AUXILIARES OPTIMIZADAS
# ============================================

def crear_diccionarios_optimizados(comercial_df: pd.DataFrame) -> Dict:
    """Crea diccionarios optimizados para búsqueda rápida"""
    dicts = {
        'serviciable': {},
        'contrato': {},
        'incidencia': {},
        'comercial': {}
    }

    if comercial_df.empty:
        return dicts

    # Crear diccionarios solo para columnas que existen
    for columna in dicts.keys():
        if columna in comercial_df.columns:
            # Usar vectorización para mejor rendimiento
            mask = comercial_df[columna].notna()
            if mask.any():
                subset = comercial_df[mask]
                dicts[columna] = pd.Series(
                    subset[columna].astype(str).str.strip().str.lower().values,
                    index=subset['apartment_id']
                ).to_dict()

    return dicts


def determinar_color_marcador(apt_id: str, serv_uis: str, dicts: Dict) -> Tuple[str, str]:
    """Determina el color y categoría del marcador (función vectorizable)"""

    # Valores del diccionario
    incidencia = dicts['incidencia'].get(apt_id, '')
    serv_oferta = dicts['serviciable'].get(apt_id, '')
    contrato = dicts['contrato'].get(apt_id, '')

    # Lógica de decisión optimizada
    if incidencia == 'sí':
        return 'purple', 'incidencia'
    elif serv_oferta == 'no':
        return 'red', 'no_serviciable'
    elif serv_uis == 'sí':
        return 'green', 'serviciable'
    elif contrato == 'sí' and serv_uis != 'sí':
        return 'orange', 'contratado'
    elif contrato == 'no interesado' and serv_uis != 'sí':
        return 'gray', 'no_interesado'
    else:
        return 'blue', 'no_visitado'


# ============================================
# FUNCIÓN PRINCIPAL CON FILTROS EN ZONA PRINCIPAL
# ============================================

def agregar_leyenda_al_mapa(mapa):
    """Añade una leyenda como control HTML al mapa"""

    leyenda_html = '''
    <div style="position: fixed; 
                bottom: 50px; left: 50px; 
                background-color: white; 
                border: 2px solid grey; 
                z-index: 9999; 
                padding: 10px;
                border-radius: 5px;
                font-family: Arial;
                font-size: 12px;
                box-shadow: 0 0 10px rgba(0,0,0,0.2);">
        <h4 style="margin: 0 0 10px 0;">Leyenda</h4>
        <div style="display: flex; align-items: center; margin-bottom: 5px;">
            <div style="width: 15px; height: 15px; background-color: green; 
                        margin-right: 8px; border-radius: 50%;"></div>
            <span>Serviciable</span>
        </div>
        <div style="display: flex; align-items: center; margin-bottom: 5px;">
            <div style="width: 15px; height: 15px; background-color: red; 
                        margin-right: 8px; border-radius: 50%;"></div>
            <span>No serviciable</span>
        </div>
        <div style="display: flex; align-items: center; margin-bottom: 5px;">
            <div style="width: 15px; height: 15px; background-color: blue; 
                        margin-right: 8px; border-radius: 50%;"></div>
            <span>Contratado</span>
        </div>
        <div style="display: flex; align-items: center; margin-bottom: 5px;">
            <div style="width: 15px; height: 15px; background-color: orange; 
                        margin-right: 8px; border-radius: 50%;"></div>
            <span>Incidencia</span>
        </div>
        <div style="display: flex; align-items: center; margin-bottom: 5px;">
            <div style="width: 15px; height: 15px; background-color: gray; 
                        margin-right: 8px; border-radius: 50%;"></div>
            <span>No interesado</span>
        </div>
        <div style="display: flex; align-items: center;">
            <div style="width: 15px; height: 15px; background-color: black; 
                        margin-right: 8px; border-radius: 50%;"></div>
            <span>No visitado</span>
        </div>
    </div>
    '''

    mapa.get_root().html.add_child(folium.Element(leyenda_html))


def determinar_color_marcador(apartment_id: str, serv_uis: str, dicts: Dict) -> Tuple[str, str]:
    """
    Determina el color y estado del marcador basado en múltiples fuentes

    Prioridad:
    1. Datos comerciales (si existe registro)
    2. Datos UIS (serv_uis)
    3. Por defecto: 'no_visitado'
    """

    # Primero verificar si existe en datos comerciales
    if apartment_id in dicts.get('serviciable', {}):
        serv_comercial = dicts['serviciable'][apartment_id]

        # Verificar si hay incidencia
        if apartment_id in dicts.get('incidencia', {}) and dicts['incidencia'][apartment_id] == 'sí':
            return 'orange', 'incidencia'

        # Verificar si está contratado
        if apartment_id in dicts.get('contrato', {}) and dicts['contrato'][apartment_id] == 'sí':
            return 'blue', 'contratado'

        # Verificar estado serviciable
        if serv_comercial == 'sí':
            return 'green', 'serviciable'
        elif serv_comercial == 'no':
            return 'red', 'no_serviciable'
        elif serv_comercial == 'no interesado':
            return 'gray', 'no_interesado'

    # Si no hay datos comerciales, usar datos UIS
    if serv_uis and isinstance(serv_uis, str):
        serv_uis_lower = serv_uis.lower()
        if 'serviciable' in serv_uis_lower or 'sí' in serv_uis_lower:
            return 'green', 'serviciable'
        elif 'no serviciable' in serv_uis_lower or 'no' in serv_uis_lower:
            return 'red', 'no_serviciable'

    # Por defecto
    return 'black', 'no_visitado'


def mostrar_info_detallada(apartment_id: str, datos_filtrados: pd.DataFrame,
                           comercial_filtradas: pd.DataFrame, dicts: Dict):
    """Muestra información detallada del apartamento clicado"""

    # Quitar el prefijo "🏠 " si existe
    apartment_id = apartment_id.replace("🏠 ", "")

    st.subheader(f"🏠 **Información del Apartment ID: {apartment_id}**")

    # Buscar datos en ambos dataframes
    datos_apt = datos_filtrados[datos_filtrados['apartment_id'] == apartment_id]
    comercial_apt = comercial_filtradas[comercial_filtradas['apartment_id'] == apartment_id]

    if datos_apt.empty:
        st.warning("No se encontraron datos para este apartamento")
        return

    datos_apt = datos_apt.iloc[0]

    # Crear columnas para la visualización
    col1, col2 = st.columns(2)

    # Columna 1: Datos generales
    with col1:
        st.markdown("##### 🔹 **Datos Generales**")

        datos_generales = {
            "ID Apartamento": datos_apt.get('apartment_id', 'N/A'),
            "Provincia": datos_apt.get('provincia', 'N/A'),
            "Municipio": datos_apt.get('municipio', 'N/A'),
            "Población": datos_apt.get('poblacion', 'N/A'),
            "Dirección": f"{datos_apt.get('vial', '')} {datos_apt.get('numero', '')} {datos_apt.get('letra', '')}",
            "Código Postal": datos_apt.get('cp', 'N/A'),
            "CTO ID": datos_apt.get('cto_id', 'N/A'),
            "Zona": datos_apt.get('zona', 'N/A')
        }

        for key, value in datos_generales.items():
            st.text(f"{key}: {value}")

    # Columna 2: Datos comerciales y estado
    with col2:
        st.markdown("##### 🔹 **Estado y Comercial**")

        # Determinar estado actual
        serv_uis = str(datos_apt.get('serviciable', '')).lower().strip()
        _, estado = determinar_color_marcador(apartment_id, serv_uis, dicts)

        st.metric("Estado", estado.replace('_', ' ').title())

        if apartment_id in dicts.get('comercial', {}):
            st.metric("Comercial", dicts['comercial'][apartment_id])

        if apartment_id in dicts.get('serviciable', {}):
            st.metric("Serviciable", dicts['serviciable'][apartment_id].title())

    # Sección de comentarios si hay datos comerciales
    if not comercial_apt.empty:
        st.markdown("---")
        st.markdown("##### 📝 **Información Comercial**")

        # Mostrar datos comerciales
        comercial_data = comercial_apt.iloc[0]
        cols_com = st.columns(2)

        with cols_com[0]:
            if 'motivo_serviciable' in comercial_data:
                st.text(f"Motivo: {comercial_data['motivo_serviciable']}")
            if 'nombre_cliente' in comercial_data:
                st.text(f"Cliente: {comercial_data['nombre_cliente']}")

        with cols_com[1]:
            if 'telefono' in comercial_data:
                st.text(f"Teléfono: {comercial_data['telefono']}")
            if 'observaciones' in comercial_data:
                st.text(f"Observaciones: {comercial_data['observaciones']}")

        # Campo para comentarios
        st.markdown("##### 💬 **Comentarios**")

        # Obtener comentario actual
        comentario_actual = comercial_data.get('comentarios', '')
        if pd.isna(comentario_actual):
            comentario_actual = ""

        nuevo_comentario = st.text_area(
            "Añadir o editar comentario:",
            value=comentario_actual,
            height=100,
            key=f"comentario_{apartment_id}"
        )

        if st.button("💾 Guardar Comentario", key=f"guardar_{apartment_id}"):
            try:
                # Actualizar el comentario en los datos
                if 'guardar_comentario' in globals():
                    resultado = guardar_comentario(apartment_id, nuevo_comentario, "comercial_rafa")
                    if resultado:
                        st.success("✅ Comentario guardado exitosamente")
                        st.rerun()
                else:
                    st.info("⚠️ La función 'guardar_comentario' no está disponible")
            except Exception as e:
                st.error(f"❌ Error al guardar: {str(e)}")


def mapa_seccion():
    """Muestra un mapa interactivo con filtros en zona principal"""

    # Fila 1: Búsqueda por ID y Provincia
    col1, col2, col3 = st.columns([2, 2, 1])

    with col1:
        apartment_search = st.text_input(
            "Buscar por Apartment ID",
            placeholder="Ej: APT123456",
            help="Busca un apartment específico por su ID",
            key="search_id_input"
        )

    with col2:
        # Cargar provincias
        with st.spinner("Cargando..."):
            provincias = cargar_provincias()

        provincia_sel = st.selectbox(
            "Provincia",
            ["Selecciona provincia"] + provincias,
            key="select_provincia_input"
        )

    with col3:
        modo_busqueda = st.radio(
            "Modo",
            ["Exacta", "Parcial"],
            horizontal=True,
            index=0,
            key="modo_busqueda_input",
            label_visibility="collapsed"
        )

    # Fila 2: Filtros avanzados en expander
    with st.expander("⚙️ Filtros Avanzados", expanded=False):
        col_a1, col_a2, col_a3, col_a4 = st.columns(4)

        with col_a1:
            estado_filtro = st.multiselect(
                "Filtrar por estado",
                ["Serviciable", "No serviciable", "Contratado", "Incidencia", "No interesado", "No visitado"],
                default=["Serviciable", "No serviciable", "Contratado", "Incidencia", "No interesado", "No visitado"],
                key="estado_filtro_input"
            )

        with col_a2:
            mostrar_clusters = st.checkbox("Mostrar clusters", value=True, key="mostrar_clusters_input")

        with col_a3:
            mostrar_leyenda = st.checkbox("Mostrar leyenda en mapa", value=True, key="mostrar_leyenda_input")

        with col_a4:
            zoom_inicial = st.slider("Zoom inicial", 8, 18, 12, key="zoom_inicial_input")

    # ===== LÓGICA DE CARGA DE DATOS =====

    # Inicializar variables
    datos_filtrados = pd.DataFrame()
    comercial_filtradas = pd.DataFrame()
    dicts = {}

    # Opción 1: Búsqueda por ID
    if apartment_search:
        with st.spinner("🔍 Buscando apartment..."):
            if modo_busqueda == "Exacta":
                datos_uis, comercial_rafa_df = buscar_por_id(apartment_search)
                if not datos_uis.empty:
                    datos_filtrados = datos_uis
                    comercial_filtradas = comercial_rafa_df
                    st.success(f"✅ Encontrado: {apartment_search}")
                else:
                    st.error(f"❌ No se encontró el Apartment ID: {apartment_search}")
                    return
            else:
                # Búsqueda parcial - cargar datos limitados primero
                datos_uis, comercial_rafa_df = cargar_datos_limitados()
                mask = datos_uis['apartment_id'].astype(str).str.contains(apartment_search, case=False, na=False)
                datos_filtrados = datos_uis[mask]
                comercial_filtradas = comercial_rafa_df[
                    comercial_rafa_df['apartment_id'].isin(datos_filtrados['apartment_id'])]

                if datos_filtrados.empty:
                    st.warning(f"⚠️ No se encontraron coincidencias para: {apartment_search}")
                    # Mostrar vista limitada por defecto
                    datos_filtrados, comercial_filtradas = cargar_datos_limitados()
                else:
                    st.success(f"✅ Encontradas {len(datos_filtrados)} coincidencias")

    # Opción 2: Filtro por provincia
    elif provincia_sel != "Selecciona provincia":
        with st.spinner(f"⏳ Cargando datos de {provincia_sel}..."):
            datos_uis, comercial_rafa_df = cargar_datos_por_provincia(provincia_sel)

            if datos_uis.empty:
                st.warning(f"⚠️ No hay datos para {provincia_sel}")
                # Cargar vista limitada
                datos_filtrados, comercial_filtradas = cargar_datos_limitados()
            else:
                datos_filtrados = datos_uis
                comercial_filtradas = comercial_rafa_df

                # Filtros adicionales
                col_m1, col_m2 = st.columns(2)

                with col_m1:
                    if 'municipio' in datos_filtrados.columns:
                        municipios = ["Todos"] + sorted(datos_filtrados['municipio'].dropna().unique().tolist())
                        municipio_sel = st.selectbox("Municipio", municipios, key="select_municipio_input")

                        if municipio_sel and municipio_sel != "Todos":
                            datos_filtrados = datos_filtrados[datos_filtrados['municipio'] == municipio_sel]

                with col_m2:
                    if 'poblacion' in datos_filtrados.columns and 'municipio_sel' in locals() and municipio_sel != "Todos":
                        poblaciones = ["Todas"] + sorted(datos_filtrados['poblacion'].dropna().unique().tolist())
                        poblacion_sel = st.selectbox("Población", poblaciones, key="select_poblacion_input")

                        if poblacion_sel and poblacion_sel != "Todas":
                            datos_filtrados = datos_filtrados[datos_filtrados['poblacion'] == poblacion_sel]

    # Opción 3: Vista inicial (sin filtros)
    else:
        st.info("👆 Selecciona una provincia o busca por ID para cargar datos")

        # Cargar datos limitados para vista previa
        with st.spinner("⏳ Cargando vista previa..."):
            datos_filtrados, comercial_filtradas = cargar_datos_limitados()

            if not datos_filtrados.empty:
                st.success(f"✅ Vista previa cargada: {len(datos_filtrados)} apartments")

    # ===== VERIFICACIÓN Y PROCESAMIENTO DE DATOS =====

    if datos_filtrados.empty:
        st.warning("⚠️ No hay datos para mostrar. Prueba con otros filtros.")
        return

    # Crear diccionarios optimizados
    dicts = crear_diccionarios_optimizados(comercial_filtradas)

    # Aplicar filtros de estado si están activos
    if estado_filtro and len(estado_filtro) < 6:
        estados_permitidos = [estado.lower().replace(" ", "_") for estado in estado_filtro]

        # Calcular estado para cada fila
        estados = []
        for _, row in datos_filtrados.iterrows():
            apt_id = row['apartment_id']
            serv_uis = str(row.get('serviciable', '')).lower().strip() if 'serviciable' in row else ''
            _, estado = determinar_color_marcador(apt_id, serv_uis, dicts)
            estados.append(estado)

        # Filtrar por estado
        mask = [estado in estados_permitidos for estado in estados]
        datos_filtrados = datos_filtrados[mask].copy()

        # Actualizar datos comerciales
        if not datos_filtrados.empty:
            apt_ids = datos_filtrados['apartment_id'].tolist()
            comercial_filtradas = comercial_filtradas[comercial_filtradas['apartment_id'].isin(apt_ids)]
            dicts = crear_diccionarios_optimizados(comercial_filtradas)

    # ===== ESTADÍSTICAS =====
    if not datos_filtrados.empty:
        col_s1, col_s2, col_s3, col_s4 = st.columns(4)

        with col_s1:
            st.metric("Total Apartments", f"{len(datos_filtrados):,}")

        with col_s2:
            if not comercial_filtradas.empty:
                comerciales = comercial_filtradas['comercial'].nunique()
                st.metric("Comerciales", comerciales)

        with col_s3:
            # Contar serviciables
            serviciables = sum(1 for apt_id in datos_filtrados['apartment_id']
                               if dicts.get('serviciable', {}).get(apt_id) == 'sí')
            st.metric("Serviciables", serviciables)

        with col_s4:
            # Contar incidencias
            incidencias = sum(1 for apt_id in datos_filtrados['apartment_id']
                              if dicts.get('incidencia', {}).get(apt_id) == 'sí')
            st.metric("Incidencias", incidencias)

    # ===== CREACIÓN DEL MAPA =====

    if datos_filtrados.empty:
        st.warning("⚠️ No hay datos que cumplan los filtros seleccionados")
        return

    # Calcular centro del mapa
    if len(datos_filtrados) == 1:
        center_lat = float(datos_filtrados.iloc[0]['latitud'])
        center_lon = float(datos_filtrados.iloc[0]['longitud'])
        zoom_start = 16
    elif len(datos_filtrados) <= 10:
        center_lat = float(datos_filtrados['latitud'].mean())
        center_lon = float(datos_filtrados['longitud'].mean())
        zoom_start = 14
    else:
        center_lat = float(datos_filtrados['latitud'].mean())
        center_lon = float(datos_filtrados['longitud'].mean())
        zoom_start = zoom_inicial

    # Crear mapa
    with st.spinner("🗺️ Generando mapa..."):
        m = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=zoom_start,
            max_zoom=21,
            tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
            attr="Google Satellite",
            control_scale=True
        )

        # Añadir plugins
        if mostrar_clusters and len(datos_filtrados) > 10:
            cluster_layer = MarkerCluster(
                max_cluster_radius=80,
                min_cluster_size=2,
                disable_clustering_at_zoom=16
            ).add_to(m)
            layer = cluster_layer
        else:
            layer = m

        Geocoder(collapsed=True, position='topright').add_to(m)
        Fullscreen(position='topright').add_to(m)

        # Añadir leyenda al mapa si está activado
        if mostrar_leyenda:
            agregar_leyenda_al_mapa(m)

        # Manejar coordenadas duplicadas
        coord_counts = {}
        for _, row in datos_filtrados.iterrows():
            coord = (round(row['latitud'], 6), round(row['longitud'], 6))
            coord_counts[coord] = coord_counts.get(coord, 0) + 1

        # Añadir marcadores
        markers_added = 0
        for _, row in datos_filtrados.iterrows():
            apt_id = row['apartment_id']
            lat = float(row['latitud'])
            lon = float(row['longitud'])

            # Aplicar offset si hay duplicados
            coord_key = (round(lat, 6), round(lon, 6))
            if coord_counts.get(coord_key, 0) > 1:
                offset = coord_counts[coord_key] * 0.00002
                lat += offset
                lon -= offset
                coord_counts[coord_key] -= 1

            # Determinar color
            serv_uis = str(row.get('serviciable', '')).lower().strip() if 'serviciable' in row else ''
            color, estado = determinar_color_marcador(apt_id, serv_uis, dicts)

            # Crear popup
            popup_html = f"""
            <div style="font-family: Arial; max-width: 250px;">
                <div style="background: #2c3e50; color: white; padding: 8px; border-radius: 5px 5px 0 0;">
                    <strong>🏠 {apt_id}</strong>
                </div>
                <div style="padding: 10px;">
                    <div><strong>📍 Ubicación:</strong></div>
                    <div>{row.get('provincia', '')}</div>
                    <div>{row.get('municipio', '')} - {row.get('poblacion', '')}</div>
                    <div style="margin-top: 5px;">{row.get('vial', '')} {row.get('numero', '')}</div>
                    <div style="color: #666; font-size: 11px; margin-top: 5px;">
                        📍 {lat:.6f}, {lon:.6f}
                    </div>
            """

            # Añadir info comercial si existe
            if apt_id in dicts.get('comercial', {}) or apt_id in dicts.get('serviciable', {}):
                popup_html += '<hr style="margin: 10px 0;"><div><strong>👤 Datos:</strong></div>'

                if apt_id in dicts.get('comercial', {}):
                    popup_html += f"<div>Comercial: {dicts['comercial'][apt_id]}</div>"

                if apt_id in dicts.get('serviciable', {}):
                    serv_value = dicts['serviciable'][apt_id].title()
                    popup_html += f"<div>Serviciable: {serv_value}</div>"

            popup_html += "</div></div>"

            # Crear marcador
            folium.Marker(
                location=[lat, lon],
                popup=folium.Popup(popup_html, max_width=300),
                tooltip=f"🏠 {apt_id}",
                icon=folium.Icon(color=color, icon="home", prefix="fa")
            ).add_to(layer)

            markers_added += 1

            # Límite de rendimiento
            if markers_added >= 1000:
                st.warning("⚠️ Mostrando primeros 1000 puntos por rendimiento")
                break

        # Renderizar mapa
        map_data = st_folium(
            m,
            height=600,
            width='stretch',
            returned_objects=["last_object_clicked_tooltip", "bounds", "zoom"]
        )

        # Manejar clic en marcador
        if map_data and map_data.get("last_object_clicked_tooltip"):
            mostrar_info_detallada(
                map_data["last_object_clicked_tooltip"],
                datos_filtrados,
                comercial_filtradas,
                dicts
            )

    # ===== ACCIONES RÁPIDAS =====
    col_a1, col_a2, col_a3 = st.columns(3)

    with col_a1:
        if st.button("🔄 Actualizar Vista", width='stretch'):
            st.cache_data.clear()
            st.rerun()

    with col_a2:
        if st.button("📍 Ver Todos", width='stretch', key="ver_todos_btn"):
            # Limpiar caché y recargar para mostrar todos
            st.cache_data.clear()
            st.rerun()

    with col_a3:
        # Exportar datos
        if not datos_filtrados.empty:
            csv = datos_filtrados.to_csv(index=False, sep=';')
            st.download_button(
                label="📥 Exportar CSV",
                data=csv,
                file_name=f"mapa_{pd.Timestamp.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                width='stretch',
                key="exportar_csv_btn"
            )


# Funciones de compatibilidad
def limpiar_mapa():
    """Función placeholder para mantener compatibilidad"""
    pass


def cargar_datos_uis():
    """Función original para mantener compatibilidad"""
    return cargar_datos_limitados()


def mostrar_info_rapida(apartment_id: str, datos_filtrados: pd.DataFrame,
                        comercial_filtradas: pd.DataFrame, dicts: Dict):
    """Función original para mantener compatibilidad - usar mostrar_info_detallada en su lugar"""
    mostrar_info_detallada(apartment_id, datos_filtrados, comercial_filtradas, dicts)


def mostrar_info_apartamento(apartment_id, datos_df, comercial_rafa_df):
    """Función original para mantener compatibilidad - usar mostrar_info_detallada en su lugar"""
    dicts = crear_diccionarios_optimizados(comercial_rafa_df)
    mostrar_info_detallada(apartment_id, datos_df, comercial_rafa_df, dicts)


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
        st.toast(f"Error al actualizar la base de datos: {str(e)}")
        return False

def upload_file_to_cloudinary(file, public_id=None, folder=None):
    """
    Sube un archivo genérico (como Excel, PDF, ZIP...) a Cloudinary y devuelve la URL pública.
    Puedes especificar una carpeta opcional con el parámetro 'folder'.
    """
    try:
        upload_result = cloudinary.uploader.upload(
            file,
            resource_type="raw",  # ✅ Permite subir PDF, ZIP, etc.
            public_id=public_id,  # opcional, si quieres nombre personalizado
            folder=folder,        # 👈 Carpeta en Cloudinary (p.ej. "PRESUPUESTOS")
            overwrite=True
        )
        return upload_result.get("secure_url")
    except Exception as e:
        st.toast(f"❌ Error al subir el archivo a Cloudinary: {e}")
        return None

def viabilidades_seccion():
    # 🟩 Submenú horizontal
    sub_seccion = option_menu(
        menu_title=None,
        options=["Ver Viabilidades", "Crear Viabilidades"],
        icons=["map", "plus-circle"],
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
    # 🧩 Sección 1: Ver Viabilidades (tu código actual)
    if sub_seccion == "Ver Viabilidades":
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
                    st.toast("❌ La tabla 'viabilidades' no se encuentra en la base de datos.")
                    conn.close()
                    return

                viabilidades_df = pd.read_sql("SELECT * FROM viabilidades", conn)
                conn.close()

                if viabilidades_df.empty:
                    st.warning("⚠️ No hay viabilidades disponibles.")
                    return

            except Exception as e:
                st.toast(f"❌ Error al cargar los datos de la base de datos: {e}")
                return

        # Verificamos columnas necesarias
        for col in ['latitud', 'longitud', 'ticket']:
            if col not in viabilidades_df.columns:
                st.toast(f"❌ Falta la columna '{col}'.")
                return

        # Agregamos columna de duplicados
        viabilidades_df.loc[:, 'is_duplicate'] = viabilidades_df['apartment_id'].duplicated(keep=False)

        # ✅ CORRECCIÓN 2: Agregar columna que indica si tiene presupuesto asociado
        try:
            conn = obtener_conexion()
            presupuestos_df = pd.read_sql("SELECT DISTINCT ticket FROM presupuestos_viabilidades", conn)
            conn.close()
            # Usar .loc para una asignación segura
            viabilidades_df.loc[:, 'tiene_presupuesto'] = viabilidades_df['ticket'].isin(presupuestos_df['ticket'])
        except Exception as e:
            viabilidades_df.loc[:, 'tiene_presupuesto'] = False

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
            df_reordered = viabilidades_df[cols].copy()

            # Preparamos la configuración con filtros y anchos
            gb = GridOptionsBuilder.from_dataframe(df_reordered)
            gb.configure_default_column(
                filter=True,
                floatingFilter=True,
                sortable=True,
                resizable=True,
                minWidth=100,
                flex=1
            )

            # Resaltado de duplicados
            dup_ids = viabilidades_df.loc[viabilidades_df['is_duplicate'], 'apartment_id'].copy().unique().tolist()

            gb.configure_column(
                'apartment_id',
                cellStyle={
                    'function': f"""
                        function(params) {{
                            if (params.value && {dup_ids}.includes(params.value)) {{
                                return {{'backgroundColor': 'yellow', 'cursor': 'pointer'}};
                            }}
                            return {{'cursor': 'pointer'}};
                        }}
                    """
                },
                cellRenderer='''function(params) {
                    return `<a href="#" style="color:#00bfff;text-decoration:underline;">${params.value}</a>`;
                }'''
            )

            # Selección de fila única
            gb.configure_selection(selection_mode="single", use_checkbox=False)

            gridOptions = gb.build()

            # Fila en rojo si resultado = NO
            for col_def in gridOptions['columnDefs']:
                if col_def['field'] != 'apartment_id':
                    col_def['cellStyle'] = {
                        'function': """
                            function(params) {
                                if (params.data.resultado && params.data.resultado.toUpperCase() === 'NO') {
                                    return {'backgroundColor': 'red'};
                                }
                            }
                        """
                    }

            grid_response = AgGrid(
                df_reordered,
                gridOptions=gridOptions,
                enable_enterprise_modules=True,
                update_mode=GridUpdateMode.SELECTION_CHANGED,
                data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
                fit_columns_on_grid_load=False,
                height=400,
                theme='alpine-dark'
            )

            # ==============================
            # 🔍 Manejo robusto de selección
            # ==============================
            selected_rows = grid_response.get("selected_data", [])
            if isinstance(selected_rows, pd.DataFrame):
                selected_rows = selected_rows.to_dict(orient="records")

            if not isinstance(selected_rows, list):
                selected_rows = grid_response.get("selected_rows", [])

            if isinstance(selected_rows, pd.DataFrame):
                selected_rows = selected_rows.to_dict(orient="records")

            if selected_rows is None:
                selected_rows = []

            if isinstance(selected_rows, list) and len(selected_rows) > 0:
                row = selected_rows[0]
                ticket_key = next((k for k in row.keys() if k.lower().strip() == "ticket"), None)
                clicked_ticket = str(row.get(ticket_key, "")).strip() if ticket_key else ""

                if clicked_ticket and clicked_ticket != st.session_state.get("selected_ticket"):
                    st.session_state["selected_ticket"] = clicked_ticket
                    st.session_state["reload_form"] = True
                    st.rerun()

            # ==============================
            # Mostrar detalles del ticket
            # ==============================
            selected_viabilidad = None
            if st.session_state.get("selected_ticket"):
                ticket_str = str(st.session_state["selected_ticket"]).strip()
                mask = viabilidades_df["ticket"].astype(str).str.strip() == ticket_str
                filtered = viabilidades_df.loc[mask].copy()
                if not filtered.empty:
                    selected_viabilidad = filtered.iloc[0].copy()

            # ==============================
            # Exportar a Excel
            # ==============================
            df_export = viabilidades_df.copy()

            def expand_apartments(df):
                rows = []
                for _, row in df.iterrows():
                    ids = str(row.get("apartment_id", "")).split(",")
                    for apt in ids:
                        new_row = row.copy()
                        new_row["apartment_id"] = apt.strip()
                        rows.append(new_row)
                return pd.DataFrame(rows)

            df_export = expand_apartments(viabilidades_df)

            output = BytesIO()
            with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                df_export.to_excel(writer, index=False, sheet_name="Viabilidades")
            output.seek(0)

            col_b1, _, col_b2 = st.columns([1, 2.3, 1])

            with col_b1:
                if st.button("🔄 Actualizar"):
                    with st.spinner("🔄 Actualizando hoja de Google Sheets..."):
                        actualizar_google_sheet_desde_db(
                            sheet_id="14nC88hQoCdh6B6pTq7Ktu2k8HWOyS2BaTqcUOIhXuZY",
                            sheet_name="viabilidades_verde"
                        )

            with col_b2:
                st.download_button(
                    label="📥 Descargar Excel",
                    data=output,
                    file_name="viabilidades_export.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

        with col1:

            # ==============================
            # Función para dibujar el mapa
            # ==============================
            def draw_map(df, center, zoom, selected_ticket=None):
                m = folium.Map(location=center, zoom_start=zoom,
                               tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
                               attr="Google", min_zoom=4, max_zoom=20)
                marker_cluster = MarkerCluster().add_to(m)

                for _, row in df.iterrows():
                    ticket = str(row['ticket']).strip()
                    lat, lon = row['latitud'], row['longitud']

                    popup = f"""
                        <b>🏠 Ticket:</b> {ticket}<br>
                        📍 {lat:.6f}, {lon:.6f}<br>
                        <b>Cliente:</b> {row.get('nombre_cliente', 'N/D')}<br>
                        <b>Serviciable:</b> {row.get('serviciable', 'N/D')}<br>
                    """

                    serviciable = str(row.get('serviciable', '')).strip()
                    apartment_id = str(row.get('apartment_id', '')).strip()
                    tiene_presupuesto = row.get('tiene_presupuesto', False)

                    # Color por estado
                    if tiene_presupuesto:
                        marker_color = 'orange'
                    elif row.get('estado') == "No interesado":
                        marker_color = 'black'
                    elif row.get('estado') == "Incidencia":
                        marker_color = 'purple'
                    elif serviciable == "No":
                        marker_color = 'red'
                    elif serviciable == "Sí" and apartment_id not in ["", "N/D"]:
                        marker_color = 'green'
                    else:
                        marker_color = 'blue'

                    # Si es el ticket seleccionado, resaltamos en dorado
                    if selected_ticket and ticket == str(selected_ticket).strip():
                        folium.Marker(
                            location=[lat, lon],
                            popup=popup + "<b>🎯 Ticket seleccionado</b>",
                            icon=folium.Icon(icon='star')
                        ).add_to(m)
                    else:
                        folium.Marker(
                            location=[lat, lon],
                            popup=popup,
                            tooltip=f"{ticket}",
                            icon=folium.Icon(color=marker_color, icon='info-sign')
                        ).add_to(marker_cluster)

                return m

            # ==============================
            # Determinar centro y zoom
            # ==============================
            if st.session_state.get("selected_ticket"):
                ticket_str = str(st.session_state["selected_ticket"]).strip()
                df_sel = viabilidades_df.loc[viabilidades_df["ticket"].astype(str).str.strip() == ticket_str]
                if not df_sel.empty:
                    center = [df_sel.iloc[0]["latitud"], df_sel.iloc[0]["longitud"]]
                    zoom = 16
                else:
                    center = st.session_state.get("map_center", [40.0, -3.7])
                    zoom = st.session_state.get("map_zoom", 6)
            else:
                center = st.session_state.get("map_center", [40.0, -3.7])
                zoom = st.session_state.get("map_zoom", 6)

            # ==============================
            # Dibujar mapa
            # ==============================
            m_to_show = draw_map(
                viabilidades_df,
                center=center,
                zoom=zoom,
                selected_ticket=st.session_state.get("selected_ticket")
            )

            # ==============================
            # Leyenda
            # ==============================
            legend = """
            {% macro html(this, kwargs) %}
            <div style="
                position: fixed; 
                bottom: 0px; left: 0px; width: 170px; 
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
            <i style="color:gold;">★</i> Ticket seleccionado<br>
            </div>
            {% endmacro %}
            """
            macro = MacroElement()
            macro._template = Template(legend)
            m_to_show.get_root().add_child(macro)
            Geocoder().add_to(m_to_show)

            # ==============================
            # Mostrar mapa y detectar clic
            # ==============================
            map_output = st_folium(
                m_to_show,
                height=500,
                width=700,
                key="main_map",
                returned_objects=["last_object_clicked"]
            )

            # ==============================
            # Detectar clic del mapa
            # ==============================
            if map_output and map_output.get("last_object_clicked"):
                clicked_lat = map_output["last_object_clicked"]["lat"]
                clicked_lng = map_output["last_object_clicked"]["lng"]

                tolerance = 0.0001  # ~11 m
                match = viabilidades_df[
                    (viabilidades_df["latitud"].between(clicked_lat - tolerance, clicked_lat + tolerance)) &
                    (viabilidades_df["longitud"].between(clicked_lng - tolerance, clicked_lng + tolerance))
                    ]

                if not match.empty:
                    clicked_ticket = str(match.iloc[0]["ticket"]).strip()

                    if clicked_ticket != st.session_state.get("selected_ticket"):
                        st.session_state["selected_ticket"] = clicked_ticket
                        st.session_state["map_center"] = [clicked_lat, clicked_lng]
                        st.session_state["map_zoom"] = 16
                        st.session_state["selection_source"] = "map"

                        st.toast(f"📍 Ticket {clicked_ticket} seleccionado desde el mapa")

                        # Forzar recarga
                        st.rerun()

            # ==============================
            # Si venimos del mapa, limpiamos selección de tabla
            # ==============================
            if st.session_state.get("selection_source") == "map":
                st.session_state["selection_source"] = None
                st.session_state["last_table_selection"] = None

        # Mostrar formulario debajo
        if st.session_state["selected_ticket"]:
            mostrar_formulario(selected_viabilidad)

            if st.session_state.get("selected_ticket"):
                archivo = st.file_uploader(
                    f"📁 Sube el archivo PDF del presupuesto para Ticket {st.session_state['selected_ticket']}",
                    type=["pdf"]
                )

                if archivo:
                    st.toast("✅ Archivo PDF cargado correctamente.")

                    proyecto = st.text_input(
                        "🔖 Proyecto / Nombre del presupuesto",
                        value=f"Ticket {st.session_state['selected_ticket']}"
                    )
                    mensaje = st.text_area(
                        "📝 Mensaje para los destinatarios",
                        value="Adjunto presupuesto en formato PDF para su revisión."
                    )

                    # Define los destinatarios disponibles
                    destinatarios_posibles = {
                        "Rafa Sanz": "rafasanz9@gmail.com",
                        "Juan AsturPhone": "admin@asturphone.com",
                        "Correo para pruebas": "patricia@verdetuoperador.com",
                        "Juan Pablo": "jpterrel@verdetuoperador.com"
                    }

                    seleccionados = st.multiselect("👥 Selecciona destinatarios", list(destinatarios_posibles.keys()))

                    if seleccionados and st.button("🚀 Enviar presupuesto en PDF por correo"):
                        try:
                            nombre_archivo = archivo.name
                            archivo_bytes = archivo.getvalue()  # Leer bytes del PDF

                            # 📂 Subir a la carpeta "PRESUPUESTOS" en Cloudinary

                            # 🔹 Subir PDF a Cloudinary (como tipo raw)
                            st.toast("📤 Subiendo PDF a Cloudinary...")
                            cloudinary_url = upload_file_to_cloudinary(
                                io.BytesIO(archivo_bytes),
                                public_id=nombre_archivo,  # solo el nombre del archivo
                                folder="PRESUPUESTOS"  # 👈 ahora Cloudinary lo organiza correctamente
                            )

                            if not cloudinary_url:
                                st.toast("❌ Error al subir el archivo a Cloudinary. No se puede continuar.")
                                st.stop()

                            # 🔹 Enviar correo a los seleccionados
                            for nombre in seleccionados:
                                correo = destinatarios_posibles[nombre]

                                correo_envio_presupuesto_manual(
                                    destinatario=correo,
                                    proyecto=proyecto,
                                    mensaje_usuario=mensaje,
                                    archivo_bytes=archivo_bytes,
                                    nombre_archivo=nombre_archivo
                                )

                                # 🔹 Registrar el envío en la base de datos con URL
                                try:
                                    conn = obtener_conexion()
                                    cursor = conn.cursor()
                                    cursor.execute("""
                                        INSERT INTO envios_presupuesto_viabilidad 
                                        (ticket, destinatario, proyecto, fecha_envio, archivo_nombre, archivo_url)
                                        VALUES (?, ?, ?, ?, ?, ?)
                                    """, (
                                        st.session_state["selected_ticket"],
                                        correo,
                                        proyecto,
                                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                        nombre_archivo,
                                        cloudinary_url
                                    ))
                                    conn.commit()
                                    conn.close()
                                except Exception as db_error:
                                    st.toast(
                                        f"⚠️ Correo enviado a {correo}, pero no se pudo registrar en la BBDD: {db_error}"
                                    )

                            # 🔹 Marcar en la tabla viabilidades que se ha enviado
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
                                st.toast("🗂️ Se ha registrado en la BBDD que el presupuesto en PDF ha sido enviado.")
                            except Exception as db_error:
                                st.toast(
                                    f"⚠️ El correo fue enviado, pero hubo un error al actualizar la BBDD: {db_error}"
                                )

                            st.toast("✅ Presupuesto en PDF enviado y guardado correctamente en Cloudinary.")
                        except Exception as e:
                            st.toast(f"❌ Error al enviar o guardar el presupuesto PDF: {e}")

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
                    st.dataframe(df_historial, width='stretch')

            except Exception as e:
                st.toast(f"❌ Error al cargar el historial de envíos: {e}")

        # 🧩 Sección 2: Crear Viabilidades (vacía por ahora)
    elif sub_seccion == "Crear Viabilidades":
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
            lat, lon, ticket, serviciable, apartment_id, direccion_id = v

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

        # 🔹 Añadir la leyenda flotante
        # Crear un figure para que FloatImage funcione bien
        legend = """
        {% macro html(this, kwargs) %}
        <div style="
            position: fixed; 
            bottom: 0px; left: 0px; width: 150px; 
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
        m.get_root().add_child(macro)

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
                col12, col13 = st.columns(2)
                # Conexión para cargar los OLT desde la tabla
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT id_olt, nombre_olt FROM olt ORDER BY nombre_olt")
                olts = cursor.fetchall()
                conn.close()

                # Diccionario con clave 'id. nombre' y valor (id, nombre)
                opciones_olt = {f"{fila[0]}. {fila[1]}": fila for fila in olts}

                with col12:
                    opcion_olt = st.selectbox("🏢 OLT", options=list(opciones_olt.keys()))
                    id_olt, nombre_olt = opciones_olt[opcion_olt]
                with col13:
                    apartment_id = st.text_input("🏘️ Apartment ID")
                comentario = st.text_area("📝 Comentario")

                # ✅ Campo para seleccionar el comercial
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT username FROM usuarios ORDER BY username")
                lista_usuarios = [fila[0] for fila in cursor.fetchall()]
                conn.close()

                # Lista de usuarios a excluir
                excluir = ["roberto", "nestor", "rafaela"]

                # Filtrar la lista
                usuarios_filtrados = [u for u in lista_usuarios if u.lower() not in excluir]

                # Agregar opción vacía al inicio y usar index=0 para selección por defecto
                usuarios_con_opcion_vacia = [""] + usuarios_filtrados
                comercial = st.selectbox("🧑‍💼 Comercial responsable *",
                                         options=usuarios_con_opcion_vacia,
                                         placeholder="Selecciona un comercial...",
                                         index=None,
                                         help="Selecciona un comercial responsable. Este campo es obligatorio.")

                submit = st.form_submit_button("Enviar Formulario")

                if submit:
                    # Validar que se haya seleccionado un comercial
                    if not comercial or comercial == "":
                        st.error("❌ Por favor, selecciona un comercial responsable. Este campo es obligatorio.")
                        st.stop()  # Detiene la ejecución para evitar guardar datos incompletos

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
                        f"{id_olt}. {nombre_olt}",  # nuevo campo
                        apartment_id  # nuevo campo
                    ))

                    st.toast(f"✅ Viabilidad guardada correctamente.\n\n📌 **Ticket:** `{ticket}`")

                    # Resetear marcador para permitir nuevas viabilidades
                    st.session_state.viabilidad_marker = None
                    st.session_state.map_center = (43.463444, -3.790476)  # Vuelve a la ubicación inicial
                    st.rerun()

# Función para obtener conexión a la base de datos (SQLite Cloud)
def get_db_connection():
    return sqlitecloud.connect(
        "sqlitecloud://ceafu04onz.g6.sqlite.cloud:8860/usuarios.db?apikey=Qo9m18B9ONpfEGYngUKm99QB5bgzUTGtK7iAcThmwvY"
    )

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

    # Obtener email del comercial seleccionado
    comercial_email = None
    cursor.execute("SELECT email FROM usuarios WHERE username = ?", (datos[13],))
    fila = cursor.fetchone()
    if fila:
        comercial_email = fila[0]

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
        st.toast("⚠️ No se encontró ningún email de administrador, no se pudo enviar la notificación.")

    # Enviar notificación al comercial seleccionado
    if comercial_email:
        correo_viabilidad_comercial(comercial_email, ticket_id, descripcion_viabilidad)
        st.toast(
            f"📧 Se ha enviado una notificación al comercial responsable: {nombre_comercial} ({comercial_email})")
    else:
        st.toast(f"⚠️ No se pudo encontrar el email del comercial {nombre_comercial}.")

    # Mostrar mensaje de éxito en Streamlit
    st.toast("✅ Los cambios para la viabilidad han sido guardados correctamente")

# Función para obtener viabilidades guardadas en la base de datos
def obtener_viabilidades():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT latitud, longitud, ticket, serviciable, apartment_id, direccion_id 
        FROM viabilidades
    """)
    viabilidades = cursor.fetchall()
    conn.close()
    return viabilidades


def mostrar_formulario(click_data):
    """Muestra el formulario para editar los datos de la viabilidad y guarda los cambios en la base de datos."""

    # DEBUG: Verificar qué datos estamos recibiendo
    st.sidebar.write("🔍 DATOS RECIBIDOS:")
    st.sidebar.write(f"Ticket: {click_data.get('ticket', 'NO ENCONTRADO')}")
    st.sidebar.write(f"Municipio: {click_data.get('municipio', 'NO ENCONTRADO')}")
    st.sidebar.write(f"OLT: {click_data.get('olt', 'NO ENCONTRADO')}")

    # Obtener valores de la tabla OLT
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("SELECT id_olt, nombre_olt FROM olt ORDER BY id_olt ASC")
    olts = cursor.fetchall()
    conn.close()

    # Preparar opciones del selectbox: se mostrará "id_olt - nombre_olt"
    opciones_olt = [f"{olt[0]} - {olt[1]}" for olt in olts]

    # Extraer los datos del registro seleccionado
    ticket = click_data["ticket"]

    # Inicializar session_state para este ticket si no existe
    if f"form_data_{ticket}" not in st.session_state:
        st.session_state[f"form_data_{ticket}"] = {
            "latitud": click_data.get("latitud", ""),
            "longitud": click_data.get("longitud", ""),
            "provincia": click_data.get("provincia", ""),
            "municipio": click_data.get("municipio", ""),
            "poblacion": click_data.get("poblacion", ""),
            "vial": click_data.get("vial", ""),
            "numero": click_data.get("numero", ""),
            "letra": click_data.get("letra", ""),
            "cp": click_data.get("cp", ""),
            "comentario": click_data.get("comentario", ""),
            "cto_cercana": click_data.get("cto_cercana", ""),
            "olt": click_data.get("olt", ""),
            "cto_admin": click_data.get("cto_admin", ""),
            "id_cto": click_data.get("id_cto", ""),
            "municipio_admin": click_data.get("municipio_admin", ""),
            "serviciable": click_data.get("serviciable", "Sí"),
            "coste": float(click_data.get("coste", 0.0)),
            "comentarios_comercial": click_data.get("comentarios_comercial", ""),
            "comentarios_internos": click_data.get("comentarios_internos", ""),
            "fecha_viabilidad": click_data.get("fecha_viabilidad", ""),
            "apartment_id": click_data.get("apartment_id", ""),
            "nombre_cliente": click_data.get("nombre_cliente", ""),
            "telefono": click_data.get("telefono", ""),
            "usuario": click_data.get("usuario", ""),
            "direccion_id": click_data.get("direccion_id", ""),
            "confirmacion_rafa": click_data.get("confirmacion_rafa", ""),
            "zona_estudio": click_data.get("zona_estudio", ""),
            "estado": click_data.get("estado", "Sin estado"),
            "presupuesto_enviado": click_data.get("presupuesto_enviado", ""),
            "nuevapromocion": click_data.get("nuevapromocion", "NO"),
            "resultado": click_data.get("resultado", "NO"),
            "justificacion": click_data.get("justificacion", "SIN JUSTIFICACIÓN"),
            "contratos": click_data.get("contratos", ""),
            "respuesta_comercial": click_data.get("respuesta_comercial", ""),
            "comentarios_gestor": click_data.get("comentarios_gestor", "")
        }

    # Obtener datos actuales del formulario
    form_data = st.session_state[f"form_data_{ticket}"]

    # Función para actualizar valores en session_state
    def update_form_data(field, value):
        st.session_state[f"form_data_{ticket}"][field] = value

    with st.form(key=f"form_viabilidad_{ticket}"):
        st.subheader(f"✏️ Editar Viabilidad - Ticket {ticket}")

        # --- UBICACIÓN ---
        col1, col2, col3 = st.columns(3)
        with col1:
            st.text_input("🎟️ Ticket", value=ticket, disabled=True, key=f"ticket_{ticket}")
        with col2:
            latitud = st.text_input("📍 Latitud", value=form_data["latitud"],
                                    key=f"latitud_{ticket}")
            if latitud != form_data["latitud"]:
                update_form_data("latitud", latitud)
        with col3:
            longitud = st.text_input("📍 Longitud", value=form_data["longitud"],
                                     key=f"longitud_{ticket}")
            if longitud != form_data["longitud"]:
                update_form_data("longitud", longitud)

        col4, col5, col6 = st.columns(3)
        with col4:
            provincia = st.text_input("🏠 Provincia", value=form_data["provincia"],
                                      key=f"provincia_{ticket}")
            if provincia != form_data["provincia"]:
                update_form_data("provincia", provincia)
        with col5:
            municipio = st.text_input("🏙️ Municipio", value=form_data["municipio"],
                                      key=f"municipio_{ticket}")
            if municipio != form_data["municipio"]:
                update_form_data("municipio", municipio)
        with col6:
            poblacion = st.text_input("👥 Población", value=form_data["poblacion"],
                                      key=f"poblacion_{ticket}")
            if poblacion != form_data["poblacion"]:
                update_form_data("poblacion", poblacion)

        col7, col8, col9, col10 = st.columns([2, 1, 1, 1])
        with col7:
            vial = st.text_input("🚦 Vial", value=form_data["vial"],
                                 key=f"vial_{ticket}")
            if vial != form_data["vial"]:
                update_form_data("vial", vial)
        with col8:
            numero = st.text_input("🔢 Número", value=form_data["numero"],
                                   key=f"numero_{ticket}")
            if numero != form_data["numero"]:
                update_form_data("numero", numero)
        with col9:
            letra = st.text_input("🔠 Letra", value=form_data["letra"],
                                  key=f"letra_{ticket}")
            if letra != form_data["letra"]:
                update_form_data("letra", letra)
        with col10:
            cp = st.text_input("📮 Código Postal", value=form_data["cp"],
                               key=f"cp_{ticket}")
            if cp != form_data["cp"]:
                update_form_data("cp", cp)

        comentario = st.text_area("💬 Comentarios", value=form_data["comentario"],
                                  key=f"comentario_{ticket}")
        if comentario != form_data["comentario"]:
            update_form_data("comentario", comentario)

        # --- CONTACTO ---
        colc1, colc2, colc3 = st.columns(3)
        with colc1:
            nombre_cliente = st.text_input("👤 Nombre Cliente", value=form_data["nombre_cliente"],
                                           key=f"nombre_cliente_{ticket}")
            if nombre_cliente != form_data["nombre_cliente"]:
                update_form_data("nombre_cliente", nombre_cliente)
        with colc2:
            telefono = st.text_input("📞 Teléfono", value=form_data["telefono"],
                                     key=f"telefono_{ticket}")
            if telefono != form_data["telefono"]:
                update_form_data("telefono", telefono)
        with colc3:
            # --- Obtener lista de comerciales desde la base de datos ---
            try:
                conn = obtener_conexion()
                cursor = conn.cursor()
                cursor.execute("SELECT DISTINCT usuario FROM viabilidades WHERE usuario IS NOT NULL AND usuario != ''")
                comerciales = [row[0] for row in cursor.fetchall()]
                conn.close()
            except Exception as e:
                st.toast(f"Error al cargar comerciales: {e}")
                comerciales = []

            # Añadir el valor actual si no está en la lista
            if form_data["usuario"] and form_data["usuario"] not in comerciales:
                comerciales.append(form_data["usuario"])

            comerciales = sorted(comerciales)  # ordenar alfabéticamente

            # --- Mostrar selectbox con comercial actual seleccionado ---
            if comerciales:
                index_actual = comerciales.index(form_data["usuario"]) if form_data["usuario"] in comerciales else 0
                usuario = st.selectbox("👤 Comercial", comerciales, index=index_actual, key=f"usuario_{ticket}")
            else:
                usuario = st.text_input("👤 Comercial", value=form_data["usuario"], key=f"usuario_{ticket}")

            if usuario != form_data["usuario"]:
                update_form_data("usuario", usuario)

        # --- FECHAS Y CTO ---
        colf1, colf2 = st.columns(2)
        with colf1:
            st.text_input("📅 Fecha Viabilidad", value=form_data["fecha_viabilidad"],
                          disabled=True, key=f"fecha_viabilidad_{ticket}")
        with colf2:
            cto_cercana = st.text_input("🔌 CTO Cercana", value=form_data["cto_cercana"],
                                        key=f"cto_cercana_{ticket}")
            if cto_cercana != form_data["cto_cercana"]:
                update_form_data("cto_cercana", cto_cercana)

        # --- APARTAMENTO / DIRECCIÓN / OLT ---
        col11, col12, col13 = st.columns(3)
        with col11:
            apartment_id = st.text_area("🏠 Apartment IDs", value=form_data["apartment_id"],
                                        key=f"apartment_id_{ticket}")
            if apartment_id != form_data["apartment_id"]:
                update_form_data("apartment_id", apartment_id)
        with col12:
            direccion_id = st.text_input("📍 Dirección ID", value=form_data["direccion_id"],
                                         key=f"direccion_id_{ticket}")
            if direccion_id != form_data["direccion_id"]:
                update_form_data("direccion_id", direccion_id)
        with col13:
            olt_guardado = str(form_data["olt"]) if form_data["olt"] else ""
            indice_default = 0

            def normalizar_id(olt_value):
                # Toma solo la parte antes de "-" o "."
                return str(olt_value).split("-")[0].split(".")[0].strip().upper()

            olt_guardado_norm = normalizar_id(olt_guardado)

            # Buscar cuál de las opciones tiene ese mismo ID
            for i, opcion in enumerate(opciones_olt):
                id_opcion = normalizar_id(opcion)
                if id_opcion == olt_guardado_norm:
                    indice_default = i
                    break

            # Selectbox para seleccionar la OLT
            olt_seleccionado = st.selectbox("⚡ OLT", opciones_olt, index=indice_default, key=f"olt_{ticket}")

            # 🟢 Guardar el texto completo (id - nombre)
            update_form_data("olt", olt_seleccionado)

        # --- ADMINISTRACIÓN CTO ---
        col14, col15, col16 = st.columns(3)
        with col14:
            cto_admin = st.text_input("⚙️ CTO Admin", value=form_data["cto_admin"],
                                      key=f"cto_admin_{ticket}")
            if cto_admin != form_data["cto_admin"]:
                update_form_data("cto_admin", cto_admin)
        with col15:
            municipio_admin = st.text_input("🌍 Municipio Admin", value=form_data["municipio_admin"],
                                            key=f"municipio_admin_{ticket}")
            if municipio_admin != form_data["municipio_admin"]:
                update_form_data("municipio_admin", municipio_admin)
        with col16:
            id_cto = st.text_input("🔧 ID CTO", value=form_data["id_cto"],
                                   key=f"id_cto_{ticket}")
            if id_cto != form_data["id_cto"]:
                update_form_data("id_cto", id_cto)

        # --- ESTADO Y VIABILIDAD ---
        col17, col18, col19, col20 = st.columns([1, 1, 1, 1])
        with col17:
            serviciable_index = 0 if str(form_data["serviciable"]).upper() in ["SÍ", "SI", "S", "YES", "TRUE",
                                                                               "1"] else 1
            serviciable = st.selectbox("🔍 Serviciable", ["Sí", "No"],
                                       index=serviciable_index,
                                       key=f"serviciable_{ticket}")
            if serviciable != form_data["serviciable"]:
                update_form_data("serviciable", serviciable)
        with col18:
            coste = st.number_input(
                "💰 Coste (sin IVA)",
                value=float(form_data["coste"]),
                step=0.01,
                key=f"coste_{ticket}"
            )
            if coste != form_data["coste"]:
                update_form_data("coste", coste)
        with col19:
            coste_con_iva = round(float(form_data["coste"]) * 1.21, 2)
            st.text_input("💰 Coste con IVA 21%", value=f"{coste_con_iva:.2f}",
                          disabled=True, key=f"coste_iva_{ticket}")
        with col20:
            presupuesto_enviado = st.text_input("📤 Presupuesto Enviado",
                                                value=form_data["presupuesto_enviado"],
                                                key=f"presupuesto_enviado_{ticket}")
            if presupuesto_enviado != form_data["presupuesto_enviado"]:
                update_form_data("presupuesto_enviado", presupuesto_enviado)

        # --- COMENTARIOS ---
        comentarios_comercial = st.text_area("📝 Comentarios Comerciales",
                                             value=form_data["comentarios_comercial"],
                                             key=f"comentarios_comercial_{ticket}")
        if comentarios_comercial != form_data["comentarios_comercial"]:
            update_form_data("comentarios_comercial", comentarios_comercial)

        comentarios_internos = st.text_area("📄 Comentarios Internos",
                                            value=form_data["comentarios_internos"],
                                            key=f"comentarios_internos_{ticket}")
        if comentarios_internos != form_data["comentarios_internos"]:
            update_form_data("comentarios_internos", comentarios_internos)

        comentarios_gestor = st.text_area("🗒️ Comentarios Gestor",
                                          value=form_data["comentarios_gestor"],
                                          key=f"comentarios_gestor_{ticket}")
        if comentarios_gestor != form_data["comentarios_gestor"]:
            update_form_data("comentarios_gestor", comentarios_gestor)

        # --- OTROS CAMPOS ---
        col20, col21, col22 = st.columns(3)
        with col20:
            confirmacion_rafa = st.text_input("📍 Confirmación Rafa",
                                              value=form_data["confirmacion_rafa"],
                                              key=f"confirmacion_rafa_{ticket}")
            if confirmacion_rafa != form_data["confirmacion_rafa"]:
                update_form_data("confirmacion_rafa", confirmacion_rafa)
        with col21:
            zona_estudio = st.text_input("🗺️ Zona de Estudio",
                                         value=form_data["zona_estudio"],
                                         key=f"zona_estudio_{ticket}")
            if zona_estudio != form_data["zona_estudio"]:
                update_form_data("zona_estudio", zona_estudio)
        with col22:
            estado = st.text_input("📌 Estado", value=form_data["estado"],
                                   key=f"estado_{ticket}")
            if estado != form_data["estado"]:
                update_form_data("estado", estado)

        col23, col24, col25 = st.columns(3)
        with col23:
            nueva_promocion_index = 0 if str(form_data["nuevapromocion"]).upper() == "SI" else 1
            nueva_promocion = st.selectbox("🏗️ Nueva Promoción", ["SI", "NO"],
                                           index=nueva_promocion_index,
                                           key=f"nueva_promocion_{ticket}")
            if nueva_promocion != form_data["nuevapromocion"]:
                update_form_data("nuevapromocion", nueva_promocion)
        with col24:
            opciones_resultado = ["NO", "OK", "PDTE. INFORMACION", "SERVICIADO", "SOBRECOSTE"]
            resultado_index = opciones_resultado.index(form_data["resultado"]) if form_data[
                                                                                      "resultado"] in opciones_resultado else 0
            resultado = st.selectbox("✅ Resultado", opciones_resultado,
                                     index=resultado_index,
                                     key=f"resultado_{ticket}")
            if resultado != form_data["resultado"]:
                update_form_data("resultado", resultado)
        with col25:
            opciones_justificacion = ["SIN JUSTIFICACIÓN", "ZONA SUBVENCIONADA", "INVIABLE", "MAS PREVENTA",
                                      "RESERVADA WHL", "PDTE. FIN DE OBRA", "NO ES UNA VIABILIDAD"]
            justificacion_index = opciones_justificacion.index(form_data["justificacion"]) if form_data[
                                                                                                  "justificacion"] in opciones_justificacion else 0
            justificacion = st.selectbox("📌 Justificación", opciones_justificacion,
                                         index=justificacion_index,
                                         key=f"justificacion_{ticket}")
            if justificacion != form_data["justificacion"]:
                update_form_data("justificacion", justificacion)

        contratos = st.text_input("📑 Contratos", value=form_data["contratos"],
                                  key=f"contratos_{ticket}")
        if contratos != form_data["contratos"]:
            update_form_data("contratos", contratos)

        respuesta_comercial = st.text_input("📨 Respuesta Comercial",
                                            value=form_data["respuesta_comercial"],
                                            key=f"respuesta_comercial_{ticket}")
        if respuesta_comercial != form_data["respuesta_comercial"]:
            update_form_data("respuesta_comercial", respuesta_comercial)

        submit = st.form_submit_button("💾 Guardar cambios")

    if submit:
        try:
            # ============================================
            # 1. VALIDACIÓN DE CAMPOS OBLIGATORIOS
            # ============================================
            campos_obligatorios = [
                ("cto_admin", "CTO Admin"),
                ("id_cto", "ID CTO"),
                ("serviciable", "Serviciable"),
                ("resultado", "Resultado"),
                ("justificacion", "Justificación")
            ]

            campos_faltantes = []
            current_data = st.session_state[f"form_data_{ticket}"]

            for campo_key, campo_nombre in campos_obligatorios:
                if not current_data.get(campo_key) or str(current_data[campo_key]).strip() == "":
                    campos_faltantes.append(campo_nombre)

            if campos_faltantes:
                st.error(f"❌ Campos obligatorios faltantes: {', '.join(campos_faltantes)}")
                st.stop()

            # ============================================
            # 2. CONEXIÓN A BASE DE DATOS Y ACTUALIZACIÓN
            # ============================================
            conn = obtener_conexion()
            cursor = conn.cursor()

            # Limpiar apartment_id
            apartment_id_clean = ",".join(
                [aid.strip() for aid in (current_data["apartment_id"] or "").split(",") if aid.strip()]
            )

            # Actualización completa de la viabilidad
            cursor.execute("""
                UPDATE viabilidades SET
                    latitud=?, longitud=?, provincia=?, municipio=?, poblacion=?, vial=?, numero=?, letra=?, cp=?, comentario=?,
                    cto_cercana=?, olt=?, cto_admin=?, id_cto=?, municipio_admin=?, serviciable=?, coste=?, comentarios_comercial=?, 
                    comentarios_internos=?, fecha_viabilidad=?, apartment_id=?, nombre_cliente=?, telefono=?, usuario=?, 
                    direccion_id=?, confirmacion_rafa=?, zona_estudio=?, estado=?, presupuesto_enviado=?, nuevapromocion=?, 
                    resultado=?, justificacion=?, contratos=?, respuesta_comercial=?, comentarios_gestor=?
                WHERE ticket=?
            """, (
                current_data["latitud"],
                current_data["longitud"],
                current_data["provincia"],
                current_data["municipio"],
                current_data["poblacion"],
                current_data["vial"],
                current_data["numero"],
                current_data["letra"],
                current_data["cp"],
                current_data["comentario"],
                current_data["cto_cercana"],
                current_data["olt"],
                current_data["cto_admin"],
                current_data["id_cto"],
                current_data["municipio_admin"],
                current_data["serviciable"],
                current_data["coste"],
                current_data["comentarios_comercial"],
                current_data["comentarios_internos"],
                current_data["fecha_viabilidad"],
                apartment_id_clean,
                current_data["nombre_cliente"],
                current_data["telefono"],
                current_data["usuario"],
                current_data["direccion_id"],
                current_data["confirmacion_rafa"],
                current_data["zona_estudio"],
                current_data["estado"],
                current_data["presupuesto_enviado"],
                current_data["nuevapromocion"],
                current_data["resultado"],
                current_data["justificacion"],
                current_data["contratos"],
                current_data["respuesta_comercial"],
                current_data["comentarios_gestor"],
                ticket
            ))

            conn.commit()

            # ============================================
            # 3. ENVIAR NOTIFICACIÓN AL COMERCIAL ASIGNADO (SIN REGISTRO EN BD)
            # ============================================
            try:
                # Verificar si hay un comercial asignado
                comercial_asignado = current_data["usuario"]

                if comercial_asignado and comercial_asignado.strip():
                    # Obtener el email del comercial desde la tabla usuarios
                    cursor.execute("SELECT email FROM usuarios WHERE username = ?", (comercial_asignado,))
                    row = cursor.fetchone()
                    correo_comercial = row[0] if row else None

                    if correo_comercial:
                        # Importar la función de notificaciones
                        try:
                            from notificaciones import correo_respuesta_comercial

                            # Preparar el comentario para la notificación
                            comentario_notificacion = (
                                    current_data.get("respuesta_comercial") or
                                    current_data.get("comentarios_comercial") or
                                    f"""
                                <strong>Actualización de viabilidad - Ticket {ticket}</strong><br><br>
                                <strong>Resultado:</strong> {current_data.get('resultado', 'N/A')}<br>
                                <strong>Serviciable:</strong> {current_data.get('serviciable', 'N/A')}<br>
                                <strong>Estado:</strong> {current_data.get('estado', 'N/A')}<br>
                                <strong>Comentarios:</strong> {current_data.get('comentarios_comercial', 'Sin comentarios')}
                                """
                            )

                            # Enviar correo de notificación al comercial
                            correo_respuesta_comercial(
                                destinatario=correo_comercial,
                                ticket_id=ticket,
                                nombre_comercial=comercial_asignado,
                                comentario=comentario_notificacion
                            )

                            st.toast(f"📧 Notificación enviada al comercial {comercial_asignado}")

                        except ImportError:
                            st.toast("⚠️ Módulo 'notificaciones' no encontrado. La notificación no se envió.")
                    else:
                        st.toast(f"⚠️ No se encontró el correo del comercial {comercial_asignado}")
                else:
                    st.toast("ℹ️ No hay comercial asignado para notificar")
            except Exception as e:
                st.toast(f"⚠️ Error al enviar notificación: {str(e)}")
                # Continuar con el flujo aunque falle la notificación

            conn.close()

            # ============================================
            # 4. MENSAJE DE CONFIRMACIÓN Y LIMPIEZA
            # ============================================
            st.success(f"✅ Cambios guardados correctamente para el ticket {ticket}")

            # Limpiar el session_state para forzar recarga de datos
            if f"form_data_{ticket}" in st.session_state:
                del st.session_state[f"form_data_{ticket}"]

            # Añadir pequeño delay visual antes del rerun
            import time
            time.sleep(1.5)
            st.rerun()

        except Exception as e:
            st.error(f"❌ Error al guardar los cambios: {str(e)}")
            st.toast(f"❌ Error detallado: {str(e)}")

def obtener_apartment_ids_existentes(cursor):
    cursor.execute("SELECT apartment_id FROM datos_uis")
    return {row[0] for row in cursor.fetchall()}


def mostrar_ofertas_comerciales():
    """Función optimizada para mostrar y gestionar ofertas comerciales"""
    st.info("ℹ️ En esta sección puedes visualizar las ofertas registradas por los comerciales.")

    # Limpiar sesión si existe
    st.session_state.pop("df", None)

    # Cargar datos
    with st.spinner("⏳ Cargando ofertas comerciales..."):
        try:
            conn = obtener_conexion()
            query = "SELECT * FROM comercial_rafa WHERE serviciable IS NOT NULL"
            df_ofertas = pd.read_sql(query, conn)
            conn.close()

            if df_ofertas.empty:
                st.toast("❌ No se encontraron ofertas realizadas por los comerciales.")
                return

        except Exception as e:
            st.error(f"❌ Error al cargar datos de la base de datos: {e}")
            return

    # Guardar en sesión
    st.session_state["df"] = df_ofertas

    # Configurar y mostrar AgGrid
    gb = GridOptionsBuilder.from_dataframe(df_ofertas)
    gb.configure_default_column(
        filter=True,
        floatingFilter=True,
        sortable=True,
        resizable=True,
        minWidth=120,
        flex=1
    )
    grid_options = gb.build()

    AgGrid(
        df_ofertas,
        gridOptions=grid_options,
        enable_enterprise_modules=True,
        update_mode=GridUpdateMode.NO_UPDATE,
        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
        fit_columns_on_grid_load=False,
        height=500,
        theme='alpine-dark',
        reload_data=False
    )

    # Sección de visualización de imagen
    mostrar_imagen_oferta(df_ofertas)

    # Sección de descarga de Excel
    descargar_excel_ofertas(df_ofertas)

    # Sección de eliminación de oferta
    eliminar_oferta_comercial(df_ofertas)

    # Sección de descarga de imágenes
    descargar_imagenes_ofertas(df_ofertas)


def mostrar_imagen_oferta(df_ofertas):
    """Muestra imagen de una oferta seleccionada"""
    st.markdown("---")
    st.subheader("🖼️ Visualizar Imagen de Oferta")

    # Filtrar solo ofertas con imágenes válidas
    ofertas_con_imagen = df_ofertas[
        df_ofertas["fichero_imagen"].notna() &
        (df_ofertas["fichero_imagen"].str.strip() != "")
        ]

    if ofertas_con_imagen.empty:
        st.warning("No hay ofertas con imágenes disponibles.")
        return

    seleccion_id = st.selectbox(
        "Selecciona un Apartment ID para ver su imagen:",
        ofertas_con_imagen["apartment_id"].unique(),
        key="select_imagen_oferta"
    )

    if seleccion_id:
        imagen_url = ofertas_con_imagen[
            ofertas_con_imagen["apartment_id"] == seleccion_id
            ].iloc[0]["fichero_imagen"]

        try:
            st.image(
                imagen_url,
                caption=f"Imagen de la oferta {seleccion_id}",
                width='stretch'
            )
        except Exception:
            st.warning(f"❌ No se pudo cargar la imagen para {seleccion_id}")


def descargar_excel_ofertas(df_ofertas):
    """Genera y permite descargar Excel con las ofertas"""
    st.markdown("---")
    st.subheader("📊 Descargar Datos")

    towrite = io.BytesIO()
    with pd.ExcelWriter(towrite, engine='xlsxwriter') as writer:
        df_ofertas.to_excel(writer, index=False, sheet_name='Ofertas')

    st.download_button(
        label="📥 Descargar todas las ofertas (Excel)",
        data=towrite.getvalue(),
        file_name="ofertas_comerciales.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        help="Descarga todas las ofertas en formato Excel"
    )


def eliminar_oferta_comercial(df_ofertas):
    """Elimina una oferta comercial seleccionada"""
    st.markdown("---")
    st.subheader("🗑️ Eliminar Oferta Comercial")

    # Usar un formulario para la eliminación
    with st.form("form_eliminar_oferta"):
        selected_apartment_id = st.selectbox(
            "Selecciona el Apartment ID de la oferta a eliminar:",
            ["-- Seleccione --"] + sorted(df_ofertas['apartment_id'].unique().tolist()),
            key="select_eliminar_oferta"
        )

        submitted = st.form_submit_button("Eliminar Oferta",
                                          type="primary",
                                          width='stretch')

        if submitted and selected_apartment_id != "-- Seleccione --":
            try:
                conn = obtener_conexion()
                cursor = conn.cursor()

                # Usar parámetros para prevenir SQL injection
                cursor.execute(
                    "DELETE FROM comercial_rafa WHERE apartment_id = ?",
                    (selected_apartment_id,)
                )

                conn.commit()
                conn.close()

                st.success(f"✅ Oferta {selected_apartment_id} eliminada exitosamente.")
                st.toast(f"Oferta {selected_apartment_id} eliminada", icon="✅")

                # Forzar recarga de la página
                st.rerun()

            except Exception as e:
                st.error(f"❌ Error al eliminar la oferta: {e}")


def descargar_imagenes_ofertas(df_ofertas):
    """Gestiona la descarga de imágenes de ofertas"""
    st.markdown("---")
    st.subheader("🖼️ Descargar Imágenes")

    # Filtrar ofertas con imágenes existentes
    ofertas_con_imagen = []
    for _, row in df_ofertas.iterrows():
        img_path = row.get("fichero_imagen")
        if (isinstance(img_path, str) and
                img_path.strip() != "" and
                os.path.exists(img_path)):
            ofertas_con_imagen.append({
                "apartment_id": row["apartment_id"],
                "path": img_path,
                "filename": os.path.basename(img_path)
            })

    if not ofertas_con_imagen:
        st.info("No hay ofertas con imágenes disponibles para descargar.")
        return

    # Descarga individual
    st.markdown("##### Descargar imagen individual")

    selected_offer = st.selectbox(
        "Selecciona una oferta:",
        ["-- Seleccione --"] + [f"{o['apartment_id']} - {o['filename']}"
                                for o in ofertas_con_imagen],
        key="select_descarga_imagen"
    )

    if selected_offer != "-- Seleccione --":
        # Extraer apartment_id de la selección
        apt_id = selected_offer.split(" - ")[0]
        oferta = next(o for o in ofertas_con_imagen if o["apartment_id"] == apt_id)

        col1, col2 = st.columns([1, 2])
        with col1:
            try:
                st.image(oferta["path"], width='stretch')
            except Exception:
                st.warning("No se pudo cargar la vista previa")

        with col2:
            # Determinar MIME type
            ext = os.path.splitext(oferta["path"].lower())[1]
            mime_types = {
                '.png': 'image/png',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.gif': 'image/gif',
                '.bmp': 'image/bmp'
            }
            mime = mime_types.get(ext, 'application/octet-stream')

            with open(oferta["path"], "rb") as f:
                st.download_button(
                    label=f"Descargar {oferta['filename']}",
                    data=f.read(),
                    file_name=oferta['filename'],
                    mime=mime,
                    width='stretch'
                )

    # Descarga múltiple
    st.markdown("##### Descargar todas las imágenes")

    # Opción para seleccionar qué imágenes descargar
    imagenes_seleccionadas = st.multiselect(
        "Selecciona las imágenes a descargar:",
        [f"{o['apartment_id']} - {o['filename']}" for o in ofertas_con_imagen],
        default=[f"{o['apartment_id']} - {o['filename']}" for o in ofertas_con_imagen],
        key="multiselect_imagenes"
    )

    if imagenes_seleccionadas and st.button("📦 Descargar selección como ZIP"):
        with st.spinner("Creando archivo ZIP..."):
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for item in imagenes_seleccionadas:
                    apt_id = item.split(" - ")[0]
                    oferta = next(o for o in ofertas_con_imagen
                                  if o["apartment_id"] == apt_id)
                    zip_file.write(oferta["path"], oferta["filename"])

            st.download_button(
                label=f"📥 Descargar {len(imagenes_seleccionadas)} imágenes",
                data=zip_buffer.getvalue(),
                file_name="imagenes_ofertas.zip",
                mime="application/zip",
                width='stretch'
            )

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
                "Trazabilidad y logs", "Gestionar Usuarios", "Anuncios", "Control de versiones"
            ],
            icons=[
                "house", "graph-up", "bar-chart", "check-circle", "globe", "upload",
                "file-earmark-text", "journal-text", "people", "megaphone", "arrow-clockwise"
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

                st.toast("✅ Has cerrado sesión correctamente. Redirigiendo al login...")
                # Limpiar parámetros de la URL
                st.query_params.clear()  # Limpiamos la URL (opcional, si hay parámetros en la URL)
                st.rerun()

    # Opción: Visualizar datos de la tabla datos_uis
    if opcion == "Home":
        home_page()
    elif opcion == "Ver Datos":

        sub_seccion = option_menu(
            menu_title=None,  # Sin título encima del menú
            options=["Visualizar Datos UIS", "Seguimiento de Contratos", "Precontratos","TIRC"],
            icons=["table", "file-earmark-spreadsheet", "file-text", "puzzle"],  # Puedes cambiar iconos
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
            st.info(
                "ℹ️ Aquí puedes visualizar, filtrar y descargar los datos UIS, Viabilidades y Contratos en formato Excel.")

            if "df" in st.session_state:
                del st.session_state["df"]

            # Función para normalizar apartment_id
            def normalizar_apartment_id(apartment_id):
                if pd.isna(apartment_id) or apartment_id is None or apartment_id == "":
                    return None

                str_id = str(apartment_id).strip().upper()

                # Si ya empieza con P00, limpiar y estandarizar
                if str_id.startswith('P00'):
                    numeros = ''.join(filter(str.isdigit, str_id[3:]))
                    return f"P00{numeros}" if numeros else str_id

                # Si es solo numérico, agregar P00
                if str_id.isdigit() and 1 <= len(str_id) <= 10:
                    return f"P00{str_id}"

                # Intentar extraer números de cualquier formato
                numeros = ''.join(filter(str.isdigit, str_id))
                if numeros and 1 <= len(numeros) <= 10:
                    return f"P00{numeros}"

                return str_id

            with st.spinner("Cargando datos..."):
                try:
                    conn = obtener_conexion()

                    # --- CARGAR TODAS LAS TABLAS ---
                    data_uis = pd.read_sql("SELECT * FROM datos_uis", conn)
                    data_uis["origen"] = "UIS"
                    data_uis["apartment_id_normalizado"] = data_uis["apartment_id"].apply(normalizar_apartment_id)

                    data_via = pd.read_sql("SELECT * FROM viabilidades", conn)
                    data_via["origen"] = "Viabilidad"

                    # Expandir apartment_id separados por comas - MÁS ROBUSTO
                    data_via_expandido = data_via.assign(
                        apartment_id=data_via['apartment_id'].str.split(',')
                    ).explode('apartment_id')
                    data_via_expandido['apartment_id'] = data_via_expandido['apartment_id'].str.strip()
                    data_via = data_via_expandido[data_via_expandido['apartment_id'] != ''].copy()
                    data_via["apartment_id_normalizado"] = data_via["apartment_id"].apply(normalizar_apartment_id)

                    data_contratos = pd.read_sql("SELECT * FROM seguimiento_contratos", conn)
                    data_contratos["apartment_id_normalizado"] = data_contratos["apartment_id"].apply(
                        normalizar_apartment_id)

                    data_tirc = pd.read_sql("SELECT * FROM TIRC", conn)
                    data_tirc["apartment_id_normalizado"] = data_tirc["apartment_id"].apply(normalizar_apartment_id)

                    conn.close()

                except Exception as e:
                    st.toast(f"❌ Error al cargar los datos: {e}")
                    st.stop()

            # PASO 1: Crear una tabla maestra de todos los apartment_id
            st.toast("**Paso 1: Creando tabla maestra de apartment_id...**")

            # Recolectar todos los apartment_id únicos de todas las tablas
            todos_apartment_ids = set()

            # De UIS
            uis_apt_ids = data_uis[['apartment_id', 'apartment_id_normalizado']].drop_duplicates()
            todos_apartment_ids.update(uis_apt_ids['apartment_id_normalizado'].dropna())

            # De Viabilidades
            via_apt_ids = data_via[['apartment_id', 'apartment_id_normalizado']].drop_duplicates()
            todos_apartment_ids.update(via_apt_ids['apartment_id_normalizado'].dropna())

            # De Contratos
            contr_apt_ids = data_contratos[['apartment_id', 'apartment_id_normalizado']].drop_duplicates()
            todos_apartment_ids.update(contr_apt_ids['apartment_id_normalizado'].dropna())

            # De TIRC
            tirc_apt_ids = data_tirc[['apartment_id', 'apartment_id_normalizado']].drop_duplicates()
            todos_apartment_ids.update(tirc_apt_ids['apartment_id_normalizado'].dropna())

            # Crear tabla maestra
            tabla_maestra = pd.DataFrame({'apartment_id_normalizado': list(todos_apartment_ids)})
            st.toast(f"✅ Tabla maestra creada con {len(tabla_maestra)} apartment_id únicos")

            # PASO 2: Unir datos de todas las tablas a la tabla maestra
            st.toast("**Paso 2: Uniendo datos de todas las tablas...**")

            # Unir datos de UIS
            uis_agrupado = data_uis.groupby('apartment_id_normalizado').first().reset_index()
            tabla_maestra = pd.merge(tabla_maestra, uis_agrupado, on='apartment_id_normalizado', how='left',
                                     suffixes=('', '_uis'))

            # Unir datos de Viabilidades
            via_agrupado = data_via.groupby('apartment_id_normalizado').first().reset_index()
            via_agrupado = via_agrupado.rename(columns={
                "cto_admin": "cto",
                "id_cto": "cto_id",
                "direccion_id": "address_id",
                "ticket": "id_ams",
                "usuario": "comercial"
            })
            tabla_maestra = pd.merge(tabla_maestra, via_agrupado, on='apartment_id_normalizado', how='left',
                                     suffixes=('', '_via'))

            # Unir datos de TIRC
            tirc_agrupado = data_tirc.groupby('apartment_id_normalizado').first().reset_index()
            tabla_maestra = pd.merge(tabla_maestra, tirc_agrupado, on='apartment_id_normalizado', how='left',
                                     suffixes=('', '_tirc'))

            # Unir datos de Contratos - FORZAR LA INCLUSIÓN DEL ESTADO
            contr_agrupado = data_contratos.groupby('apartment_id_normalizado').first().reset_index()
            # Renombrar la columna estado para evitar conflictos
            contr_agrupado = contr_agrupado.rename(columns={'estado': 'estado_contrato_original'})

            tabla_maestra = pd.merge(tabla_maestra, contr_agrupado, on='apartment_id_normalizado', how='left',
                                     suffixes=('', '_contrato'))

            st.toast(f"✅ Datos unidos - {len(tabla_maestra)} registros en tabla maestra")

            # --- RESULTADOS DEL CRUCE MEJORADO ---
            # Calcular estadísticas
            total_contratos = len(data_contratos)
            contratos_cruzados_mejorado = tabla_maestra[
                'num_contrato'].notna().sum() if 'num_contrato' in tabla_maestra.columns else 0
            eficiencia_mejorada = (contratos_cruzados_mejorado / total_contratos) * 100 if total_contratos > 0 else 0

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Contratos Totales", total_contratos)
            with col2:
                st.metric("Contratos Cruzados", contratos_cruzados_mejorado)
            with col3:
                st.metric("Eficiencia", f"{eficiencia_mejorada:.1f}%")

            # Mostrar los 12 contratos que no se cruzaron
            if contratos_cruzados_mejorado < total_contratos:
                st.toast(f"🚨 {total_contratos - contratos_cruzados_mejorado} contratos no se cruzaron")
                contratos_no_cruzados = data_contratos[~data_contratos['apartment_id_normalizado'].isin(
                    tabla_maestra[tabla_maestra['num_contrato'].notna()]['apartment_id_normalizado'])]
                if len(contratos_no_cruzados) > 0:
                    with st.expander("Ver contratos no cruzados"):
                        st.dataframe(contratos_no_cruzados[
                                         ['apartment_id', 'apartment_id_normalizado', 'num_contrato', 'cliente',
                                          'estado']])

            # --- PREPARAR DATOS FINALES PARA VISUALIZACIÓN ---
            # Primero, identificar qué columnas tenemos disponibles
            columnas_disponibles = tabla_maestra.columns.tolist()

            # Definir las columnas que nos interesan (sin sufijos)
            columnas_interes = [
                'apartment_id_normalizado', 'origen', 'provincia', 'municipio', 'poblacion',
                'id_ams', 'address_id', 'site_operational_state', 'apartment_operational_state',
                'cto_id', 'olt', 'cto', 'latitud', 'longitud', 'comercial',
                'serviciable', 'coste', 'fecha_viabilidad', 'nombre_cliente', 'telefono',
                'parcela_catastral', 'site_activation_date', 'apartment_activation_date',
                'num_contrato', 'cliente', 'estado_contrato_original', 'fecha_instalacion', 'fecha_fin_contrato',
                'divisor', 'puerto', 'comentarios', 'fecha_inicio_contrato'
            ]

            # Buscar versiones de estas columnas en las columnas disponibles
            columnas_finales = ['apartment_id_normalizado']  # Siempre incluir esta

            for col_base in columnas_interes:
                # Buscar la columna base primero
                if col_base in columnas_disponibles:
                    columnas_finales.append(col_base)
                else:
                    # Buscar versiones con sufijos
                    for sufijo in ['_uis', '_via', '_tirc', '_contrato']:
                        col_con_sufijo = col_base + sufijo
                        if col_con_sufijo in columnas_disponibles:
                            columnas_finales.append(col_con_sufijo)
                            break

            # Crear dataset final para visualización - SOLO con columnas que existen
            columnas_finales_existentes = [col for col in columnas_finales if col in tabla_maestra.columns]
            data_final = tabla_maestra[columnas_finales_existentes].copy()

            # Limpiar y unificar columnas duplicadas
            # Para id_ams
            if 'id_ams' in data_final.columns and 'id_ams_via' in data_final.columns:
                data_final['id_ams'] = data_final['id_ams'].fillna(data_final['id_ams_via'])
                data_final = data_final.drop(['id_ams_via'], axis=1)

            # Para comercial/solicitante
            if 'comercial' in data_final.columns:
                data_final = data_final.rename(columns={"comercial": "solicitante"})
            elif 'comercial_via' in data_final.columns:
                data_final = data_final.rename(columns={"comercial_via": "solicitante"})

            # Para serviciable
            if 'serviciable' in data_final.columns and 'serviciable_via' in data_final.columns:
                data_final['serviciable'] = data_final['serviciable'].fillna(data_final['serviciable_via'])
                data_final = data_final.drop(['serviciable_via'], axis=1)

            # --- FORZAR LA INCLUSIÓN DEL ESTADO DE CONTRATOS ---
            # Opción 1: Si existe estado_contrato_original, renombrarlo a estado
            if 'estado_contrato_original' in data_final.columns:
                data_final['estado'] = data_final['estado_contrato_original']

            # Opción 2: Si no existe, hacer una unión directa con la tabla de contratos
            if 'estado' not in data_final.columns:
                # Hacer merge directo con la tabla de contratos para obtener el estado
                data_final = pd.merge(data_final,
                                      data_contratos[['apartment_id_normalizado', 'estado']],
                                      on='apartment_id_normalizado',
                                      how='left')

            # Opción 3: Si aún no existe, crear columna vacía
            if 'estado' not in data_final.columns:
                data_final['estado'] = None

            # --- ENRIQUECER DATOS DE CONTRATOS CON TIRC Y VIABILIDADES - CORREGIDO ---
            st.toast("**Enriqueciendo datos de contratos con TIRC y Viabilidades...**")

            # Identificar contratos que no tienen origen (solo existen en seguimiento_contratos)
            contratos_sin_origen = data_final[data_final['origen'].isna()].copy()

            if len(contratos_sin_origen) > 0:
                st.toast(f"🔍 Encontrados {len(contratos_sin_origen)} contratos sin origen, enriqueciendo datos...")

                # Crear diccionarios para búsqueda rápida de datos - MÁS ROBUSTO
                tirc_dict = {}
                for _, row in data_tirc.iterrows():
                    apt_id = row['apartment_id_normalizado']
                    if pd.notna(apt_id) and apt_id not in tirc_dict:
                        tirc_dict[apt_id] = row

                via_dict = {}
                for _, row in data_via.iterrows():
                    apt_id = row['apartment_id_normalizado']
                    if pd.notna(apt_id) and apt_id not in via_dict:
                        via_dict[apt_id] = row

                # Para cada contrato sin origen, buscar en TIRC y Viabilidades - CORREGIDO
                for idx in contratos_sin_origen.index:
                    # Obtener el valor de manera segura
                    apt_id_value = data_final.loc[idx, 'apartment_id_normalizado']

                    # Verificar si es una Series y obtener el valor escalar
                    if isinstance(apt_id_value, pd.Series):
                        if len(apt_id_value) > 0:
                            apt_id = apt_id_value.iloc[0]
                        else:
                            apt_id = None
                    else:
                        apt_id = apt_id_value

                    # Función auxiliar para verificar si un valor es nulo o vacío
                    def es_valor_valido(valor):
                        if isinstance(valor, pd.Series):
                            return False
                        return not (pd.isna(valor) or valor is None or valor == '')

                    # Verificar si es un valor válido
                    if not es_valor_valido(apt_id):
                        data_final.at[idx, 'origen'] = 'Contrato'
                        continue

                    origen_actual = 'Contrato'
                    datos_enriquecidos = False

                    # Buscar en TIRC
                    if apt_id in tirc_dict:
                        tirc_row = tirc_dict[apt_id]
                        # Completar datos faltantes con TIRC
                        campos_tirc = ['provincia', 'municipio', 'poblacion', 'cto_id', 'site_operational_state',
                                       'apartment_operational_state', 'parcela_catastral', 'address_id']

                        for campo in campos_tirc:
                            if campo in tirc_row and campo in data_final.columns:
                                valor_actual = data_final.at[idx, campo]
                                valor_tirc = tirc_row[campo]
                                if not es_valor_valido(valor_actual) and es_valor_valido(valor_tirc):
                                    data_final.at[idx, campo] = valor_tirc
                                    datos_enriquecidos = True

                        # Campos específicos de TIRC con nombres diferentes
                        if 'OLT' in tirc_row and 'olt' in data_final.columns:
                            valor_actual = data_final.at[idx, 'olt']
                            valor_tirc = tirc_row['OLT']
                            if not es_valor_valido(valor_actual) and es_valor_valido(valor_tirc):
                                data_final.at[idx, 'olt'] = valor_tirc
                                datos_enriquecidos = True

                        if 'CTO' in tirc_row and 'cto' in data_final.columns:
                            valor_actual = data_final.at[idx, 'cto']
                            valor_tirc = tirc_row['CTO']
                            if not es_valor_valido(valor_actual) and es_valor_valido(valor_tirc):
                                data_final.at[idx, 'cto'] = valor_tirc
                                datos_enriquecidos = True

                        if datos_enriquecidos:
                            origen_actual = 'Contrato + TIRC'

                    # Buscar en Viabilidades
                    if apt_id in via_dict:
                        via_row = via_dict[apt_id]
                        # Completar datos faltantes con Viabilidades
                        campos_via = ['provincia', 'municipio', 'poblacion', 'latitud', 'longitud',
                                      'nombre_cliente', 'telefono', 'serviciable', 'coste', 'id_ams']

                        for campo in campos_via:
                            if campo in via_row and campo in data_final.columns:
                                valor_actual = data_final.at[idx, campo]
                                valor_via = via_row[campo]
                                if not es_valor_valido(valor_actual) and es_valor_valido(valor_via):
                                    data_final.at[idx, campo] = valor_via
                                    datos_enriquecidos = True

                        # Campo específico de viabilidades
                        if 'usuario' in via_row and 'solicitante' in data_final.columns:
                            valor_actual = data_final.at[idx, 'solicitante']
                            valor_via = via_row['usuario']
                            if not es_valor_valido(valor_actual) and es_valor_valido(valor_via):
                                data_final.at[idx, 'solicitante'] = valor_via
                                datos_enriquecidos = True

                        if datos_enriquecidos:
                            if origen_actual == 'Contrato + TIRC':
                                origen_actual = 'Contrato + TIRC + Viabilidad'
                            else:
                                origen_actual = 'Contrato + Viabilidad'

                    data_final.at[idx, 'origen'] = origen_actual

            # Limpieza final
            for col in data_final.columns:
                if col in data_final.columns:
                    col_data = data_final[col]
                    if hasattr(col_data, 'dtype') and col_data.dtype == "object":
                        data_final[col] = data_final[col].replace({'true': True, 'false': False})
                        try:
                            data_final[col] = pd.to_numeric(data_final[col], errors="ignore")
                        except:
                            pass

            # Eliminar columnas duplicadas si las hay
            data_final = data_final.loc[:, ~data_final.columns.duplicated()]

            # --- MOSTRAR ESTADÍSTICAS DE ORIGEN ---
            st.toast("✅ Datos enriquecidos correctamente")

            # Mostrar distribución de orígenes
            if 'origen' in data_final.columns:
                distribucion_origen = data_final['origen'].value_counts()
                with st.expander("📊 Distribución de orígenes de datos"):
                    st.dataframe(distribucion_origen)

                    # Mostrar estadísticas de contratos enriquecidos
                    contratos_enriquecidos = len(data_final[data_final['origen'].str.contains('Contrato', na=False)])
                    st.metric("Contratos enriquecidos con TIRC/Viabilidades", contratos_enriquecidos)

            # --- MOSTRAR DATOS EN AgGrid ---
            st.session_state["df"] = data_final

            # Preparar columnas para mostrar
            columnas = data_final.columns.tolist()
            columnas_a_mostrar = [col for col in columnas]

            # Configurar AgGrid
            gb = GridOptionsBuilder.from_dataframe(data_final[columnas_a_mostrar])
            gb.configure_default_column(
                filter=True,
                floatingFilter=True,
                sortable=True,
                resizable=True,
                minWidth=120,
                flex=1
            )

            # Columnas a ocultar (solo las que existen)
            columnas_a_ocultar = [
                'id', 'motivo', 'respuesta_comercial', 'comentarios_gestor',
                'Presupuesto_enviado', 'justificacion', 'comentarios_comercial',
                'comentarios_internos', 'comentario', 'contratos', 'zona_estudio',
                'nombre_cliente', 'telefono', 'municipio_admin', 'nuevapromocion',
                'resultado', 'confirmacion_rafa', 'CERTIFICABLE', 'zona', 'estado_contrato_original'
            ]

            # Filtrar solo las columnas que existen
            columnas_a_ocultar_existentes = [col for col in columnas_a_ocultar if col in columnas_a_mostrar]

            for col in columnas_a_ocultar_existentes:
                gb.configure_column(col, hide=True)

            gridOptions = gb.build()
            gridOptions['suppressColumnVirtualisation'] = True

            # Mostrar la tabla
            AgGrid(
                data_final[columnas_a_mostrar],
                gridOptions=gridOptions,
                enable_enterprise_modules=True,
                update_mode=GridUpdateMode.NO_UPDATE,
                data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
                fit_columns_on_grid_load=False,
                height=550,
                theme='alpine-dark'
            )

            # --- BOTONES DE DESCARGA Y ENVÍO ---
            towrite = io.BytesIO()
            with pd.ExcelWriter(towrite, engine='xlsxwriter') as writer:
                data_final.to_excel(writer, index=False, sheet_name='Datos Completos')

            towrite.seek(0)

            col1, col2 = st.columns([1, 1])
            with col1:
                st.download_button(
                    label="📥 Descargar excel completo",
                    data=towrite,
                    file_name="datos_completos_mejorado.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    width='stretch'
                )
            with col2:
                if st.button("📧 Enviar excel completo", width='stretch'):
                    with st.spinner("Enviando Excel..."):
                        try:
                            correo_excel_control(
                                destinatario="aarozamena@symtel.es",
                                bytes_excel=towrite.getvalue()
                            )
                            st.toast("✅ Correo enviado correctamente.")
                        except Exception as e:
                            st.toast(f"❌ Error al enviar el correo: {e}")


        elif sub_seccion == "Seguimiento de Contratos":
            st.info("ℹ️ Aquí puedes cargar contratos, mapear columnas, guardar en BD y sincronizar con datos UIS.")

            # Mapeo de columnas del Excel a la BD

            if st.button("🔄 Actualizar contratos"):
                with st.spinner("Cargando y guardando contratos desde Google Sheets..."):
                    try:
                        # 1. Cargar datos desde Google Sheets
                        df = cargar_contratos_google()

                        # Normalizar nombres de columnas INMEDIATAMENTE
                        df.columns = df.columns.map(lambda x: str(x).strip().lower() if x is not None else "")

                        # 2. Guardar en la base de datos
                        conn = obtener_conexion()
                        cur = conn.cursor()

                        # Borrar registros anteriores
                        cur.execute("DELETE FROM seguimiento_contratos")
                        conn.commit()

                        total = len(df)
                        progress = st.progress(0)

                        insert_sql = '''INSERT INTO seguimiento_contratos (
                            num_contrato, cliente, coordenadas, estado, fecha_inicio_contrato, fecha_ingreso,
                            comercial, fecha_instalacion, apartment_id, fecha_fin_contrato, divisor, puerto, comentarios
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'''

                        inserted_divisor = 0
                        inserted_puerto = 0
                        inserted_fecha_fin = 0

                        for i, row in df.iterrows():
                            # Obtener apartment_id y formatearlo
                            ap_id = row.get('apartment_id')
                            try:
                                ap_id_int = int(ap_id)
                                padded_id = 'P' + str(ap_id_int).zfill(10)
                            except (ValueError, TypeError):
                                padded_id = None

                            # Obtener valores CORRECTAMENTE (después de la normalización)
                            fecha_instalacion = row.get('fecha_instalacion')
                            fecha_fin_contrato = row.get('fecha_fin_contrato')

                            # Obtener divisor y puerto usando los nombres NORMALIZADOS
                            divisor = row.get('divisor')
                            puerto = row.get('puerto')

                            # Contar cuántos valores no nulos tenemos
                            if divisor is not None and divisor != '':
                                inserted_divisor += 1
                            if puerto is not None and puerto != '':
                                inserted_puerto += 1
                            if fecha_fin_contrato is not None and fecha_fin_contrato != '':
                                inserted_fecha_fin += 1

                            # Inserción
                            try:
                                cur.execute(insert_sql, (
                                    row.get('num_contrato'),
                                    row.get('cliente'),
                                    row.get('coordenadas'),
                                    row.get('estado'),
                                    row.get('fecha_inicio_contrato'),
                                    row.get('fecha_ingreso'),
                                    row.get('comercial'),
                                    fecha_instalacion,
                                    padded_id,
                                    fecha_fin_contrato,
                                    divisor,
                                    puerto,
                                    row.get('comentarios')
                                ))
                            except Exception as e:
                                st.toast(f"⚠️ Error al insertar fila {i}: {e}")
                                st.write(
                                    f"Valores: divisor={divisor}, puerto={puerto}, fecha_fin_contrato={fecha_fin_contrato}")

                            progress.progress((i + 1) / total)

                        conn.commit()

                        # Mostrar estadísticas de inserción
                        st.info(f"📊 Divisores insertados: {inserted_divisor}/{total}")
                        st.info(f"📊 Puertos insertados: {inserted_puerto}/{total}")
                        st.info(f"📊 Fechas fin contrato insertadas: {inserted_fecha_fin}/{total}")

                        # 3. Verificar qué se guardó realmente en la base de datos
                        cur.execute("""
                            SELECT COUNT(*) as total, 
                                   COUNT(divisor) as con_divisor, 
                                   COUNT(puerto) as con_puerto,
                                   COUNT(fecha_fin_contrato) as con_fecha_fin 
                            FROM seguimiento_contratos
                        """)
                        stats = cur.fetchone()
                        st.toast(
                            f"📊 En base de datos - Total: {stats[0]}, Con divisor: {stats[1]}, Con puerto: {stats[2]}, Con fecha_fin_contrato: {stats[3]}")

                        # 4. Mostrar algunos ejemplos de lo que se guardó
                        cur.execute("""
                            SELECT apartment_id, fecha_fin_contrato, divisor, puerto 
                            FROM seguimiento_contratos 
                            WHERE fecha_fin_contrato IS NOT NULL OR divisor IS NOT NULL OR puerto IS NOT NULL
                            LIMIT 5
                        """)

                        # 5. Actualizar datos_uis (solo si hay datos)
                        if stats[0] > 0:
                            with obtener_conexion() as conn:
                                cur = conn.cursor()

                                # Actualizar divisor en datos_uis
                                cur.execute("""
                                    UPDATE datos_uis
                                    SET divisor = (
                                        SELECT sc.divisor
                                        FROM seguimiento_contratos sc
                                        WHERE sc.apartment_id = datos_uis.apartment_id
                                        AND sc.divisor IS NOT NULL
                                        AND sc.divisor != ''
                                        LIMIT 1
                                    )
                                    WHERE apartment_id IN (
                                        SELECT apartment_id FROM seguimiento_contratos 
                                        WHERE divisor IS NOT NULL AND divisor != ''
                                    )
                                """)
                                updated_divisor = cur.rowcount
                                conn.commit()

                                # Actualizar puerto en datos_uis
                                cur.execute("""
                                    UPDATE datos_uis
                                    SET puerto = (
                                        SELECT sc.puerto
                                        FROM seguimiento_contratos sc
                                        WHERE sc.apartment_id = datos_uis.apartment_id
                                        AND sc.puerto IS NOT NULL
                                        AND sc.puerto != ''
                                        LIMIT 1
                                    )
                                    WHERE apartment_id IN (
                                        SELECT apartment_id FROM seguimiento_contratos 
                                        WHERE puerto IS NOT NULL AND puerto != ''
                                    )
                                """)
                                updated_puerto = cur.rowcount
                                conn.commit()

                                # Actualizar fecha_fin_contrato en datos_uis
                                cur.execute("""
                                    UPDATE datos_uis
                                    SET fecha_fin_contrato = (
                                        SELECT sc.fecha_fin_contrato
                                        FROM seguimiento_contratos sc
                                        WHERE sc.apartment_id = datos_uis.apartment_id
                                        AND sc.fecha_fin_contrato IS NOT NULL
                                        AND sc.fecha_fin_contrato != ''
                                        LIMIT 1
                                    )
                                    WHERE apartment_id IN (
                                        SELECT apartment_id FROM seguimiento_contratos 
                                        WHERE fecha_fin_contrato IS NOT NULL AND fecha_fin_contrato != ''
                                    )
                                """)
                                updated_fecha_fin = cur.rowcount
                                conn.commit()

                                st.toast(
                                    f"✅ Actualizados {updated_divisor} divisores, {updated_puerto} puertos y {updated_fecha_fin} fechas fin contrato en datos_uis")

                        # 6. Feedback final
                        st.toast("✅ Proceso completado correctamente.")

                    except Exception as e:
                        st.toast(f"❌ Error en el proceso: {e}")
                        import traceback
                        st.code(traceback.format_exc())
            # ✅ CHECKBOX RESTAURADO - Mostrar registros existentes
            if st.checkbox("Mostrar registros existentes en la base de datos", key="view_existing_contracts_contratos"):
                with st.spinner("Cargando registros de contratos..."):
                    try:
                        conn = obtener_conexion()
                        existing = pd.read_sql("SELECT * FROM seguimiento_contratos", conn)
                        conn.close()
                        if existing.empty:
                            st.warning("⚠️ No hay registros en 'seguimiento_contratos'.")
                        else:
                            cols = st.multiselect("Filtra columnas a mostrar", existing.columns,
                                                  default=existing.columns,
                                                  key="cols_existing")
                            st.dataframe(existing[cols], width='stretch')
                    except Exception as e:
                        st.toast(f"❌ Error al cargar registros existentes: {e}")

        if sub_seccion == "Precontratos":
            # Conexión a la base de datos para mostrar precontratos existentes
            conn = get_db_connection()
            cursor = conn.cursor()

            # Obtener precontratos (los más recientes primero) - CON NUEVOS CAMPOS
            cursor.execute("""
                            SELECT p.id, p.precontrato_id, p.apartment_id, p.nombre, p.tarifas, p.precio, 
                                   p.fecha, p.comercial, pl.usado, p.mail, p.permanencia, p.telefono1, p.telefono2
                            FROM precontratos p
                            LEFT JOIN precontrato_links pl ON p.id = pl.precontrato_id
                            ORDER BY p.fecha DESC
                            LIMIT 50
                        """)
            precontratos = cursor.fetchall()
            conn.close()

            if precontratos:
                st.write(f"**Últimos {len(precontratos)} precontratos:**")
                for precontrato in precontratos:
                    with st.expander(f"📄 {precontrato[1]} - {precontrato[3] or 'Sin nombre'} - {precontrato[4]}",
                                     expanded=False):

                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.write(f"**ID:** {precontrato[1]}")
                            st.write(f"**Apartment ID:** {precontrato[2] or 'No asignado'}")
                            st.write(f"**Tarifa:** {precontrato[4]}")
                            st.write(f"**Precio:** {precontrato[5]}€")

                        with col2:
                            st.write(f"**Fecha:** {precontrato[6]}")
                            st.write(f"**Comercial:** {precontrato[7]}")
                            st.write(f"**Permanencia:** {precontrato[10] or 'No especificada'}")

                        with col3:
                            estado = "✅ Usado" if precontrato[8] else "🟢 Activo"
                            st.write(f"**Estado:** {estado}")
                            st.write(f"**Email:** {precontrato[9] or 'No especificado'}")
                            st.write(f"**Teléfono 1:** {precontrato[11] or 'No especificado'}")
                            if precontrato[12]:  # Si hay teléfono 2
                                st.write(f"**Teléfono 2:** {precontrato[12]}")

                        # Botón para regenerar enlace si está usado o expirado
                        if precontrato[8]:  # Si está usado
                            if st.button(f"🔄 Regenerar enlace para {precontrato[1]}", key=f"regen_{precontrato[0]}"):
                                try:
                                    conn = get_db_connection()
                                    cursor = conn.cursor()
                                    # Generar nuevo token
                                    token_valido = False
                                    max_intentos = 5
                                    intentos = 0

                                    while not token_valido and intentos < max_intentos:
                                        token = secrets.token_urlsafe(16)
                                        cursor.execute("SELECT id FROM precontrato_links WHERE token = ?", (token,))
                                        if cursor.fetchone() is None:
                                            token_valido = True
                                        intentos += 1

                                    if token_valido:
                                        expiracion = datetime.now() + datetime.timedelta(hours=24)

                                        # Actualizar el token existente
                                        cursor.execute("""
                                                        UPDATE precontrato_links 
                                                        SET token = ?, expiracion = ?, usado = 0
                                                        WHERE precontrato_id = ?
                                                    """, (token, expiracion, precontrato[0]))
                                        conn.commit()
                                        conn.close()
                                        base_url = "https://one7022025.onrender.com"
                                        link_cliente = f"{base_url}?precontrato_id={precontrato[0]}&token={urllib.parse.quote(token)}"
                                        st.success("✅ Nuevo enlace generado correctamente.")
                                        st.code(link_cliente, language="text")
                                        st.info("💡 Copia este nuevo enlace y envíalo al cliente.")
                                except Exception as e:
                                    st.toast(f"❌ Error al regenerar enlace: {e}")

            else:
                st.toast(
                    "📝 No hay precontratos registrados aún. Crea el primero en la pestaña 'Crear Nuevo Precontrato'.")

        if sub_seccion == "TIRC":
            st.info(
                "ℹ️ Aquí puedes visualizar, filtrar y descargar los datos TIRC junto con información de viabilidades relacionadas.")

            # --- 1️⃣ Leer datos de la base de datos ---
            try:
                conn = obtener_conexion()
                df_tirc = pd.read_sql("SELECT * FROM TIRC", conn)
                df_viabilidades = pd.read_sql("SELECT * FROM viabilidades", conn)
                conn.close()
            except Exception as e:
                st.toast(f"❌ Error al cargar datos: {e}")
                df_tirc = pd.DataFrame()
                df_viabilidades = pd.DataFrame()

            if not df_tirc.empty:
                # --- 2️⃣ PROCESAR Y ENRIQUECER DATOS TIRC ---

                # Función para normalizar apartment_id (la misma que usamos antes)
                def normalizar_apartment_id(apartment_id):
                    if pd.isna(apartment_id) or apartment_id is None or apartment_id == "":
                        return None
                    str_id = str(apartment_id).strip().upper()
                    if str_id.startswith('P00'):
                        numeros = ''.join(filter(str.isdigit, str_id[3:]))
                        return f"P00{numeros}" if numeros else str_id
                    if str_id.isdigit() and 1 <= len(str_id) <= 10:
                        return f"P00{str_id}"
                    numeros = ''.join(filter(str.isdigit, str_id))
                    if numeros and 1 <= len(numeros) <= 10:
                        return f"P00{numeros}"
                    return str_id

                # Aplicar normalización a TIRC
                df_tirc["apartment_id_normalizado"] = df_tirc["apartment_id"].apply(normalizar_apartment_id)

                # Preparar viabilidades para el cruce (expandir múltiples apartment_id)
                df_via_expandido = df_viabilidades.assign(
                    apartment_id=df_viabilidades['apartment_id'].str.split(',')
                ).explode('apartment_id')
                df_via_expandido['apartment_id'] = df_via_expandido['apartment_id'].str.strip()
                df_via_expandido = df_via_expandido[df_via_expandido['apartment_id'] != ''].copy()
                df_via_expandido["apartment_id_normalizado"] = df_via_expandido["apartment_id"].apply(
                    normalizar_apartment_id)

                # --- 3️⃣ CREAR DATASET ENRIQUECIDO ---

                # Agrupar viabilidades para evitar duplicados
                via_agrupada = df_via_expandido.groupby('apartment_id_normalizado').agg({
                    'ticket': 'first',
                    'estado': 'first',
                    'serviciable': 'first',
                    'coste': 'first',
                    'fecha_viabilidad': 'first',
                    'usuario': 'first',
                    'nombre_cliente': 'first',
                    'telefono': 'first',
                    'id': 'count'  # Contar cuántas viabilidades tiene este apartment_id
                }).reset_index()

                via_agrupada = via_agrupada.rename(columns={
                    'id': 'cantidad_viabilidades',
                    'usuario': 'comercial_viabilidad'
                })

                # Unir TIRC con viabilidades
                df_tirc_enriquecido = pd.merge(
                    df_tirc,
                    via_agrupada,
                    on='apartment_id_normalizado',
                    how='left',
                    suffixes=('', '_via')
                )

                # Crear columna de relación
                df_tirc_enriquecido['relacion_viabilidad'] = df_tirc_enriquecido['ticket'].apply(
                    lambda x: '✅ Con viabilidad' if pd.notna(x) else '❌ Sin viabilidad'
                )

                # --- 4️⃣ ESTADÍSTICAS ---
                total_tirc = len(df_tirc_enriquecido)
                tirc_con_viabilidad = len(
                    df_tirc_enriquecido[df_tirc_enriquecido['relacion_viabilidad'] == '✅ Con viabilidad'])
                porcentaje_con_viabilidad = (tirc_con_viabilidad / total_tirc) * 100 if total_tirc > 0 else 0

                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total TIRC", total_tirc)
                with col2:
                    st.metric("TIRC con viabilidad", tirc_con_viabilidad)
                with col3:
                    st.metric("Cobertura", f"{porcentaje_con_viabilidad:.1f}%")

                # --- 5️⃣ FILTROS ---
                col1, col2, col3 = st.columns(3)
                with col1:
                    filtro_relacion = st.selectbox(
                        "Relación con viabilidad:",
                        ["Todos", "✅ Con viabilidad", "❌ Sin viabilidad"]
                    )
                with col2:
                    filtro_estado = st.selectbox(
                        "Estado viabilidad:",
                        ["Todos"] + list(df_tirc_enriquecido['estado'].dropna().unique())
                    )
                with col3:
                    filtro_serviciable = st.selectbox(
                        "Serviciable:",
                        ["Todos"] + list(df_tirc_enriquecido['serviciable'].dropna().unique())
                    )

                # Aplicar filtros
                df_filtrado = df_tirc_enriquecido.copy()
                if filtro_relacion != "Todos":
                    df_filtrado = df_filtrado[df_filtrado['relacion_viabilidad'] == filtro_relacion]
                if filtro_estado != "Todos":
                    df_filtrado = df_filtrado[df_filtrado['estado'] == filtro_estado]
                if filtro_serviciable != "Todos":
                    df_filtrado = df_filtrado[df_filtrado['serviciable'] == filtro_serviciable]

                # --- 6️⃣ COLUMNAS PARA MOSTRAR ---
                columnas_base = [
                    'apartment_id', 'provincia', 'municipio', 'poblacion',
                    'ESTADO', 'SINCRONISMO', 'TIPO CTO', 'CTO', 'OLT'
                ]

                columnas_viabilidad = [
                    'relacion_viabilidad', 'ticket', 'estado', 'serviciable',
                    'coste', 'fecha_viabilidad', 'comercial_viabilidad',
                    'nombre_cliente', 'telefono', 'cantidad_viabilidades'
                ]

                # Seleccionar solo columnas que existen
                columnas_a_mostrar = []
                for col in columnas_base + columnas_viabilidad:
                    if col in df_filtrado.columns:
                        columnas_a_mostrar.append(col)

                # --- 7️⃣ CONFIGURAR AgGrid ---
                gb = GridOptionsBuilder.from_dataframe(df_filtrado[columnas_a_mostrar])
                gb.configure_pagination(paginationAutoPageSize=True)
                gb.configure_default_column(
                    editable=False,
                    filter=True,
                    sortable=True,
                    minWidth=120,
                    flex=1
                )

                # Configurar columnas específicas
                gb.configure_column("relacion_viabilidad", headerName="📋 Relación", width=150)
                gb.configure_column("ticket", headerName="🎫 Ticket Viabilidad", width=150)
                gb.configure_column("coste", headerName="💰 Coste", width=100)
                gb.configure_column("fecha_viabilidad", headerName="📅 Fecha Viab.", width=120)
                gb.configure_column("estado", headerName="📊 Estado Viab.", width=120)
                gb.configure_column("serviciable", headerName="✅ Serviciable", width=120)

                grid_options = gb.build()

                # --- 8️⃣ MOSTRAR TABLA ---
                AgGrid(
                    df_filtrado[columnas_a_mostrar],
                    gridOptions=grid_options,
                    enable_enterprise_modules=True,
                    update_mode="MODEL_CHANGED",
                    height=500,
                    fit_columns_on_grid_load=False,
                    theme='alpine-dark'
                )

                # --- 9️⃣ OPCIONES DE DESCARGA ---
                col1, col2, col3 = st.columns(3)

                with col1:
                    # Descargar CSV filtrado
                    csv = df_filtrado[columnas_a_mostrar].to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📥 Descargar CSV (filtrado)",
                        data=csv,
                        file_name="tirc_filtrado.csv",
                        mime="text/csv",
                        width='stretch'
                    )

                with col2:
                    # Descargar Excel completo
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        df_tirc_enriquecido.to_excel(writer, sheet_name='TIRC Completo', index=False)
                        df_filtrado.to_excel(writer, sheet_name='TIRC Filtrado', index=False)
                    output.seek(0)

                    st.download_button(
                        label="📥 Descargar Excel (completo)",
                        data=output,
                        file_name="tirc_completo.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        width='stretch'
                    )

                with col3:
                    # Descargar solo TIRC sin viabilidad
                    tirc_sin_viabilidad = df_tirc_enriquecido[
                        df_tirc_enriquecido['relacion_viabilidad'] == '❌ Sin viabilidad']
                    if not tirc_sin_viabilidad.empty:
                        csv_sin_viab = tirc_sin_viabilidad[columnas_base].to_csv(index=False).encode('utf-8')
                        st.download_button(
                            label="📥 TIRC sin viabilidad",
                            data=csv_sin_viab,
                            file_name="tirc_sin_viabilidad.csv",
                            mime="text/csv",
                            width='stretch'
                        )

                # --- 🔟 INFORMACIÓN ADICIONAL ---
                with st.expander("📈 Información detallada de la relación TIRC-Viabilidades"):
                    col1, col2 = st.columns(2)

                    with col1:
                        st.write("**Distribución por estado de viabilidad:**")
                        if 'estado' in df_tirc_enriquecido.columns:
                            estado_counts = df_tirc_enriquecido['estado'].value_counts()
                            st.dataframe(estado_counts, width='stretch')

                    with col2:
                        st.write("**Distribución por serviciable:**")
                        if 'serviciable' in df_tirc_enriquecido.columns:
                            serviciable_counts = df_tirc_enriquecido['serviciable'].value_counts()
                            st.dataframe(serviciable_counts, width='stretch')

                    # Mostrar algunos ejemplos de TIRC sin viabilidad
                    tirc_sin_viab_ejemplos = df_tirc_enriquecido[
                        df_tirc_enriquecido['relacion_viabilidad'] == '❌ Sin viabilidad'
                        ].head(10)

                    if not tirc_sin_viab_ejemplos.empty:
                        st.write("**Ejemplos de TIRC sin viabilidad:**")
                        st.dataframe(tirc_sin_viab_ejemplos[['apartment_id', 'provincia', 'municipio', 'poblacion']])

            else:
                st.warning("⚠️ No hay datos en la tabla TIRC.")

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
        # Uso en el código principal
        if sub_seccion == "Ver Ofertas":
            mostrar_ofertas_comerciales()

        elif sub_seccion == "Certificación":
            mostrar_certificacion()

    elif opcion == "Viabilidades":
        st.header("Viabilidades")

        with st.expander("🧭 Guía de uso del panel de viabilidades", expanded=False):
            st.info("""
            ℹ️ En esta sección puedes **consultar y completar los tickets de viabilidades** según el comercial, filtrar los datos por etiquetas o columnas, buscar elementos concretos (lupa de la tabla)  
            y **descargar los resultados filtrados en Excel o CSV**.

            🔹 **Organización:**  
            Usa las etiquetas rojas para personalizar cómo deseas visualizar la información en la tabla.  

            🔹 **Edición:**  
            Selecciona la viabilidad que quieras estudiar en el plano y completa los datos en el formulario que se despliega en la parte inferior.  
            Una vez guardadas tus modificaciones, podrás refrescar la tabla para ver los cambios reflejados.  

            🔹 **Creación:**  
            Al pulsar **“Crear Viabilidades”**, haz clic en el mapa para agregar un marcador que represente el punto de viabilidad.  
            También puedes actualizar las tablas internas y el Excel externo desde **“Actualizar tablas”**.  
            
            🔹 **Presupuestos:**  
            Al subir un presupuesto, no te olvides de elegir un remitente y darle a **"Enviar"**. Si no quieres que lo reciba nadie, usa el correo de prueba. 

            🔹 **Importante:**  
            Si una viabilidad requiere **más de una CTO o varios Apartment ID por CTO**, debes crear una viabilidad nueva por cada una.  
            Esto asegura que todos los elementos queden correctamente asignados a su caja específica, generando así dos o más tickets separados.
            """)
        viabilidades_seccion()

    elif opcion == "Mapa UUIIs":
        with st.expander("📊 Guía de uso del panel de datos cruzados AMS / Ofertas", expanded=False):
            st.info("""
                ℹ️ En esta sección puedes **visualizar geográficamente todos los datos cruzados entre AMS y las ofertas de los comerciales**, mostrando su estado actual en el mapa interactivo.

                🔍 **Modos de búsqueda disponibles:**  
                - **Búsqueda por Apartment ID:** Filtra por identificador específico (modo exacto o parcial)  
                - **Búsqueda por ubicación:** Filtra progresivamente por **Provincia → Municipio → Población**  

                ⚙️ **Configuración adicional en "Filtros Avanzados":**
                - **Filtrar por estado:** Serviciable, No serviciable, Contratado, Incidencia, No interesado, No visitado
                - **Personalizar mapa:** Activar/desactivar clusters, leyenda y ajustar zoom inicial

                📊 **Funcionalidades del mapa:**
                - Vista satélite de Google Maps con zoom completo
                - Información detallada al hacer clic en cualquier punto
                - Exportación de los datos filtrados
                - Estadísticas en tiempo real

                ⚠️ **Nota importante:**  
                Los filtros de **ubicación (Provincia, Municipio, Población) solo están activos cuando NO se ha ingresado un Apartment ID**.  
                Para usar filtros geográficos, asegúrate de que el campo de ID esté vacío.
                """)
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
                st.dataframe(df_usuarios, width='stretch', height=540)
            else:
                st.warning("No hay usuarios registrados.")

        # ➕ SUBSECCIÓN: Agregar usuarios
        elif sub_seccion == "Agregar usuarios":
            st.info("ℹ️ Desde esta sección puedes agregar nuevos usuarios al sistema.")
            nombre = st.text_input("Nombre del Usuario")
            rol = st.selectbox("Rol", ["admin", "comercial", "comercial_jefe", "comercial_rafa", "comercial_vip","demo"])
            email = st.text_input("Email del Usuario")
            password = st.text_input("Contraseña", type="password")

            if st.button("Agregar Usuario"):
                if nombre and password and email:
                    agregar_usuario(nombre, rol, password, email)
                    st.toast("✅ Usuario agregado correctamente.")
                else:
                    st.toast("❌ Por favor, completa todos los campos.")

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
                                             ["admin", "comercial", "comercial_jefe", "comercial_rafa","comercial_vip","demo"],
                                             index=["admin", "comercial", "comercial_jefe",
                                                    "comercial_rafa","comercial_vip","demo"].index(usuario[1]))
                    nuevo_email = st.text_input("Nuevo Email", value=usuario[2])
                    nueva_contraseña = st.text_input("Nueva Contraseña", type="password")

                    if st.button("Guardar Cambios"):
                        editar_usuario(usuario_id, nuevo_nombre, nuevo_rol, nueva_contraseña, nuevo_email)
                        st.toast("✅ Usuario editado correctamente.")
                else:
                    st.toast("❌ Usuario no encontrado.")

            st.info("ℹ️ Elimina el usuario que quieras del sistema.")
            eliminar_id = st.number_input("ID del Usuario a Eliminar", min_value=1, step=1)
            if eliminar_id and st.button("Eliminar Usuario"):
                eliminar_usuario(eliminar_id)
                st.toast("✅ Usuario eliminado correctamente.")


    elif opcion == "Cargar Nuevos Datos":
        st.header("Cargar Nuevos Datos")
        with st.expander("⚠️ Carga y reemplazo de base de datos", expanded=False):
            st.info("""
            ℹ️ Aquí puedes **cargar un archivo Excel o CSV** para reemplazar los datos existentes en la base de datos por una versión más reciente.  

            ⚠️ **ATENCIÓN:**  
            - Esta acción **eliminará todos los datos actuales** de la base de datos.  
            - Cualquier actualización realizada dentro de la aplicación también se perderá.  
            - Antes de continuar, asegúrate de que el nuevo archivo contenga **todas las columnas actualizadas** necesarias.  

            🗂️ **Recomendación:**  
            Si el archivo que cargas no tiene la información completa, **recarga el Excel de seguimiento de contratos** para mantener la integridad de los datos.  

            📥 **Nota:** Es posible cargar tanto **nuevos puntos** como **nuevas TIRC**.
            """)

        log_trazabilidad(
            st.session_state["username"],
            "Cargar Nuevos Datos",
            "El admin accedió a la sección de carga de nuevos datos y se procederá a reemplazar el contenido de la tabla."
        )
        col1, col2 = st.columns(2)
        # ===================== 📁 TARJETA PARA CARGAR TIRC =====================
        with col1:
            st.markdown("""
                <div style='
                    background-color:#F0F7F2;
                    padding:25px;
                    margin-top:10px;
                    text-align:center;
                    border-radius:0px;
                '>
                    <h4 style='color:#1e3d59;'>🧩 Cargar Archivos TIRC</h4>
                    <p style='color:#333;'>
                        Arrastra o selecciona uno o varios archivos <b>Excel (.xlsx o .xls)</b> con los datos TIRC actualizados.
                    </p>
                </div>
            """, unsafe_allow_html=True)

            uploaded_tirc_files = st.file_uploader(
                "Selecciona uno o varios Excel para la tabla TIRC",
                type=["xlsx", "xls"],
                key="upload_tirc",
                accept_multiple_files=True,
                label_visibility="collapsed"
            )

            if uploaded_tirc_files:
                conn = obtener_conexion()
                cursor = conn.cursor()

                columnas_tirc = [
                    "id", "apartment_id", "address_id", "provincia", "municipio", "poblacion", "street_id",
                    "tipo_vial", "vial", "parcela_catastral", "tipo", "numero", "bis", "bloque", "portal_puerta",
                    "letra", "cp", "site_dummy", "site_operational_state", "subvention_code", "nodo", "sales_area",
                    "electronica", "red", "competencia", "descripcion", "nota_interna", "lng", "lat", "gis_status",
                    "created_at", "homes", "site_activation_date", "escalera", "piso", "mano1", "mano2",
                    "apartment_sales_area", "apartment_dummy", "apartment_operational_state",
                    "apartment_created_at", "apartment_activation_date", "cto_id", "OLT", "CTO",
                    "FECHA PRIMERA ACTIVACION", "ESTADO", "SINCRONISMO", "TIPO CTO", "CT", "ID TIRC",
                    "FECHA REVISION", "PROYECTO", "POBLACION CORREGIDA"
                ]

                for uploaded_tirc in uploaded_tirc_files:
                    try:
                        with st.spinner(f"⏳ Procesando {uploaded_tirc.name}..."):
                            # Leer Excel con pandas
                            df_tirc = pd.read_excel(uploaded_tirc, dtype=str)

                            # Normalizar encabezados (quitar espacios, mayúsculas, etc.)
                            df_tirc.columns = [c.strip() for c in df_tirc.columns]

                            # Verificar columnas faltantes
                            faltantes = [c for c in columnas_tirc if c not in df_tirc.columns]
                            if faltantes:
                                st.toast(f"❌ {uploaded_tirc.name}: faltan columnas: {', '.join(faltantes)}")
                                continue

                            # Ordenar columnas según estructura esperada
                            df_tirc = df_tirc[columnas_tirc].fillna("")

                            data_values = df_tirc.values.tolist()

                            insert_query = f"""
                                INSERT INTO TIRC ({', '.join([f'"{c}"' for c in columnas_tirc])})
                                VALUES ({', '.join(['?'] * len(columnas_tirc))})
                                ON CONFLICT(id) DO UPDATE SET
                                {', '.join([f'"{c}"=excluded."{c}"' for c in columnas_tirc if c != "id"])}
                            """

                            cursor.executemany(insert_query, data_values)
                            conn.commit()

                            st.toast(f"✅ {uploaded_tirc.name}: {len(df_tirc)} registros insertados/actualizados.")

                            log_trazabilidad(
                                st.session_state["username"],
                                "Carga TIRC incremental",
                                f"Archivo {uploaded_tirc.name} con {len(df_tirc)} registros procesados."
                            )

                    except Exception as e:
                        st.toast(f"❌ Error en {uploaded_tirc.name}: {e}")

                conn.close()

            # ===================== 🧱 TARJETA PARA CARGAR UUII =====================
            with col2:
                st.markdown("""
                <div style='background-color:#F0F7F2; padding:25px; margin-top:10px; text-align:center;'>
                    <h4 style='color:#1e3d59;'>🏢 Cargar Archivo UUII</h4>
                    <p>Arrastra o selecciona el archivo <b>Excel (.xlsx)</b> o <b>CSV</b> con los datos actualizados de puntos comerciales.</p>
                </div>
                """, unsafe_allow_html=True)

                uploaded_file = st.file_uploader(
                    "Selecciona un archivo Excel o CSV para subir nuevos puntos comerciales visitables",
                    type=["xlsx", "csv"],
                    key="upload_uu",
                    label_visibility="collapsed"
                )

                if uploaded_file is not None:
                    try:
                        with st.spinner("⏳ Cargando archivo..."):
                            # Intentar importar ftfy
                            try:
                                USE_FTFY = True
                            except ImportError:
                                USE_FTFY = False
                                st.toast("⚠️ Para mejor corrección de caracteres, instala: pip install ftfy")

                            # Función para limpiar texto usando ftfy si está disponible
                            def limpiar_texto(texto):
                                if texto is None or not isinstance(texto, str):
                                    return texto
                                if USE_FTFY:
                                    return ftfy.fix_text(texto)
                                return texto

                            # Función para limpiar nombres de columnas
                            def limpiar_nombre_columna(nombre):
                                if not isinstance(nombre, str):
                                    return nombre
                                nombre = limpiar_texto(nombre)
                                # Simplificar: convertir a minúsculas y reemplazar espacios/guiones
                                nombre = nombre.strip().lower()
                                nombre = nombre.replace(' ', '_').replace('-', '_')
                                # Eliminar caracteres especiales excepto guión bajo
                                nombre = ''.join(c for c in nombre if c.isalnum() or c == '_')
                                return nombre

                            if uploaded_file.name.endswith(".xlsx"):
                                # Para Excel, usar engine openpyxl
                                data = pd.read_excel(uploaded_file, engine='openpyxl')
                                # Limpiar nombres de columnas
                                data.columns = [limpiar_nombre_columna(col) for col in data.columns]

                            elif uploaded_file.name.endswith(".csv"):
                                # Para CSV, probar diferentes encodings
                                encodings_to_try = ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252', 'utf-8-sig']

                                for encoding in encodings_to_try:
                                    try:
                                        uploaded_file.seek(0)  # Resetear puntero
                                        data = pd.read_csv(uploaded_file, encoding=encoding, on_bad_lines='warn')
                                        st.toast(f"✅ Archivo leído con encoding: {encoding}")
                                        break
                                    except Exception:
                                        continue
                                else:
                                    # Si fallan todos, intentar con reemplazo de errores
                                    uploaded_file.seek(0)
                                    data = pd.read_csv(uploaded_file, encoding='utf-8', on_bad_lines='warn',
                                                       errors='replace')
                                    st.toast("⚠️ Se usó reemplazo de caracteres para leer el archivo")

                                # Limpiar nombres de columnas
                                data.columns = [limpiar_nombre_columna(col) for col in data.columns]

                            # Diccionario para mapear columnas (con variantes permitidas)
                            mapeo_columnas_base = {
                                "id_ams": "id_ams",
                                "apartment_id": "apartment_id",
                                "address_id": "address_id",
                                "provincia": "provincia",
                                "municipio": "municipio",
                                "poblacion": "poblacion",
                                "vial": "vial",
                                "numero": "numero",
                                "parcela_catastral": "parcela_catastral",
                                "letra": "letra",
                                "cp": "cp",
                                "site_operational_state": "site_operational_state",
                                "apartment_operational_state": "apartment_operational_state",
                                "cto_id": "cto_id",
                                "olt": "olt",
                                "cto": "cto",
                                "lat": "latitud",
                                "lng": "longitud",
                                "tipo_olt_rental": "tipo_olt_rental",
                                "certificable": "CERTIFICABLE",
                                "comercial": "comercial",
                                "zona": "zona",
                                "fecha": "fecha",
                                "serviciable": "serviciable",
                                "motivo": "motivo",
                                "contrato_uis": "contrato_uis"
                            }

                            # Crear mapeo con variantes comunes
                            mapeo_columnas = {}
                            variantes_comunes = {
                                "poblacion": ["poblacion", "población", "localidad"],
                                "provincia": ["provincia", "provincia", "prov"],
                                "municipio": ["municipio", "municipio", "ciudad"],
                                "cp": ["cp", "codigo_postal", "codigopostal", "código_postal"],
                                "lat": ["lat", "latitud", "latitude"],
                                "lng": ["lng", "longitud", "longitude", "long"],
                                "fecha": ["fecha", "date", "fecha_actualizacion"],
                                "comercial": ["comercial", "vendedor", "agente"]
                            }

                            # Buscar columnas que coincidan
                            columnas_encontradas = {}
                            columnas_faltantes = []

                            for col_db, col_excel in mapeo_columnas_base.items():
                                encontrada = False

                                # Buscar la columna exacta o variantes
                                posibles_nombres = [col_excel]
                                if col_excel in variantes_comunes:
                                    posibles_nombres.extend(variantes_comunes[col_excel])

                                for posible_nombre in posibles_nombres:
                                    if posible_nombre in data.columns:
                                        columnas_encontradas[col_db] = posible_nombre
                                        encontrada = True
                                        break

                                if not encontrada:
                                    columnas_faltantes.append(col_excel)

                            if columnas_faltantes:
                                st.toast(f"❌ Columnas faltantes: {', '.join(columnas_faltantes)}")
                                st.toast(f"📋 Columnas encontradas en el archivo: {', '.join(data.columns[:10])}")
                                return

                            # Renombrar columnas y limpiar datos
                            data = data.rename(columns={v: k for k, v in columnas_encontradas.items()})

                            # Limpiar contenido de columnas de texto
                            columnas_texto = [
                                'provincia', 'municipio', 'poblacion', 'vial', 'letra',
                                'site_operational_state', 'apartment_operational_state',
                                'olt', 'cto', 'tipo_olt_rental', 'comercial', 'zona',
                                'motivo', 'contrato_uis'
                            ]

                            for col in columnas_texto:
                                if col in data.columns:
                                    data[col] = data[col].astype(str).apply(limpiar_texto)

                            # Seleccionar solo las columnas necesarias
                            columnas_necesarias = list(mapeo_columnas_base.keys())
                            columnas_disponibles = [col for col in columnas_necesarias if col in data.columns]

                            data_filtrada = data[columnas_disponibles].copy()

                            # Renombrar columnas según el esquema final
                            data_filtrada.rename(columns={
                                'lat': 'latitud',
                                'lng': 'longitud',
                                'certificable': 'CERTIFICABLE'
                            }, inplace=True)

                            # Asegurar que tenemos todas las columnas finales
                            columnas_finales = [
                                "id_ams", "apartment_id", "address_id", "provincia", "municipio", "poblacion",
                                "vial", "numero", "parcela_catastral", "letra", "cp", "site_operational_state",
                                "apartment_operational_state", "cto_id", "olt", "cto", "latitud", "longitud",
                                "tipo_olt_rental", "CERTIFICABLE", "comercial", "zona", "fecha",
                                "serviciable", "motivo", "contrato_uis"
                            ]

                            # Añadir columnas faltantes con valores por defecto
                            for col in columnas_finales:
                                if col not in data_filtrada.columns:
                                    if col in ['CERTIFICABLE', 'serviciable']:
                                        data_filtrada[col] = None
                                    elif col == 'fecha':
                                        data_filtrada[col] = pd.Timestamp.now().strftime("%Y-%m-%d")
                                    else:
                                        data_filtrada[col] = ''

                            # Ordenar columnas
                            data_filtrada = data_filtrada[columnas_finales]

                            # Convertir coordenadas
                            data_filtrada["latitud"] = pd.to_numeric(
                                data_filtrada["latitud"].astype(str).str.replace(",", "."), errors="coerce"
                            ).round(7)

                            data_filtrada["longitud"] = pd.to_numeric(
                                data_filtrada["longitud"].astype(str).str.replace(",", "."), errors="coerce"
                            ).round(7)

                            # Procesar fecha
                            if "fecha" in data_filtrada.columns:
                                data_filtrada["fecha"] = pd.to_datetime(data_filtrada["fecha"], errors="coerce")
                                data_filtrada["fecha"] = data_filtrada["fecha"].dt.strftime("%Y-%m-%d")
                                data_filtrada["fecha"] = data_filtrada["fecha"].where(
                                    pd.notnull(data_filtrada["fecha"]), None)

                            # Leer datos anteriores
                            conn = obtener_conexion()
                            df_antiguos = pd.read_sql("SELECT * FROM datos_uis", conn)
                            st.write(
                                "✅ Datos filtrados correctamente. Procediendo a reemplazar los datos en la base de datos...")

                            cursor = conn.cursor()
                            cursor.execute("DELETE FROM datos_uis")
                            cursor.execute("DELETE FROM sqlite_sequence WHERE name='datos_uis'")
                            conn.commit()

                            total_registros = len(data_filtrada)
                            insert_values = data_filtrada.values.tolist()
                            chunk_size = 500
                            num_chunks = (total_registros + chunk_size - 1) // chunk_size

                            query = """
                                INSERT INTO datos_uis (
                                    id_ams, apartment_id, address_id, provincia, municipio, poblacion, vial, numero,
                                    parcela_catastral, letra, cp, site_operational_state, apartment_operational_state,
                                    cto_id, olt, cto, latitud, longitud, tipo_olt_rental, CERTIFICABLE, comercial,
                                    zona, fecha, serviciable, motivo, contrato_uis
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """

                            progress_bar = st.progress(0)
                            for i in range(num_chunks):
                                chunk = insert_values[i * chunk_size: (i + 1) * chunk_size]
                                cursor.executemany(query, chunk)
                                conn.commit()
                                progress_bar.progress(min((i + 1) / num_chunks, 1.0))

                            # -------------------------------------------------------
                            # 🔄 Asignación automática de nuevos puntos en zonas ya asignadas
                            # -------------------------------------------------------

                            # Buscar zonas ya asignadas en comercial_rafa
                            cursor.execute("""
                                SELECT DISTINCT provincia, municipio, poblacion, comercial
                                FROM comercial_rafa
                            """)
                            zonas_asignadas = cursor.fetchall()

                            for zona in zonas_asignadas:
                                provincia, municipio, poblacion, comercial = zona

                                # Puntos ya asignados en esa zona
                                cursor.execute("""
                                    SELECT apartment_id
                                    FROM comercial_rafa
                                    WHERE provincia = ? AND municipio = ? AND poblacion = ? AND comercial = ?
                                """, (provincia, municipio, poblacion, comercial))
                                asignados_ids = {fila[0] for fila in cursor.fetchall()}

                                # Puntos disponibles en datos_uis para esa zona
                                cursor.execute("""
                                    SELECT apartment_id, provincia, municipio, poblacion, vial, numero, letra, cp, latitud, longitud
                                    FROM datos_uis
                                    WHERE provincia = ? AND municipio = ? AND poblacion = ?
                                """, (provincia, municipio, poblacion))
                                puntos_zona = cursor.fetchall()

                                # 🔹 Obtener todos los apartment_id ya existentes en comercial_rafa
                                cursor.execute("SELECT apartment_id FROM comercial_rafa")
                                todos_asignados = {fila[0] for fila in cursor.fetchall()}

                                # 🔹 Filtrar los nuevos para no insertar duplicados
                                nuevos_para_asignar = [p for p in puntos_zona if p[0] not in todos_asignados]

                                # Insertarlos asignados al mismo comercial
                                for p in nuevos_para_asignar:
                                    cursor.execute("""
                                        INSERT INTO comercial_rafa
                                        (apartment_id, provincia, municipio, poblacion, vial, numero, letra, cp, latitud, longitud, comercial, Contrato)
                                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                    """, (p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7], p[8], p[9], comercial,
                                          'Pendiente'))

                                if nuevos_para_asignar:
                                    st.toast(
                                        f"📌 Se asignaron {len(nuevos_para_asignar)} nuevos puntos a {comercial} en la zona {poblacion} ({municipio}, {provincia})"
                                    )

                                    # 🔹 Notificación al comercial
                                    cursor.execute("SELECT email FROM usuarios WHERE LOWER(username) = ?",
                                                   (comercial.lower(),))
                                    resultado = cursor.fetchone()
                                    if resultado:
                                        email = resultado[0]
                                        try:
                                            correo_asignacion_puntos_existentes(
                                                destinatario=email,
                                                nombre_comercial=comercial,
                                                provincia=provincia,
                                                municipio=municipio,
                                                poblacion=poblacion,
                                                nuevos_puntos=len(nuevos_para_asignar)
                                            )
                                            st.write(
                                                f"📧 Notificación enviada a {comercial} ({email}) por nuevos puntos en zona existente")
                                        except Exception as e:
                                            st.toast(f"❌ Error enviando correo a {comercial} ({email}): {e}")
                                    else:
                                        st.toast(f"⚠️ No se encontró email para el comercial: {comercial}")

                                    # 🔹 Notificación a administradores
                                    cursor.execute("SELECT email FROM usuarios WHERE role = 'admin'")
                                    admins = [fila[0] for fila in cursor.fetchall()]
                                    for email_admin in admins:
                                        try:
                                            correo_asignacion_puntos_existentes(
                                                destinatario=email_admin,
                                                nombre_comercial=comercial,
                                                provincia=provincia,
                                                municipio=municipio,
                                                poblacion=poblacion,
                                                nuevos_puntos=len(nuevos_para_asignar)
                                            )
                                            st.toast(
                                                f"📧 Notificación enviada a administrador ({email_admin}) por nuevos puntos en zona existente")
                                        except Exception as e:
                                            st.toast(f"❌ Error enviando correo a admin ({email_admin}): {e}")

                            conn.commit()

                            # Comparar apartment_id nuevos
                            apt_antiguos = set(df_antiguos['apartment_id'].unique())
                            apt_nuevos = set(data_filtrada['apartment_id'].unique())
                            nuevos_apartment_id = apt_nuevos - apt_antiguos
                            df_nuevos_filtrados = data_filtrada[data_filtrada['apartment_id'].isin(nuevos_apartment_id)]

                            try:
                                df_nuevos_filtrados["comercial"] = df_nuevos_filtrados["comercial"].astype(str)
                                df_nuevos_filtrados["poblacion"] = df_nuevos_filtrados["poblacion"].astype(str)

                                resumen = df_nuevos_filtrados.groupby('comercial').agg(
                                    total_nuevos=('apartment_id', 'count'),
                                    poblaciones_nuevas=('poblacion', lambda x: ', '.join(sorted(x.dropna().unique())))
                                ).reset_index()
                            except Exception as e:
                                st.warning(f"⚠️ Error generando resumen de nuevos datos: {e}")
                                resumen = pd.DataFrame()

                            for _, row in resumen.iterrows():
                                comercial = str(row["comercial"]).strip()
                                total_nuevos = row["total_nuevos"]
                                poblaciones_nuevas = row["poblaciones_nuevas"]

                                comercial_normalizado = comercial.lower()
                                cursor.execute("SELECT email FROM usuarios WHERE LOWER(username) = ?",
                                               (comercial_normalizado,))
                                resultado = cursor.fetchone()

                                if resultado:
                                    email = resultado[0]
                                    try:
                                        correo_nuevas_zonas_comercial(
                                            destinatario=email,
                                            nombre_comercial=comercial,
                                            total_nuevos=total_nuevos,
                                            poblaciones_nuevas=poblaciones_nuevas
                                        )
                                        st.write(f"📧 Notificación enviada a {comercial} ({email})")
                                    except Exception as e:
                                        st.toast(f"❌ Error enviando correo a {comercial} ({email}): {e}")
                                else:
                                    st.toast(f"⚠️ No se encontró email para el comercial: {comercial}")

                            # 🔹 Notificar también a los administradores
                            cursor.execute("SELECT email FROM usuarios WHERE role = 'admin'")
                            admins = [fila[0] for fila in cursor.fetchall()]

                            for email_admin in admins:
                                try:
                                    correo_nuevas_zonas_comercial(
                                        destinatario=email_admin,
                                        nombre_comercial="ADMINISTRACIÓN",
                                        total_nuevos=total_registros,
                                        poblaciones_nuevas="Se han cargado nuevos datos en el sistema."
                                    )
                                    st.write(f"📧 Notificación enviada a administrador ({email_admin})")
                                except Exception as e:
                                    st.toast(f"❌ Error enviando correo a admin ({email_admin}): {e}")

                            st.success("✅ Archivo procesado correctamente y datos actualizados en la base de datos")

                    except Exception as e:
                        st.error(f"❌ Error al cargar el archivo: {e}")
                        import traceback
                        st.error(f"Detalles: {traceback.format_exc()}")


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
                    st.toast("✔️ Tabla vaciada y IDs reseteados con éxito.")
                except Exception as e:
                    st.toast(f"❌ Error al vaciar la tabla: {e}")

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
                    st.dataframe(trazabilidad_data[columnas], width='stretch')

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
                st.toast(f"❌ Error al cargar la trazabilidad: {e}")

    elif opcion == "Anuncios":
        st.info(f"📢 Panel de Anuncios Internos")
        conn = get_db_connection()
        cursor = conn.cursor()

        # Crear tabla si no existe (sin columna autor)
        cursor.execute("""
                CREATE TABLE IF NOT EXISTS anuncios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    titulo TEXT NOT NULL,
                    descripcion TEXT NOT NULL,
                    fecha TEXT NOT NULL
                )
            """)
        conn.commit()

        # Obtener rol del usuario actual
        rol = st.session_state.get("role", "user")

        # ───────────────────────────────────────
        # 📝 Formulario solo para admin o jefe
        # ───────────────────────────────────────
        if rol in ["admin", "comercial_jefe"]:
            with st.form("form_anuncio"):
                titulo = st.text_input("📰 Título del anuncio", placeholder="Ej: Nueva carga de datos completada")
                descripcion = st.text_area(
                    "📋 Descripción o comentarios",
                    placeholder="Ej: Se han actualizado los datos de asignaciones del 10 al 15 de octubre..."
                )
                enviar = st.form_submit_button("📢 Publicar anuncio")

                if enviar:
                    if not titulo or not descripcion:
                        st.toast("❌ Debes completar todos los campos.")
                    else:
                        fecha_actual = pd.Timestamp.now(tz="Europe/Madrid").strftime("%Y-%m-%d %H:%M:%S")
                        cursor.execute("""
                                INSERT INTO anuncios (titulo, descripcion, fecha)
                                VALUES (?, ?, ?)
                            """, (titulo, descripcion, fecha_actual))
                        conn.commit()
                        st.toast("✅ Anuncio publicado correctamente.")

        # ───────────────────────────────────────
        # 🗂️ Listado de anuncios
        # ───────────────────────────────────────
        df_anuncios = pd.read_sql_query("SELECT * FROM anuncios ORDER BY id DESC", conn)
        conn.close()

        if df_anuncios.empty:
            st.info("ℹ️ No hay anuncios publicados todavía.")
        else:
            for _, row in df_anuncios.iterrows():
                with st.expander(f"📢 {row['titulo']}  —  🕒 {row['fecha']}"):
                    st.markdown(f"🗒️ {row['descripcion']}")

    elif opcion == "Control de versiones":
        log_trazabilidad(st.session_state["username"], "Control de versiones", "El admin accedió a la sección de control de versiones.")
        mostrar_control_versiones()


def mostrar_leyenda_en_streamlit():
    """Muestra la leyenda directamente en Streamlit (no en el mapa)"""
    with st.expander("📍 Leyenda del Mapa", expanded=True):
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("""
            **Colores de los marcadores:**
            - 🟢 **Verde:** Serviciable
            - 🔴 **Rojo:** No serviciable  
            - 🟠 **Naranja:** Contrato Sí
            """)

        with col2:
            st.markdown("""
            **Continuación:**
            - ⚫ **Gris:** No interesado
            - 🟣 **Morado:** Incidencia
            - 🔵 **Azul:** No Visitado
            """)

def mostrar_certificacion():
    """Muestra el panel de certificación con análisis de ofertas y observaciones"""
    st.info("📋 **Certificación de Ofertas** - Análisis completo de visitas comerciales y estado de CTOs")

    with st.spinner("⏳ Cargando y procesando datos de certificación..."):
        try:
            # Cargar datos principales
            conn = obtener_conexion()
            if conn is None:
                st.error("❌ No se pudo conectar a la base de datos")
                return

            # Primero, obtener las columnas disponibles de comercial_rafa
            cursor = conn.cursor()

            # Método 1: Usar PRAGMA para SQLite
            cursor.execute("PRAGMA table_info(comercial_rafa)")
            columnas_comercial_rafa = [row[1] for row in cursor.fetchall()]

            # Método alternativo: Usar consulta SELECT con LIMIT 0
            # cursor.execute("SELECT * FROM comercial_rafa LIMIT 0")
            # columnas_comercial_rafa = [desc[0] for desc in cursor.description]

            st.toast(f"📊 Columnas en comercial_rafa: {len(columnas_comercial_rafa)} encontradas")

            # Verificar columnas específicas
            columnas_a_incluir = []
            columnas_base = [
                'apartment_id', 'comercial', 'serviciable', 'incidencia',
                'Tipo_Vivienda', 'observaciones', 'contrato', 'fichero_imagen'
            ]

            # Buscar variaciones de fecha
            posibles_nombres_fecha = ['fecha_visita', 'fecha', 'fecha_visita_comercial',
                                      'visita_fecha', 'fecha_visita_1', 'fecha_visita_2']

            nombre_fecha = None
            for nombre in posibles_nombres_fecha:
                if nombre in columnas_comercial_rafa:
                    nombre_fecha = nombre
                    st.toast(f"✅ Columna de fecha encontrada: {nombre_fecha}")
                    break

            # Construir consulta dinámicamente
            columnas_seleccionadas = []

            # Columnas de comercial_rafa
            for col in columnas_base:
                if col in columnas_comercial_rafa:
                    columnas_seleccionadas.append(f"cr.{col}")
                else:
                    st.toast(f"⚠️ Columna '{col}' no encontrada en comercial_rafa")

            # Añadir columna de fecha si existe
            if nombre_fecha:
                columnas_seleccionadas.append(f"cr.{nombre_fecha}")

            # Si no hay suficientes columnas, usar todas
            if len(columnas_seleccionadas) < 5:
                st.warning("⚠️ Pocas columnas encontradas, usando SELECT *")
                columnas_seleccionadas = ["cr.*"]

            # Consulta dinámica
            columnas_str = ", ".join(columnas_seleccionadas)

            query_ofertas = f"""
            SELECT 
                {columnas_str},
                du.cto,
                du.olt,
                du.provincia AS provincia_du,
                du.municipio AS municipio_du,
                du.poblacion AS poblacion_du,
                du.vial AS vial_du,
                du.numero AS numero_du
            FROM comercial_rafa cr
            LEFT JOIN datos_uis du ON cr.apartment_id = du.apartment_id
            WHERE (cr.contrato IS NULL OR LOWER(TRIM(COALESCE(cr.contrato, ''))) != 'pendiente')
            AND cr.serviciable IS NOT NULL
            """

            # Mostrar consulta para depuración
            with st.expander("🔍 Ver consulta SQL", expanded=False):
                st.code(query_ofertas)

            df_ofertas = pd.read_sql(query_ofertas, conn)

            if df_ofertas.empty:
                st.warning("⚠️ No se encontraron ofertas válidas para certificación.")
                conn.close()
                return

            # Paso 2: Calcular estadísticas por CTO
            query_ctos = """
            WITH visitas_realizadas AS (
                SELECT DISTINCT apartment_id 
                FROM comercial_rafa 
                WHERE observaciones IS NOT NULL 
                AND TRIM(COALESCE(observaciones, '')) != ''
            )
            SELECT
                du.cto,
                COUNT(DISTINCT du.apartment_id) AS total_viviendas_cto,
                COUNT(DISTINCT vr.apartment_id) AS viviendas_visitadas
            FROM datos_uis du
            LEFT JOIN visitas_realizadas vr ON du.apartment_id = vr.apartment_id
            WHERE du.cto IS NOT NULL AND du.cto != ''
            GROUP BY du.cto
            """

            df_ctos = pd.read_sql(query_ctos, conn)
            conn.close()

            if df_ctos.empty:
                st.warning("⚠️ No se encontraron datos de CTOs.")
                return

            # Calcular porcentaje
            df_ctos['porcentaje_visitado'] = (
                        df_ctos['viviendas_visitadas'] / df_ctos['total_viviendas_cto'] * 100).round(2)

            # Paso 3: Unir datos
            if 'cto' in df_ofertas.columns:
                df_final = pd.merge(
                    df_ofertas,
                    df_ctos,
                    on='cto',
                    how='left',
                    suffixes=('', '_cto_stats')
                )
            else:
                # Si no hay columna cto, no podemos hacer merge
                st.error("❌ No se encontró la columna 'cto' para unir estadísticas")
                df_final = df_ofertas.copy()
                df_final['total_viviendas_cto'] = None
                df_final['viviendas_visitadas'] = None
                df_final['porcentaje_visitado'] = None

            # Renombrar columnas para claridad
            rename_map = {}
            if 'provincia_du' in df_final.columns:
                rename_map['provincia_du'] = 'provincia'
            if 'municipio_du' in df_final.columns:
                rename_map['municipio_du'] = 'municipio'
            if 'poblacion_du' in df_final.columns:
                rename_map['poblacion_du'] = 'poblacion'
            if 'vial_du' in df_final.columns:
                rename_map['vial_du'] = 'vial'
            if 'numero_du' in df_final.columns:
                rename_map['numero_du'] = 'numero'

            if rename_map:
                df_final = df_final.rename(columns=rename_map)

            # Mostrar información sobre el DataFrame
            with st.expander("📊 Información del DataFrame", expanded=False):
                st.write(f"**Filas:** {len(df_final)}")
                st.write(f"**Columnas:** {len(df_final.columns)}")
                st.write("**Columnas disponibles:**", list(df_final.columns))
                st.write("**Primeras filas:**")
                st.dataframe(df_final.head())

            # Clasificar observaciones
            df_final = clasificar_observaciones(df_final)

            # Mostrar resultados
            mostrar_resultados_certificacion(df_final)

        except Exception as e:
            st.error(f"❌ Error en el proceso de certificación: {str(e)}")
            import traceback
            with st.expander("🔍 Ver detalles del error", expanded=False):
                st.code(traceback.format_exc())
            st.toast("Error al generar la certificación", icon="❌")


def clasificar_observaciones(df):
    """Clasifica automáticamente las observaciones en categorías"""

    # Verificar si existe la columna observaciones
    if 'observaciones' not in df.columns:
        st.warning("⚠️ No se encontró la columna 'observaciones'")
        df['categoria_observacion'] = 'Sin observaciones'
        return df

    # Definir categorías
    CATEGORIAS = {
        "Cliente con otro operador": [
            "movistar", "adamo", "digi", "vodafone", "orange", "jazztel",
            "euskaltel", "netcan", "o2", "yoigo", "masmovil", "másmóvil",
            "otro operador", "no se quiere cambiar",
            "con el móvil se arreglan", "datos ilimitados"
        ],
        "Segunda residencia / vacía": [
            "segunda residencia", "casa vacía", "casa cerrada", "vacacional",
            "deshabitada", "abandonada", "cerrada", "cerrado", "no vive nadie",
            "casa en ruinas", "abandonado", "abandonada"
        ],
        "No interesado": [
            "no quiere", "no le interesa", "no interesado",
            "no contratar", "decide no contratar", "anciano", "persona mayor",
            "sin internet", "no necesita fibra", "no necesita internet",
            "no tiene interes", "no tiene interés", "no estan en casa"
        ],
        "Pendiente / seguimiento": [
            "pendiente visita", "pendiente", "dejado contacto", "dejada info",
            "dejado folleto", "presentada oferta", "hablar con hijo",
            "volver más adelante", "me llamará", "lo tiene que pensar"
        ],
        "Cliente Verde": [
            "contratado con verde", "cliente de verde", "ya es cliente de verde",
            "verde", "otro comercial"
        ],
        "Reformas / obra": [
            "reforma", "obra", "reformando", "rehabilitando", "en obras"
        ],
        "Venta / Contrato realizado": [
            "venta realizada", "vendido", "venta hecha",
            "contrata fibra", "contrato solo fibra", "contrata tarifa"
        ]
    }

    def asignar_categoria(observacion):
        if not isinstance(observacion, str) or observacion.strip() == "":
            return "Sin observaciones"

        texto = observacion.lower()

        for categoria, palabras_clave in CATEGORIAS.items():
            for palabra in palabras_clave:
                if palabra in texto:
                    return categoria

        return "Otros / sin clasificar"

    df['categoria_observacion'] = df['observaciones'].apply(asignar_categoria)
    return df


def mostrar_resultados_certificacion(df):
    """Muestra los resultados de la certificación"""

    # Mostrar información sobre columnas disponibles
    with st.expander("📋 Columnas disponibles en los datos", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total de registros", f"{len(df):,}")
            st.metric("Total de columnas", f"{len(df.columns)}")
        with col2:
            if 'comercial' in df.columns:
                comerciales_unicos = df['comercial'].nunique()
                st.metric("Comerciales únicos", f"{comerciales_unicos}")
            if 'cto' in df.columns:
                ctos_unicos = df['cto'].nunique()
                st.metric("CTOs únicos", f"{ctos_unicos}")

        st.write("**Lista de columnas:**")
        for i, col in enumerate(df.columns, 1):
            st.write(f"{i}. {col} ({df[col].dtype})")

    st.markdown("---")

    # KPIs principales
    st.subheader("📊 Métricas Principales")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        total_ofertas = len(df)
        st.metric("Ofertas Analizadas", f"{total_ofertas:,}")

    with col2:
        if 'cto' in df.columns:
            ctos_unicos = df['cto'].nunique()
            st.metric("CTOs Diferentes", f"{ctos_unicos}")
        else:
            st.metric("CTOs Diferentes", "N/A")

    with col3:
        if 'porcentaje_visitado' in df.columns:
            porcentaje_promedio = df['porcentaje_visitado'].mean()
            st.metric("% Promedio Visitado", f"{porcentaje_promedio:.1f}%")
        else:
            st.metric("% Promedio Visitado", "N/A")

    with col4:
        if 'serviciable' in df.columns:
            serviciables = (df['serviciable'] == 'Sí').sum()
            st.metric("Serviciables", f"{serviciables}")
        else:
            st.metric("Serviciables", "N/A")

    st.markdown("---")

    # Análisis de observaciones
    if 'categoria_observacion' in df.columns:
        st.subheader("📋 Análisis de Observaciones")

        with st.expander("ℹ️ Información sobre las categorías", expanded=False):
            st.info("""
            Las observaciones se clasifican automáticamente en categorías predefinidas.
            - **Cliente con otro operador**: Ya tiene servicio con otra compañía
            - **Segunda residencia / vacía**: Vivienda no habitada permanentemente
            - **No interesado**: Cliente no muestra interés en el servicio
            - **Pendiente / seguimiento**: Requiere seguimiento futuro
            - **Cliente Verde**: Ya es cliente de Verde
            - **Reformas / obra**: Vivienda en obras o reformas
            - **Venta / Contrato realizado**: Venta exitosa
            - **Sin observaciones**: No hay comentarios registrados
            """)

        # Resumen por categoría
        resumen = df['categoria_observacion'].value_counts().reset_index()
        resumen.columns = ['Categoría', 'Cantidad']
        resumen['Porcentaje'] = (resumen['Cantidad'] / len(df) * 100).round(1)

        col1, col2 = st.columns([2, 1])

        with col1:
            # Gráfico de barras
            try:
                import plotly.express as px
                fig = px.bar(
                    resumen,
                    x='Categoría',
                    y='Cantidad',
                    title='Distribución por Categoría',
                    color='Categoría'
                )
                fig.update_layout(height=400, showlegend=False)
                st.plotly_chart(fig, config={'width': 'stretch', 'theme': 'streamlit'})
            except:
                st.dataframe(resumen)

        with col2:
            st.dataframe(
                resumen,
                width='stretch',
                height=400
            )
    else:
        st.warning("⚠️ No se pudo clasificar las observaciones")

    st.markdown("---")

    # Tabla de datos
    st.subheader("📋 Datos Detallados")

    # Filtrar columnas que realmente existen en el DataFrame
    columnas_disponibles = df.columns.tolist()

    # Definir columnas por defecto basadas en las disponibles
    posibles_columnas = [
        'apartment_id', 'comercial', 'provincia', 'municipio',
        'cto', 'serviciable', 'categoria_observacion',
        'observaciones'
    ]

    # Buscar columna de fecha
    posibles_fechas = [col for col in df.columns if 'fecha' in col.lower() or 'visita' in col.lower()]
    if posibles_fechas:
        posibles_columnas.append(posibles_fechas[0])

    columnas_default = [col for col in posibles_columnas if col in columnas_disponibles]

    # Si no hay columnas por defecto, usar las primeras 5
    if not columnas_default and len(columnas_disponibles) > 0:
        columnas_default = columnas_disponibles[:5]

    col1, col2 = st.columns([3, 1])

    with col1:
        columnas_seleccionadas = st.multiselect(
            "Selecciona columnas a mostrar:",
            columnas_disponibles,
            default=columnas_default,
            key="cert_cols_selector"
        )

    with col2:
        # Filtro por comercial si existe
        if 'comercial' in df.columns:
            comerciales = ['Todos'] + sorted(df['comercial'].dropna().unique().tolist())
            comercial_filtro = st.selectbox("Filtrar por comercial:", comerciales)
        else:
            comercial_filtro = 'Todos'

    # Aplicar filtro si es necesario
    df_filtrado = df.copy()
    if comercial_filtro != 'Todos' and 'comercial' in df.columns:
        df_filtrado = df_filtrado[df_filtrado['comercial'] == comercial_filtro]
        st.info(f"Mostrando {len(df_filtrado)} registros del comercial: {comercial_filtro}")

    if columnas_seleccionadas:
        st.dataframe(
            df_filtrado[columnas_seleccionadas],
            width='stretch',
            height=500
        )
    else:
        st.warning("Por favor, selecciona al menos una columna para mostrar")

    # Exportación
    st.markdown("---")
    st.subheader("📥 Exportar Datos")

    col1, col2, col3 = st.columns(3)

    with col1:
        # Exportar a Excel
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Certificación')
        output.seek(0)

        st.download_button(
            label="📥 Excel Completo",
            data=output,
            file_name="certificacion_ofertas.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width='stretch'
        )

    with col2:
        # Exportar datos filtrados
        output_filtrado = io.BytesIO()
        with pd.ExcelWriter(output_filtrado, engine='xlsxwriter') as writer:
            df_filtrado.to_excel(writer, index=False, sheet_name='Datos_Filtrados')
        output_filtrado.seek(0)

        st.download_button(
            label="📊 Datos Filtrados",
            data=output_filtrado,
            file_name="certificacion_filtrada.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width='stretch'
        )

    with col3:
        # Exportar resumen
        if 'categoria_observacion' in df.columns:
            resumen = df['categoria_observacion'].value_counts().reset_index()
            resumen.columns = ['Categoría', 'Cantidad']

            output_resumen = io.BytesIO()
            with pd.ExcelWriter(output_resumen, engine='xlsxwriter') as writer:
                resumen.to_excel(writer, index=False, sheet_name='Resumen')
            output_resumen.seek(0)

            st.download_button(
                label="📈 Resumen",
                data=output_resumen,
                file_name="resumen_certificacion.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width='stretch'
            )

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
        st.plotly_chart(fig, config={'width': 'stretch', 'theme': 'streamlit'})

    with col2:
        labels_incidencias = ['Incidencias', 'Visitas']
        values_incidencias = [porcentaje_incidencias, porcentaje_visitas]
        fig_incidencias = go.Figure(data=[go.Pie(labels=labels_incidencias, values=values_incidencias, hole=0.3,
                                                 textinfo='percent+label',
                                                 marker=dict(colors=['#ff6666', '#99cc99']))])
        fig_incidencias.update_layout(title="Distribución de Visitas e Incidencias", title_x=0, plot_bgcolor='white',
                                      showlegend=False)
        st.plotly_chart(fig_incidencias, config={'width': 'stretch', 'theme': 'streamlit'})

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
        st.plotly_chart(fig_serviciables, config={'width': 'stretch', 'theme': 'streamlit'})

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

        st.plotly_chart(fig_mov, config={'width': 'stretch', 'theme': 'streamlit'})

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

    # ─────────────────────────────────────────────
    # 🔹 VIABILIDADES: Resumen Detallado (Serviciable / Estado / Resultado)
    # ─────────────────────────────────────────────
    st.subheader("📋 Informe de Viabilidades")

    conn = obtener_conexion()

    # 1️⃣ Serviciable (Sí / No / Desconocido)
    query_serviciable = """
        SELECT 
            CASE 
                WHEN LOWER(serviciable) = 'sí' THEN 'Sí'
                WHEN LOWER(serviciable) = 'no' THEN 'No'
                ELSE 'Desconocido'
            END AS Serviciable,
            COUNT(*) AS Total
        FROM viabilidades
        WHERE STRFTIME('%Y-%m-%d', fecha_viabilidad) BETWEEN ? AND ?
        GROUP BY Serviciable
    """
    df_serviciable = pd.read_sql_query(query_serviciable, conn, params=(fecha_inicio, fecha_fin))
    total_viabilidades = df_serviciable["Total"].sum() if not df_serviciable.empty else 0

    # 2️⃣ Estado (fase administrativa)
    query_estado = """
        SELECT 
            COALESCE(estado, 'Sin estado') AS Estado,
            COUNT(*) AS Total
        FROM viabilidades
        WHERE STRFTIME('%Y-%m-%d', fecha_viabilidad) BETWEEN ? AND ?
        GROUP BY Estado
        ORDER BY Total DESC
    """
    df_estado = pd.read_sql_query(query_estado, conn, params=(fecha_inicio, fecha_fin))

    # 3️⃣ Resultado (dictamen final)
    query_resultado = """
        SELECT 
            COALESCE(resultado, 'Sin resultado') AS Resultado,
            COUNT(*) AS Total
        FROM viabilidades
        WHERE STRFTIME('%Y-%m-%d', fecha_viabilidad) BETWEEN ? AND ?
        GROUP BY Resultado
        ORDER BY Total DESC
    """
    df_resultado = pd.read_sql_query(query_resultado, conn, params=(fecha_inicio, fecha_fin))

    # 4️⃣ Viabilidades con comentarios del gestor
    query_comentarios = """
        SELECT COUNT(*) FROM viabilidades 
        WHERE comentarios_gestor IS NOT NULL AND TRIM(comentarios_gestor) <> ''
          AND STRFTIME('%Y-%m-%d', fecha_viabilidad) BETWEEN ? AND ?
    """
    total_comentarios = ejecutar_consulta(query_comentarios, (fecha_inicio, fecha_fin))
    porcentaje_comentarios = (total_comentarios / total_viabilidades * 100) if total_viabilidades > 0 else 0

    conn.close()

    # ──────────────────────────────
    # VISUALIZACIONES
    # ──────────────────────────────
    colv1, colv2 = st.columns(2)
    with colv1:
        fig_s = go.Figure(data=[go.Pie(
            labels=df_serviciable["Serviciable"],
            values=df_serviciable["Total"],
            hole=0.4,
            textinfo="percent+label",
            marker=dict(colors=["#81c784", "#e57373", "#bdbdbd"])
        )])
        fig_s.update_layout(
            title="Distribución de Viabilidades (Serviciables / No / Desconocidas)",
            title_x=0.1,
            showlegend=False
        )
        st.plotly_chart(fig_s, config={'width': 'stretch', 'theme': 'streamlit'})

    with colv2:
        fig_e = go.Figure(data=[go.Bar(
            x=df_estado["Estado"],
            y=df_estado["Total"],
            text=df_estado["Total"],
            textposition="outside"
        )])
        fig_e.update_layout(
            title="Distribución por Estado de Viabilidad",
            title_x=0.1,
            xaxis_title="Estado",
            yaxis_title="Número de Viabilidades",
            height=400
        )
        st.plotly_chart(fig_e, config={'width': 'stretch', 'theme': 'streamlit'})

    colv3, colv4 = st.columns(2)
    with colv3:
        fig_r = go.Figure(data=[go.Bar(
            x=df_resultado["Resultado"],
            y=df_resultado["Total"],
            text=df_resultado["Total"],
            textposition="outside"
        )])
        fig_r.update_layout(
            title="Distribución por Resultado de Viabilidad",
            title_x=0.1,
            xaxis_title="Resultado",
            yaxis_title="Número de Casos",
            height=400
        )
        st.plotly_chart(fig_r, config={'width': 'stretch', 'theme': 'streamlit'})

    with colv4:
        st.metric(label="💬 Viabilidades con Comentarios del Gestor",
                  value=f"{total_comentarios}",
                  delta=f"{porcentaje_comentarios:.2f}% del total")

    # ──────────────────────────────
    # RESUMEN DESCRIPTIVO
    # ──────────────────────────────
    resumen_viabilidades = f"""
    <div style="text-align: justify;">
    En el periodo comprendido entre <strong>{fecha_inicio}</strong> y <strong>{fecha_fin}</strong>, 
    se registraron un total de <strong>{total_viabilidades}</strong> viabilidades.  
    De ellas, las categorías de <strong>serviciabilidad</strong> se distribuyen así:
    <ul>
    {"".join([f"<li>{row['Serviciable']}: <strong>{row['Total']}</strong></li>" for _, row in df_serviciable.iterrows()])}
    </ul>
    Respecto al <strong>estado administrativo</strong>, los casos se reparten entre:
    <ul>
    {"".join([f"<li>{row['Estado']}: <strong>{row['Total']}</strong></li>" for _, row in df_estado.iterrows()])}
    </ul>
    Y en cuanto al <strong>resultado final</strong> de las viabilidades:
    <ul>
    {"".join([f"<li>{row['Resultado']}: <strong>{row['Total']}</strong></li>" for _, row in df_resultado.iterrows()])}
    </ul>
    Finalmente, <strong>{total_comentarios}</strong> viabilidades (<strong>{porcentaje_comentarios:.2f}%</strong>) 
    incluyen comentarios del gestor, lo que refleja el nivel de seguimiento técnico del proceso.
    </div>
    """
    st.markdown(resumen_viabilidades, unsafe_allow_html=True)

    # ─────────────────────────────────────────────
    # 🔹 INFORME DE PRECONTRATOS
    # ─────────────────────────────────────────────
    st.write("----------------------")
    st.subheader("📄 Informe de Precontratos")

    conn = obtener_conexion()

    # 1️⃣ Total de precontratos en el periodo
    query_total_precontratos = """
           SELECT COUNT(*) 
           FROM precontratos 
           WHERE STRFTIME('%Y-%m-%d', fecha) BETWEEN ? AND ?
       """
    total_precontratos = ejecutar_consulta(query_total_precontratos, (fecha_inicio, fecha_fin))

    # 2️⃣ Precontratos por comercial
    query_precontratos_comercial = """
           SELECT comercial, COUNT(*) as total
           FROM precontratos
           WHERE STRFTIME('%Y-%m-%d', fecha) BETWEEN ? AND ?
           GROUP BY comercial
           ORDER BY total DESC
       """
    df_precontratos_comercial = pd.read_sql_query(query_precontratos_comercial, conn, params=(fecha_inicio, fecha_fin))

    # 3️⃣ Precontratos por tarifa
    query_precontratos_tarifa = """
           SELECT tarifas, COUNT(*) as total
           FROM precontratos
           WHERE STRFTIME('%Y-%m-%d', fecha) BETWEEN ? AND ?
           GROUP BY tarifas
           ORDER BY total DESC
       """
    df_precontratos_tarifa = pd.read_sql_query(query_precontratos_tarifa, conn, params=(fecha_inicio, fecha_fin))

    # 4️⃣ Precontratos completados (con firma)
    query_precontratos_completados = """
           SELECT COUNT(*) 
           FROM precontratos 
           WHERE firma IS NOT NULL 
             AND TRIM(firma) <> ''
             AND STRFTIME('%Y-%m-%d', fecha) BETWEEN ? AND ?
       """
    total_precontratos_completados = ejecutar_consulta(query_precontratos_completados, (fecha_inicio, fecha_fin))
    porcentaje_completados = (
                total_precontratos_completados / total_precontratos * 100) if total_precontratos > 0 else 0

    conn.close()

    # Visualizaciones Precontratos
    colp1, colp2 = st.columns(2)

    with colp1:
        if not df_precontratos_comercial.empty:
            fig_prec_comercial2 = go.Figure(data=[go.Bar(
                x=df_precontratos_comercial['comercial'],
                y=df_precontratos_comercial['total'],
                text=df_precontratos_comercial['total'],
                textposition='outside',
                marker_color='#4CAF50'
            )])
            fig_prec_comercial2.update_layout(
                title="Precontratos por Comercial",
                xaxis_title="Comercial",
                yaxis_title="Número de Precontratos",
                height=400
            )
            # Corrección 1: Pasar el parámetro 'key' único
            st.plotly_chart(fig_prec_comercial2, config={'width': 'stretch', 'theme': 'streamlit'},
                            key="precontratos_comercial_bar")

    with colp2:
        if not df_precontratos_tarifa.empty:
            fig_prec_tarifa = go.Figure(data=[go.Pie(
                labels=df_precontratos_tarifa['tarifas'],
                values=df_precontratos_tarifa['total'],
                textinfo='percent+label',
                hole=0.4,
                marker=dict(colors=['#FF9800', '#2196F3', '#9C27B0', '#E91E63'])
            )])
            fig_prec_tarifa.update_layout(
                title="Distribución por Tarifa",
                showlegend=True
            )
            # Corrección 2: Usar la figura CORRECTA (fig_prec_tarifa) y un 'key' único
            st.plotly_chart(fig_prec_tarifa, config={'width': 'stretch', 'theme': 'streamlit'},
                            key="precontratos_tarifa_pie")

    # Métricas Precontratos
    col_met1, col_met2, col_met3 = st.columns(3)
    with col_met1:
        st.metric("Total Precontratos", total_precontratos)
    with col_met2:
        st.metric("Precontratos Completados", total_precontratos_completados)
    with col_met3:
        st.metric("Tasa de Completado", f"{porcentaje_completados:.1f}%")

    # Resumen Precontratos
    resumen_precontratos = f"""
       <div style="text-align: justify;">
       En el periodo analizado, se han generado <strong>{total_precontratos}</strong> precontratos. 
       De estos, <strong>{total_precontratos_completados}</strong> han sido completados por los clientes, 
       lo que representa una tasa de completado del <strong>{porcentaje_completados:.1f}%</strong>.
       {" El comercial con mayor número de precontratos es " + df_precontratos_comercial.iloc[0]['comercial'] + " con " + str(df_precontratos_comercial.iloc[0]['total']) + " precontratos." if not df_precontratos_comercial.empty else ""}
       {" La tarifa más utilizada es " + df_precontratos_tarifa.iloc[0]['tarifas'] + " con " + str(df_precontratos_tarifa.iloc[0]['total']) + " precontratos." if not df_precontratos_tarifa.empty else ""}
       </div>
       <br>
       """
    st.markdown(resumen_precontratos, unsafe_allow_html=True)

    # ─────────────────────────────────────────────
    # 🔹 INFORME DE CONTRATOS
    # ─────────────────────────────────────────────
    st.write("----------------------")
    st.subheader("📊 Informe de Contratos")

    conn = obtener_conexion()

    # 1️⃣ Total de contratos en el periodo
    query_total_contratos = """
           SELECT COUNT(*) 
           FROM seguimiento_contratos 
           WHERE STRFTIME('%Y-%m-%d', fecha_ingreso) BETWEEN ? AND ?
       """
    total_contratos = ejecutar_consulta(query_total_contratos, (fecha_inicio, fecha_fin))

    # 2️⃣ Contratos por estado
    query_contratos_estado = """
           SELECT estado, COUNT(*) as total
           FROM seguimiento_contratos
           WHERE STRFTIME('%Y-%m-%d', fecha_ingreso) BETWEEN ? AND ?
           GROUP BY estado
           ORDER BY total DESC
       """
    df_contratos_estado = pd.read_sql_query(query_contratos_estado, conn, params=(fecha_inicio, fecha_fin))

    # 3️⃣ Contratos por comercial
    query_contratos_comercial = """
           SELECT comercial, COUNT(*) as total
           FROM seguimiento_contratos
           WHERE STRFTIME('%Y-%m-%d', fecha_ingreso) BETWEEN ? AND ?
           GROUP BY comercial
           ORDER BY total DESC
       """
    df_contratos_comercial = pd.read_sql_query(query_contratos_comercial, conn, params=(fecha_inicio, fecha_fin))

    # 4️⃣ Contratos activos vs finalizados
    query_contratos_activos = """
           SELECT COUNT(*) 
           FROM seguimiento_contratos 
           WHERE estado IN ('Activo', 'En proceso', 'Pendiente')
             AND STRFTIME('%Y-%m-%d', fecha_ingreso) BETWEEN ? AND ?
       """
    total_contratos_activos = ejecutar_consulta(query_contratos_activos, (fecha_inicio, fecha_fin))
    porcentaje_activos = (total_contratos_activos / total_contratos * 100) if total_contratos > 0 else 0

    # 5️⃣ Contratos con fecha de instalación
    query_contratos_instalados = """
           SELECT COUNT(*) 
           FROM seguimiento_contratos 
           WHERE fecha_instalacion IS NOT NULL 
             AND TRIM(fecha_instalacion) <> ''
             AND STRFTIME('%Y-%m-%d', fecha_ingreso) BETWEEN ? AND ?
       """
    total_contratos_instalados = ejecutar_consulta(query_contratos_instalados, (fecha_inicio, fecha_fin))
    porcentaje_instalados = (total_contratos_instalados / total_contratos * 100) if total_contratos > 0 else 0

    conn.close()

    # Visualizaciones Contratos
    colc1, colc2 = st.columns(2)
    with colc1:
        if not df_contratos_estado.empty:
            fig_cont_estado = go.Figure(data=[go.Bar(
                x=df_contratos_estado['estado'],
                y=df_contratos_estado['total'],
                text=df_contratos_estado['total'],
                textposition='outside',
                marker_color='#2196F3'
            )])
            fig_cont_estado.update_layout(
                title="Contratos por Estado",
                xaxis_title="Estado",
                yaxis_title="Número de Contratos",
                height=400
            )
            st.plotly_chart(fig_cont_estado, config={'width': 'stretch', 'theme': 'streamlit'})

    with colc2:
        if not df_contratos_comercial.empty:
            fig_cont_comercial = go.Figure(data=[go.Pie(
                labels=df_contratos_comercial['comercial'],
                values=df_contratos_comercial['total'],
                textinfo='percent+label',
                hole=0.4,
                marker=dict(colors=['#FF5722', '#795548', '#607D8B', '#009688'])
            )])
            fig_cont_comercial.update_layout(
                title="Distribución por Comercial",
                showlegend=True
            )
            st.plotly_chart(fig_cont_comercial, config={'width': 'stretch', 'theme': 'streamlit'})

    # Métricas Contratos
    col_metc1, col_metc2, col_metc3, col_metc4 = st.columns(4)
    with col_metc1:
        st.metric("Total Contratos", total_contratos)
    with col_metc2:
        st.metric("Contratos Activos", total_contratos_activos)
    with col_metc3:
        st.metric("Tasa de Activos", f"{porcentaje_activos:.1f}%")
    with col_metc4:
        st.metric("Contratos Instalados", total_contratos_instalados)

    # Resumen Contratos
    resumen_contratos = f"""
       <div style="text-align: justify;">
       En el periodo analizado, se han registrado <strong>{total_contratos}</strong> contratos en el sistema. 
       De estos, <strong>{total_contratos_activos}</strong> se encuentran activos o en proceso 
       (<strong>{porcentaje_activos:.1f}%</strong> del total), y <strong>{total_contratos_instalados}</strong> 
       ya cuentan con fecha de instalación confirmada.
       {" El estado más común es " + df_contratos_estado.iloc[0]['estado'] + " con " + str(df_contratos_estado.iloc[0]['total']) + " contratos." if not df_contratos_estado.empty else ""}
       {" El comercial con mayor número de contratos es " + df_contratos_comercial.iloc[0]['comercial'] + " con " + str(df_contratos_comercial.iloc[0]['total']) + " contratos." if not df_contratos_comercial.empty else ""}
       </div>
       <br>
       """
    st.markdown(resumen_contratos, unsafe_allow_html=True)

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
                    st.toast("Por favor completa todos los campos.")
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

                    st.toast("Versión agregada y notificaciones enviadas.")
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
        st.toast(f"Ha ocurrido un error al cargar el control de versiones: {e}")





# Función para crear el gráfico interactivo de Serviciabilidad
def create_serviciable_graph(cursor) -> go.Figure:
    """Crea gráfico de distribución de serviciabilidad"""
    cursor.execute("""
        SELECT serviciable, COUNT(*) as count
        FROM comercial_rafa
        WHERE serviciable IN ('Sí', 'No')
        GROUP BY serviciable
        ORDER BY serviciable DESC
    """)

    data = cursor.fetchall()
    df = pd.DataFrame(data, columns=["serviciable", "count"])

    # Asegurar que siempre existan ambas categorías
    categories = {"Sí": 0, "No": 0}
    for _, row in df.iterrows():
        categories[row["serviciable"]] = row["count"]

    df = pd.DataFrame({
        "serviciable": list(categories.keys()),
        "count": list(categories.values())
    })

    fig = px.bar(
        df,
        x="serviciable",
        y="count",
        title="Distribución de Serviciabilidad",
        labels={"serviciable": "Serviciable", "count": "Cantidad"},
        color="serviciable",
        color_discrete_map={"Sí": "#2E7D32", "No": "#C62828"}
    )

    fig.update_layout(
        barmode='group',
        height=400,
        showlegend=False,
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)'
    )

    # Añadir etiquetas de valor
    fig.update_traces(
        texttemplate='%{y}',
        textposition='outside'
    )

    return fig


# Función para crear el gráfico interactivo de Incidencias por Provincia
def create_incidencias_graph(cursor) -> go.Figure:
    """Crea gráfico de incidencias por provincia"""
    cursor.execute("""
        SELECT 
            COALESCE(provincia, 'No especificada') as provincia,
            COUNT(*) AS total_incidencias
        FROM comercial_rafa
        WHERE LOWER(COALESCE(incidencia, '')) = 'sí'
        GROUP BY provincia
        ORDER BY total_incidencias DESC
        LIMIT 10
    """)

    data = cursor.fetchall()
    df = pd.DataFrame(data, columns=["provincia", "count"])

    fig = px.bar(
        df,
        x="provincia",
        y="count",
        title="Top 10 - Incidencias por Provincia",
        labels={"provincia": "Provincia", "count": "Cantidad"},
        color="provincia",
        color_discrete_sequence=px.colors.qualitative.Pastel
    )

    fig.update_layout(
        barmode='group',
        height=400,
        showlegend=False,
        xaxis_tickangle=45,
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)'
    )

    return fig


# Gráfico Distribución de Tipos de Vivienda
def create_tipo_vivienda_distribution_graph(cursor) -> go.Figure:
    """Crea gráfico de distribución de tipos de vivienda"""
    cursor.execute("""
        SELECT 
            COALESCE(NULLIF(Tipo_Vivienda, ''), 'No especificado') as Tipo_Vivienda,
            COUNT(*) as count
        FROM comercial_rafa 
        GROUP BY Tipo_Vivienda
        ORDER BY count DESC
        LIMIT 8
    """)

    data = cursor.fetchall()
    df = pd.DataFrame(data, columns=["Tipo_Vivienda", "count"])

    # Crear gráfico de barras horizontales para mejor lectura
    fig = px.bar(
        df,
        x="count",
        y="Tipo_Vivienda",
        title="Top 8 - Distribución de Tipos de Vivienda",
        labels={"Tipo_Vivienda": "Tipo de Vivienda", "count": "Cantidad"},
        color="Tipo_Vivienda",
        orientation='h',
        color_discrete_sequence=px.colors.sequential.Blues
    )

    fig.update_layout(
        height=400,
        showlegend=False,
        yaxis={'categoryorder': 'total ascending'},
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)'
    )

    # Añadir etiquetas de valor
    fig.update_traces(
        texttemplate='%{x}',
        textposition='outside'
    )

    return fig


# Gráfico de Viabilidades por Municipio
def create_viabilities_by_municipio_graph(cursor) -> go.Figure:
    """Crea gráfico de viabilidades por municipio"""
    cursor.execute("""
        SELECT 
            COALESCE(municipio, 'No especificado') as municipio,
            COUNT(*) as count
        FROM viabilidades
        GROUP BY municipio
        ORDER BY count DESC
        LIMIT 8
    """)

    data = cursor.fetchall()
    df = pd.DataFrame(data, columns=["municipio", "count"])

    # Usar gráfico de donut para mejor visualización
    fig = px.pie(
        df,
        values="count",
        names="municipio",
        title="Top 8 - Viabilidades por Municipio",
        hole=0.4,
        color_discrete_sequence=px.colors.sequential.RdBu
    )

    fig.update_layout(
        height=400,
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.2,
            xanchor="center",
            x=0.5
        ),
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)'
    )

    fig.update_traces(
        textposition='inside',
        textinfo='percent+label',
        hovertemplate='<b>%{label}</b><br>Viabilidades: %{value}<br>Porcentaje: %{percent}'
    )

    return fig


# Función para crear métricas KPI
def create_kpi_metrics(cursor) -> None:
    """Crea y muestra métricas KPI principales"""
    kpi_queries = {
        "Total Registros": "SELECT COUNT(*) FROM comercial_rafa",
        "Serviciables": "SELECT COUNT(*) FROM comercial_rafa WHERE serviciable = 'Sí'",
        "Incidencias": "SELECT COUNT(*) FROM comercial_rafa WHERE LOWER(COALESCE(incidencia, '')) = 'sí'",
        "Viabilidades Totales": "SELECT COUNT(*) FROM viabilidades"
    }

    kpi_values = {}
    for name, query in kpi_queries.items():
        try:
            cursor.execute(query)
            kpi_values[name] = cursor.fetchone()[0]
        except:
            kpi_values[name] = 0

    # Mostrar métricas en 4 columnas
    cols = st.columns(4)
    kpi_config = {
        "Total Registros": {"icon": "📊", "color": "#4A90E2"},
        "Serviciables": {"icon": "✅", "color": "#2E7D32"},
        "Incidencias": {"icon": "⚠️", "color": "#FF9800"},
        "Viabilidades Totales": {"icon": "📋", "color": "#9C27B0"}
    }

    for (kpi_name, kpi_val), col in zip(kpi_values.items(), cols):
        config = kpi_config.get(kpi_name, {})
        col.metric(
            label=f"{config.get('icon', '📈')} {kpi_name}",
            value=f"{kpi_val:,}",
            delta=None
        )


# Función principal de la página optimizada
def home_page():
    """Página principal con resumen de datos relevantes"""

    # Obtener la conexión
    conn = obtener_conexion()
    cursor = conn.cursor()

    try:
        # Mostrar KPIs principales
        create_kpi_metrics(cursor)
        st.markdown("---")

        # Organizar los gráficos en columnas
        col1, col2 = st.columns(2)

        # Gráfico de Serviciabilidad
        with col1:
            # Corrección aplicada aquí
            st.plotly_chart(create_serviciable_graph(cursor), config={'width': 'stretch'})
        with col2:
            # Corrección aplicada aquí
            st.plotly_chart(create_incidencias_graph(cursor), config={'width': 'stretch'})
        with col1:
            # Corrección aplicada aquí
            st.plotly_chart(create_tipo_vivienda_distribution_graph(cursor), config={'width': 'stretch'})
        with col2:
            # Corrección aplicada aquí
            st.plotly_chart(create_viabilities_by_municipio_graph(cursor), config={'width': 'stretch'})

        # Opcional: Mostrar tabla de datos detallados
        with st.expander("📋 Ver datos detallados", expanded=False):
            cursor.execute("""
                SELECT 
                    provincia,
                    municipio,
                    serviciable,
                    incidencia,
                    Tipo_Vivienda,
                    COUNT(*) as total
                FROM comercial_rafa
                GROUP BY provincia, municipio, serviciable, incidencia, Tipo_Vivienda
                ORDER BY total DESC
                LIMIT 20
            """)
            detalle_data = cursor.fetchall()
            df_detalle = pd.DataFrame(detalle_data,
                                      columns=["Provincia", "Municipio", "Serviciable", "Incidencia", "Tipo_Vivienda",
                                               "Total"])
            st.dataframe(df_detalle, width='stretch')

    except Exception as e:
        st.error(f"❌ Error al cargar los gráficos: {str(e)}")
        st.toast(f"Hubo un error al cargar los gráficos: {e}", icon="⚠️")

    finally:
        cursor.close()
        conn.close()


# Si necesitas mantener compatibilidad con la versión anterior
def obtener_conexion():
    """Wrapper para mantener compatibilidad"""
    return get_db_connection()  # Asumiendo que existe esta función


if __name__ == "__main__":
    admin_dashboard()
