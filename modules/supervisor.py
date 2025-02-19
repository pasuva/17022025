import streamlit as st
import pandas as pd
import sqlite3
import io
from datetime import datetime


def log_trazabilidad(usuario, accion, detalles):
    """ Inserta un registro en la tabla de trazabilidad """
    conn = sqlite3.connect("data/usuarios.db")  # Usamos la misma base de datos de usuarios
    cursor = conn.cursor()

    # Obtener la fecha y hora actual
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        INSERT INTO trazabilidad (usuario_id, accion, detalles, fecha)
        VALUES (?, ?, ?, ?)
    """, (usuario, accion, detalles, fecha))

    conn.commit()
    conn.close()


def supervisor_dashboard():
    """Panel del supervisor"""
    st.set_page_config(page_title="Panel del Supervisor", page_icon="📁", layout="wide")

    # Título del panel
    st.title("📁 Panel del Supervisor")

    # Mostrar el ícono de usuario centrado y más grande en la barra lateral
    st.sidebar.markdown(""" 
        <style> 
            .user-circle { 
                width: 100px; 
                height: 100px; 
                border-radius: 50%; 
                background-color: #28a745; 
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
        <div>Rol: Supervisor</div>
        """, unsafe_allow_html=True)

    # Mostrar el nombre del supervisor en la barra lateral
    st.sidebar.write(f"Bienvenido, {st.session_state['username']}")

    # Menú lateral para elegir qué visualizar
    menu_opcion = st.sidebar.radio("Selecciona la vista:", ["Datos UIS", "Ofertas Comerciales"])

    # Registrar trazabilidad de la selección del menú
    detalles = f"El supervisor seleccionó la vista '{menu_opcion}'."
    log_trazabilidad(st.session_state["username"], "Selección de vista", detalles)

    st.write("Desde aquí puedes visualizar los datos y descargarlos.")

    # Botón de Cerrar Sesión en la barra lateral
    with st.sidebar:
        if st.button("Cerrar sesión"):
            # Registrar trazabilidad del cierre de sesión
            detalles = f"El supervisor {st.session_state['username']} cerró sesión."
            log_trazabilidad(st.session_state["username"], "Cierre sesión", detalles)

            # Eliminar los datos de la sesión
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.success("✅ Has cerrado sesión correctamente. Redirigiendo al login...")
            st.rerun()

    # Eliminar la variable "data" del session_state si existe
    if "data" in st.session_state:
        del st.session_state["data"]

    # Cargar los datos directamente desde la base de datos según la opción seleccionada
    with st.spinner("Cargando datos... Esto puede tomar unos segundos."):
        try:
            conn = sqlite3.connect("data/usuarios.db")  # Asegúrate de que la ruta sea correcta
            # Verificar que la tabla exista
            query_tables = "SELECT name FROM sqlite_master WHERE type='table';"
            tables = pd.read_sql(query_tables, conn)
            if menu_opcion == "Datos UIS":
                if 'datos_uis' not in tables['name'].values:
                    st.error("❌ La tabla 'datos_uis' no se encuentra en la base de datos.")
                    conn.close()
                    return
                query = "SELECT * FROM datos_uis"
            else:
                if 'ofertas_comercial' not in tables['name'].values:
                    st.error("❌ La tabla 'ofertas_comercial' no se encuentra en la base de datos.")
                    conn.close()
                    return
                query = "SELECT * FROM ofertas_comercial"
            data = pd.read_sql(query, conn)
            conn.close()

            if data.empty:
                st.error("❌ No se encontraron datos en la base de datos.")
                return

        except Exception as e:
            st.error(f"❌ Error al cargar datos de la base de datos: {e}")
            return

    # Eliminar columnas duplicadas si existen
    if data.columns.duplicated().any():
        st.warning("¡Se encontraron columnas duplicadas! Se eliminarán las duplicadas.")
        data = data.loc[:, ~data.columns.duplicated()]

    # Guardar la variable en session_state para futuras referencias (opcional)
    st.session_state["data"] = data

    # Filtro de columnas a mostrar
    st.subheader("Filtrar Columnas")
    columnas = st.multiselect("Selecciona las columnas a mostrar", data.columns.tolist(), default=data.columns.tolist())

    # Mostrar los datos filtrados
    st.subheader("Datos Cargados")
    st.dataframe(data[columnas], use_container_width=True)

    # Agregar opciones de descarga
    st.subheader("Descargar Datos")
    descarga_opcion = st.radio("¿Cómo quieres descargar los datos?", ["CSV", "Excel"])

    if descarga_opcion == "CSV":
        # Registrar trazabilidad de la descarga de datos
        detalles = f"El supervisor descargó los datos en formato CSV."
        log_trazabilidad(st.session_state["username"], "Descarga de datos", detalles)

        st.download_button(
            label="Descargar como CSV",
            data=data[columnas].to_csv(index=False).encode(),
            file_name="datos.csv",
            mime="text/csv"
        )
    elif descarga_opcion == "Excel":
        # Registrar trazabilidad de la descarga de datos
        detalles = f"El supervisor descargó los datos en formato Excel."
        log_trazabilidad(st.session_state["username"], "Descarga de datos", detalles)

        with st.spinner("Generando archivo Excel... Esto puede tardar unos segundos."):
            towrite = io.BytesIO()
            with pd.ExcelWriter(towrite, engine='xlsxwriter') as writer:
                data[columnas].to_excel(writer, index=False, sheet_name="Datos")
            towrite.seek(0)
            st.download_button(
                label="Descargar como Excel",
                data=towrite,
                file_name="datos.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    st.info("Recuerda que, dependiendo del tamaño de los datos, la descarga puede tardar algunos segundos.")


if __name__ == "__main__":
    supervisor_dashboard()