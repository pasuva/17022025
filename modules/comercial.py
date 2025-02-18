import streamlit as st
import folium
from folium.plugins import MarkerCluster
import pandas as pd
import os
import re
from modules.data_loader import cargar_datos
from streamlit_folium import st_folium

def comercial_dashboard():
    """Muestra el mapa con los puntos asignados al comercial logueado usando folium
    y, al capturar un clic, muestra un formulario para enviar una oferta."""
    st.title("📍 Mapa de Ubicaciones")

    comercial = st.session_state.get("usuario")  # Se cambió 'usuario' por 'username'

    # Spinner mientras se cargan los datos
    with st.spinner("⏳ Cargando los datos del comercial..."):
        df = cargar_datos(comercial)

    # Asegurarse de que df es un DataFrame válido
    if not isinstance(df, pd.DataFrame):
        st.error("❌ Los datos no se cargaron correctamente.")
        return

    # Verificar si el DataFrame está vacío
    if df.empty:
        st.warning("⚠️ No hay datos asignados a este comercial.")
        return

    # Asegurarse de que las columnas necesarias existen
    for col in ['lat_corregida', 'long_corregida', 'address_id']:
        if col not in df.columns:
            st.error(f"❌ No se encuentra la columna '{col}'.")
            return

    # Inicializar la lista de clics en session_state si no existe
    if "clicks" not in st.session_state:
        st.session_state.clicks = []

    # Spinner mientras se carga el mapa
    with st.spinner("⏳ Cargando mapa..."):
        # Crear el mapa base centrado en el primer punto del DataFrame
        initial_lat = df['lat_corregida'].iloc[0]
        initial_lon = df['long_corregida'].iloc[0]
        m = folium.Map(location=[initial_lat, initial_lon], zoom_start=12)
        marker_cluster = MarkerCluster().add_to(m)

        # Agregar los marcadores al clúster, incluyendo address_id en el popup
        for _, row in df.iterrows():
            popup_text = f"🏠 {row['address_id']} - 📍 {row['lat_corregida']}, {row['long_corregida']}"
            folium.Marker(
                location=[row['lat_corregida'], row['long_corregida']],
                popup=popup_text,
                icon=folium.Icon(color='blue', icon='info-sign')
            ).add_to(marker_cluster)

        # Renderizar el mapa en Streamlit
        map_data = st_folium(m, height=500, width=700)

    # Capturar clics en los marcadores
    if map_data and "last_object_clicked" in map_data and map_data["last_object_clicked"]:
        st.session_state.clicks.append(map_data["last_object_clicked"])

    # Mostrar las coordenadas registradas del último clic
    if st.session_state.clicks:
        last_click = st.session_state.clicks[-1]
        st.write(f"✅ Las coordenadas del punto seleccionado son: **{last_click}**")

        # Spinner mientras carga la información del formulario
        with st.spinner("⏳ Cargando formulario..."):
            mostrar_formulario(last_click)

def validar_email(email):
    return re.match(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)

def mostrar_formulario(click_data):
    """Muestra un formulario para enviar una oferta basado en el clic del mapa.
    Se asume que click_data contiene la clave 'popup' con el address_id y coordenadas."""
    st.subheader("📄 Enviar Oferta")

    popup_text = click_data.get("popup", "")
    address_id_value = popup_text.split(" - ")[0] if " - " in popup_text else "N/D"
    lat_value = click_data.get("lat", "N/D")
    lng_value = click_data.get("lng", "N/D")

    st.write(f"📌 Coordenadas seleccionadas: **Latitud {lat_value}, Longitud {lng_value}**")

    with st.form(key="oferta_form"):
        st.text_input("🏠 ID Dirección", value=address_id_value, disabled=True)
        st.text_input("📌 Latitud", value=lat_value, disabled=True)
        st.text_input("📌 Longitud", value=lng_value, disabled=True)
        client_name = st.text_input("👤 Nombre del Cliente", max_chars=100)
        phone = st.text_input("📞 Teléfono", max_chars=15)
        email = st.text_input("📧 Correo Electrónico")
        address = st.text_input("📌 Dirección del Cliente")
        observations = st.text_area("📝 Observaciones")
        submit_button = st.form_submit_button(label="🚀 Enviar Oferta")

        if submit_button:
            if not client_name or not phone or not email or not address:
                st.error("❌ Todos los campos obligatorios deben estar llenos.")
                return
            if not validar_email(email):
                st.error("❌ Formato de correo electrónico inválido.")
                return
            if not phone.isdigit():
                st.error("❌ El teléfono debe contener solo números.")
                return

            oferta_data = {
                "ID Dirección": address_id_value,
                "Nombre Cliente": client_name,
                "Teléfono": phone,
                "Correo": email,
                "Dirección": address,
                "Observaciones": observations,
                "Latitud": lat_value,
                "Longitud": lng_value,
                "Fecha Envío": pd.Timestamp.now()
            }

            excel_filename = "ofertas.xlsx"
            # Spinner mientras se guarda la oferta en Excel
            with st.spinner("⏳ Guardando la oferta en Excel..."):
                try:
                    if os.path.exists(excel_filename):
                        existing_df = pd.read_excel(excel_filename)
                        if oferta_data["ID Dirección"] in existing_df["ID Dirección"].values:
                            st.warning("⚠️ Ya existe una oferta para esta dirección.")
                            return
                        new_df = pd.DataFrame([oferta_data])
                        df_total = pd.concat([existing_df, new_df], ignore_index=True)
                    else:
                        df_total = pd.DataFrame([oferta_data])

                    df_total.to_excel(excel_filename, index=False)
                    st.success("✅ ¡Oferta enviada y guardada en Excel con éxito!")
                except Exception as e:
                    st.error(f"❌ Error al guardar la oferta en Excel: {e}")

if __name__ == "__main__":
    comercial_dashboard()