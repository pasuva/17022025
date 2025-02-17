import streamlit as st
from modules.data_loader import cargar_datos

def supervisor_dashboard():
    """ Panel del supervisor """
    st.title("📁 Panel del Supervisor")
    st.sidebar.write(f"Bienvenido, {st.session_state['username']} (Supervisor)")

    st.write("Desde aquí puedes visualizar los datos del Excel y descargarlo.")

    # Verificar si el dataframe está en session_state y eliminarlo si existe
    if "df" in st.session_state:
        del st.session_state["df"]

    # Cargar los datos nuevamente
    df = cargar_datos()

    # Eliminar columnas duplicadas
    if df.columns.duplicated().any():
        st.warning("¡Se encontraron columnas duplicadas! Se eliminarán las duplicadas.")
        df = df.loc[:, ~df.columns.duplicated()]  # Elimina las columnas duplicadas

    # Guardar el dataframe cargado en session_state para futuras referencias
    if isinstance(df, str):
        st.error(df)  # Si ocurre un error, muestra el mensaje
    else:
        st.session_state["df"] = df  # Guarda el dataframe en session_state para futuras referencias
        st.dataframe(df)  # Muestra la tabla

        # Agregar opciones de descarga
        st.download_button("Descargar Excel", df.to_csv(index=False).encode(), "datos.csv", "text/csv")