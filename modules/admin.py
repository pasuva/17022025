import streamlit as st
import pandas as pd
import io  # Necesario para trabajar con flujos de bytes
import sqlite3
import bcrypt

DB_PATH = "../data/usuarios.db"


def obtener_conexion():
    """Retorna una nueva conexión a la base de datos."""
    try:
        conn = sqlite3.connect(DB_PATH)
        return conn
    except sqlite3.Error as e:
        print(f"Error al conectar con la base de datos: {e}")
        return None


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


# Función para eliminar un usuario
def eliminar_usuario(id):
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM usuarios WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    st.success(f"Usuario con ID {id} eliminado correctamente.")


# Función principal de la app (Dashboard de administración)
def admin_dashboard():
    """Panel del administrador."""
    st.set_page_config(page_title="Panel de Administración", page_icon="📊", layout="wide")

    # Personalizar la barra lateral
    st.sidebar.title("📊 Panel de Administración")
    st.sidebar.markdown(f"¡Bienvenido, **{st.session_state['username']}**! (Admin)")
    st.sidebar.markdown("---")

    # Opciones de navegación con iconos
    opcion = st.sidebar.radio(
        "Selecciona una opción:",
        ("📈 Ver Datos", "📊 Ofertas Comerciales", "👥 Gestionar Usuarios", "⚙️ Ajustes", "📤 Cargar Nuevos Datos"),
        index=0,
        key="menu",
    )

    # Botón de Cerrar sesión en la barra lateral
    with st.sidebar:
        if st.button("Cerrar sesión"):
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
            data[col] = pd.to_numeric(data[col], errors='ignore')

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

    # Opción: Cargar Nuevos Datos
    elif opcion == "📤 Cargar Nuevos Datos":
        st.header("📤 Cargar Nuevos Datos")
        st.write("Aquí puedes cargar un archivo Excel o CSV para agregar nuevos datos a la base de datos.")

        # Opción de carga de archivo
        uploaded_file = st.file_uploader("Selecciona un archivo Excel o CSV", type=["xlsx", "csv"])

        if uploaded_file is not None:
            try:
                # Cargar el archivo según el tipo
                if uploaded_file.name.endswith(".xlsx"):
                    # Si es un archivo Excel
                    data = pd.read_excel(uploaded_file)
                elif uploaded_file.name.endswith(".csv"):
                    # Si es un archivo CSV
                    data = pd.read_csv(uploaded_file)

                # Reemplazar comas por puntos en latitud y longitud
                data["LATITUD"] = data["LATITUD"].str.replace(",", ".").astype(float)
                data["LONGITUD"] = data["LONGITUD"].str.replace(",", ".").astype(float)

                # Filtrar las columnas necesarias
                columnas_requeridas = [
                    "id_ams", "apartment_id", "address_id", "provincia", "municipio", "poblacion",
                    "vial", "numero", "parcela_catastral", "letra", "cp", "site_operational_state",
                    "apartment_operational_state", "cto_id", "olt", "cto", "LATITUD", "LONGITUD",
                    "cto_con_proyecto", "COMERCIAL", "ZONA", "FECHA", "SERVICIABLE", "MOTIVO", "contrato_uis"
                ]

                # Verificar si todas las columnas requeridas existen en el archivo
                if all(col in data.columns for col in columnas_requeridas):
                    data_filtrada = data[columnas_requeridas]

                    # Conectar a la base de datos
                    conn = obtener_conexion()
                    cursor = conn.cursor()

                    # Recuperar todos los apartment_id existentes para evitar duplicados
                    cursor.execute("SELECT apartment_id FROM datos_uis")
                    existing_apartments = [row[0] for row in cursor.fetchall()]

                    # Filtrar los datos que ya existen en la base de datos
                    nuevos_datos = data_filtrada[~data_filtrada['apartment_id'].isin(existing_apartments)]

                    if not nuevos_datos.empty:
                        # Insertar los nuevos datos en la tabla
                        for index, row in nuevos_datos.iterrows():
                            cursor.execute("""
                                INSERT INTO datos_uis (
                                    id_ams, apartment_id, address_id, provincia, municipio, poblacion,
                                    vial, numero, parcela_catastral, letra, cp, site_operational_state,
                                    apartment_operational_state, cto_id, olt, cto, LATITUD, LONGITUD,
                                    cto_con_proyecto, COMERCIAL, ZONA, FECHA, SERVICIABLE, MOTIVO, contrato_uis
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, tuple(row))

                        # Confirmar los cambios
                        conn.commit()
                        st.success(f"✅ Se han agregado {len(nuevos_datos)} nuevos registros a la base de datos.")
                    else:
                        st.info("No se encontraron nuevos registros para agregar.")
                    conn.close()

                else:
                    st.error("❌ El archivo no contiene las columnas necesarias o está mal formateado.")
            except Exception as e:
                st.error(f"❌ Hubo un error al procesar el archivo: {e}")


if __name__ == "__main__":
    admin_dashboard()
