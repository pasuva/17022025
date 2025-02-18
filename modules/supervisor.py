import streamlit as st
import pandas as pd
import sqlite3
import io

def supervisor_dashboard():
    """ Panel del supervisor """
    st.set_page_config(page_title="Panel del Supervisor", page_icon="📁", layout="wide")

    # Título del panel
    st.title("📁 Panel del Supervisor")

    # Mostrar el nombre del supervisor en la barra lateral
    st.sidebar.write(f"Bienvenido, {st.session_state['username']} (Supervisor)")
    st.write("Desde aquí puedes visualizar los datos del Excel y descargarlos.")

    # Botón de Cerrar Sesión en la barra lateral
    with st.sidebar:
        if st.button("Cerrar sesión"):
            # Eliminar los datos de la sesión
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.success("✅ Has cerrado sesión correctamente. Redirigiendo al login...")
            st.rerun()

    # Eliminar la variable "data" del session_state si existe
    if "data" in st.session_state:
        del st.session_state["data"]

    # Cargar los datos directamente desde la base de datos con una consulta SQL
    with st.spinner("Cargando datos... Esto puede tomar unos segundos."):
        try:
            conn = sqlite3.connect("data/usuarios.db")  # Asegúrate de que la ruta sea correcta
            # Verificar que la tabla 'datos_uis' exista
            query_tables = "SELECT name FROM sqlite_master WHERE type='table';"
            tables = pd.read_sql(query_tables, conn)
            if 'datos_uis' not in tables['name'].values:
                st.error("❌ La tabla 'datos_uis' no se encuentra en la base de datos.")
                conn.close()
                return

            # Ejecutar la consulta SQL para obtener los datos
            query = "SELECT * FROM datos_uis"
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

    # Guardar la variable en session_state para futuras referencias (si lo deseas)
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
        st.download_button(
            label="Descargar como CSV",
            data=data[columnas].to_csv(index=False).encode(),
            file_name="datos.csv",
            mime="text/csv"
        )
    elif descarga_opcion == "Excel":
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