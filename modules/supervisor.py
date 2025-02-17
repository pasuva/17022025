import streamlit as st
import pandas as pd
import io
from modules.data_loader import cargar_datos


def supervisor_dashboard():
    """ Panel del supervisor """
    st.set_page_config(page_title="Panel del Supervisor", page_icon="📁",
                       layout="wide")  # Configuración para que ocupe todo el ancho

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

            # Mensaje de confirmación
            st.success("✅ Has cerrado sesión correctamente. Redirigiendo al login...")

            # Redirigir a la página de login después de un breve retraso
            st.rerun()  # Usamos st.rerun() en lugar de st.experimental_rerun()

    # Verificar si el dataframe está en session_state y eliminarlo si existe
    if "df" in st.session_state:
        del st.session_state["df"]

    # Agregar el spinner mientras cargamos los datos
    with st.spinner("Cargando datos... Esto puede tomar unos segundos."):
        # Cargar los datos nuevamente
        df = cargar_datos()

    # Verificar si el dataframe se cargó correctamente
    if isinstance(df, str):
        st.error(df)  # Si ocurre un error, muestra el mensaje
        return
    else:
        # Eliminar columnas duplicadas si existen
        if df.columns.duplicated().any():
            st.warning("¡Se encontraron columnas duplicadas! Se eliminarán las duplicadas.")
            df = df.loc[:, ~df.columns.duplicated()]  # Elimina las columnas duplicadas

        # Guardar el dataframe cargado en session_state para futuras referencias
        st.session_state["df"] = df  # Guarda el dataframe en session_state para futuras referencias

        # Filtro de columnas a mostrar
        st.subheader("Filtrar Columnas")
        columnas = st.multiselect("Selecciona las columnas a mostrar", df.columns.tolist(), default=df.columns.tolist())

        # Mostrar los datos filtrados
        st.subheader("Datos Cargados")
        st.dataframe(df[columnas], use_container_width=True)  # Mostrar la tabla filtrada

        # Agregar opciones de descarga
        st.subheader("Descargar Datos")
        descarga_opcion = st.radio("¿Cómo quieres descargar los datos?", ["CSV", "Excel"])

        if descarga_opcion == "CSV":
            st.download_button(
                label="Descargar como CSV",
                data=df[columnas].to_csv(index=False).encode(),
                file_name="datos.csv",
                mime="text/csv"
            )
        elif descarga_opcion == "Excel":
            with st.spinner("Generando archivo Excel... Esto puede tardar unos segundos."):
                towrite = io.BytesIO()
                with pd.ExcelWriter(towrite, engine='xlsxwriter') as writer:
                    df[columnas].to_excel(writer, index=False, sheet_name="Datos")
                towrite.seek(0)

                st.download_button(
                    label="Descargar como Excel",
                    data=towrite,
                    file_name="datos.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

        # Agregar un mensaje sobre el tamaño de la descarga
        st.info("Recuerda que, dependiendo del tamaño de los datos, la descarga puede tardar algunos segundos.")