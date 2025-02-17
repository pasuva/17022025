import streamlit as st
import pandas as pd

def mostrar_formulario(address_id):
    """Formulario para ingresar datos de oferta."""
    st.subheader(f"Registrar Oferta para {address_id}")

    client_name = st.text_input("Nombre del Cliente")
    phone = st.text_input("Teléfono")
    email = st.text_input("Correo Electrónico")
    address = st.text_input("Dirección del Cliente")
    observations = st.text_area("Observaciones")

    if st.button("Enviar Oferta"):
        oferta_data = {
            "ID Dirección": address_id,
            "Nombre Cliente": client_name,
            "Teléfono": phone,
            "Correo": email,
            "Dirección": address,
            "Observaciones": observations,
            "Fecha Envío": pd.Timestamp.now()
        }

        # Guardar en Excel
        excel_filename = "ofertas.xlsx"
        try:
            if pd.io.common.file_exists(excel_filename):
                existing_df = pd.read_excel(excel_filename)
                df_total = pd.concat([existing_df, pd.DataFrame([oferta_data])], ignore_index=True)
            else:
                df_total = pd.DataFrame([oferta_data])

            df_total.to_excel(excel_filename, index=False)
            st.success("¡Oferta enviada y guardada en Excel con éxito!")
        except Exception as e:
            st.error(f"Error al guardar la oferta en el Excel: {e}")