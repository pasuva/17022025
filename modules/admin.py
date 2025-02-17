import streamlit as st
from modules.data_loader import cargar_datos
import pandas as pd
import io  # Necesario para trabajar con flujos de bytes
import sqlite3
import bcrypt
import os

DB_PATH = "../data/usuarios.db"

def obtener_conexion():
    """ Retorna una nueva conexión a la base de datos """
    try:
        conn = sqlite3.connect(DB_PATH)
        return conn
    except sqlite3.Error as e:
        print(f"Error al conectar con la base de datos: {e}")
        return None


def cargar_usuarios():
    """ Carga los usuarios desde la base de datos """
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
        cursor.execute("UPDATE usuarios SET username = ?, role = ?, password = ? WHERE id = ?", (username, rol, hashed_pw, id))
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
    """ Panel del administrador """
    st.set_page_config(page_title="Panel de Administración", page_icon="📊", layout="wide")

    # Personalizar la barra lateral
    st.sidebar.title("📊 Panel de Administración")

    # Mensaje de bienvenida al usuario
    st.sidebar.markdown(f"¡Bienvenido, **{st.session_state['username']}**! (Admin)")

    # Línea divisoria
    st.sidebar.markdown("---")

    # Opciones de navegación con iconos
    opcion = st.sidebar.radio(
        "Selecciona una opción:",
        ("📈 Ver Datos", "👥 Gestionar Usuarios", "⚙️ Ajustes"),
        index=0,
        key="menu",
    )

    # Agregar botón de Cerrar sesión en la barra lateral
    with st.sidebar:
        if st.button("Cerrar sesión"):
            # Eliminar los datos de la sesión
            for key in list(st.session_state.keys()):
                del st.session_state[key]

            # Mensaje de confirmación
            st.success("✅ Has cerrado sesión correctamente. Redirigiendo al login...")

            # Redirigir a la página de login después de un breve retraso
            st.rerun()  # Usamos st.rerun() en lugar de st.experimental_rerun()

    # Mostrar las diferentes secciones
    if opcion == "📈 Ver Datos":
        # Mostrar la sección de datos
        st.header("📊 Visualizar y gestionar datos")
        st.write("Aquí puedes cargar y gestionar la base de datos.")

        # Verificar si el dataframe está en session_state y eliminarlo si existe
        if "df" in st.session_state:
            del st.session_state["df"]

        # Cargar los datos nuevamente
        with st.spinner("Cargando datos..."):
            df = cargar_datos()

        # Convertir columnas que tienen valores como 'true'/'false' a tipo booleano
        for col in df.select_dtypes(include=["object"]).columns:
            # Intentar convertir las cadenas 'true' y 'false' en valores booleanos
            df[col] = df[col].replace({'true': True, 'false': False})
            # También podemos intentar hacer la conversión a booleano si se tiene '0'/'1' o alguna variante
            df[col] = pd.to_numeric(df[col], errors='ignore')

        # Eliminar columnas duplicadas
        if df.columns.duplicated().any():
            st.warning("¡Se encontraron columnas duplicadas! Se eliminarán las duplicadas.")
            df = df.loc[:, ~df.columns.duplicated()]  # Elimina las columnas duplicadas

        # Guardar el dataframe cargado en session_state para futuras referencias
        if isinstance(df, str):
            st.error(df)  # Si ocurre un error, muestra el mensaje
        else:
            st.session_state["df"] = df  # Guarda el dataframe en session_state para futuras referencias

            # Filtro para la tabla
            st.write("Filtra las columnas del dataframe:")
            columnas = st.multiselect("Selecciona las columnas a mostrar", df.columns.tolist(),
                                      default=df.columns.tolist())

            # Mostrar la tabla (solo la versión filtrada si se aplica algún filtro)
            st.dataframe(df[columnas], use_container_width=True)

            # Opción para elegir formato de descarga
            st.subheader("Selecciona el formato para la descarga:")
            download_format = st.radio("Selecciona el formato de descarga:", ["Excel", "CSV"])

            # Agregar spinner para la descarga
            if download_format == "Excel":
                towrite = io.BytesIO()
                with pd.ExcelWriter(towrite, engine='xlsxwriter') as writer:
                    df.to_excel(writer, index=False, sheet_name='Datos')
                towrite.seek(0)  # Volver al inicio del buffer

                with st.spinner("Preparando archivo Excel..."):
                    st.download_button(
                        label="📥 Descargar Excel",
                        data=towrite,
                        file_name="datos.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )

            elif download_format == "CSV":
                csv = df.to_csv(index=False).encode()

                with st.spinner("Preparando archivo CSV..."):
                    st.download_button(
                        label="📥 Descargar CSV",
                        data=csv,
                        file_name="datos.csv",
                        mime="text/csv"
                    )

    elif opcion == "👥 Gestionar Usuarios":
        # Mostrar la lista de usuarios
        st.header("👥 Gestionar Usuarios")
        st.write("Aquí puedes gestionar los usuarios registrados.")

        # Cargar los usuarios de la base de datos
        usuarios = cargar_usuarios()
        if usuarios:
            st.subheader("Lista de Usuarios")
            df_usuarios = pd.DataFrame(usuarios, columns=["ID", "Nombre", "Rol"])
            st.dataframe(df_usuarios)

        # Opción para agregar un nuevo usuario
        st.subheader("Agregar Nuevo Usuario")
        nombre = st.text_input("Nombre del Usuario")
        rol = st.selectbox("Selecciona el Rol", ["admin", "supervisor", "comercial"])
        password = st.text_input("Contraseña", type="password")

        if st.button("Agregar Usuario"):
            if nombre and password:
                agregar_usuario(nombre, rol, password)
            else:
                st.error("Por favor, completa todos los campos.")

        # Opción para editar un usuario
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
                nuevo_rol = st.selectbox("Nuevo Rol", ["admin", "supervisor", "comercial"], index=["admin", "supervisor", "comercial"].index(usuario[1]))
                nueva_contraseña = st.text_input("Nueva Contraseña", type="password")

                if st.button("Guardar Cambios"):
                    editar_usuario(usuario_id, nuevo_nombre, nuevo_rol, nueva_contraseña)
            else:
                st.error("Usuario no encontrado.")

        # Opción para eliminar un usuario
        st.subheader("Eliminar Usuario")
        eliminar_id = st.number_input("ID del Usuario a Eliminar", min_value=1, step=1)

        if eliminar_id:
            if st.button("Eliminar Usuario"):
                eliminar_usuario(eliminar_id)

    else:
        # Configuración o ajustes adicionales
        st.header("⚙️ Ajustes")
        st.write("Realiza ajustes en la configuración del sistema.")