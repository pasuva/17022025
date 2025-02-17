import streamlit as st
from modules.data_loader import cargar_datos
import pandas as pd  # Necesario para manipular las columnas duplicadas

def admin_dashboard():
    """ Panel del administrador """
    st.title("📊 Panel de Administración")
    st.sidebar.write(f"Bienvenido, {st.session_state['username']} (Admin)")

    st.write("Desde aquí puedes gestionar los usuarios y la base de datos.")

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
        st.dataframe(df)  # Muestra el dataframe completo

        # Agregar opciones de descarga
        st.download_button("Descargar Excel", df.to_csv(index=False).encode(), "datos.csv", "text/csv")