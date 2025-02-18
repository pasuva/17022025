import streamlit as st
import folium
from folium.plugins import MarkerCluster
import pandas as pd
import sqlite3
import os
import re
from streamlit_folium import st_folium
import streamlit.components.v1 as components

def comercial_dashboard():
    """Muestra el mapa con los puntos asignados al comercial logueado usando folium."""
    st.title("📍 Mapa de Ubicaciones")

    # Se usa "username" en lugar de "usuario", ya que en el login se guarda con "username"
    comercial = st.session_state.get("username")

    # Spinner mientras se cargan los datos del comercial desde la base de datos
    with st.spinner("⏳ Cargando los datos del comercial..."):
        try:
            conn = sqlite3.connect("data/usuarios.db")  # Asegúrate de que la ruta sea correcta

            # Verificar que la tabla 'datos_uis' exista
            query_tables = "SELECT name FROM sqlite_master WHERE type='table';"
            tables = pd.read_sql(query_tables, conn)
            if 'datos_uis' not in tables['name'].values:
                st.error("❌ La tabla 'datos_uis' no se encuentra en la base de datos.")
                conn.close()
                return

            # Ejecutar la consulta SQL para obtener los datos asignados al comercial
            query = "SELECT * FROM datos_uis WHERE LOWER(COMERCIAL) = LOWER(?)"
            df = pd.read_sql(query, conn, params=(comercial,))
            conn.close()

            if df.empty:
                st.warning("⚠️ No hay datos asignados a este comercial.")
                return
        except Exception as e:
            st.error(f"❌ Error al cargar los datos de la base de datos: {e}")
            return

    # Asegurarse de que df es un DataFrame válido
    if not isinstance(df, pd.DataFrame):
        st.error("❌ Los datos no se cargaron correctamente.")
        return

    # Verificar que las columnas necesarias existen
    for col in ['latitud', 'longitud', 'address_id']:  # Usar las columnas correctas
        if col not in df.columns:
            st.error(f"❌ No se encuentra la columna '{col}'.")
            return

    # Inicializar la lista de clics en session_state si no existe
    if "clicks" not in st.session_state:
        st.session_state.clicks = []

    # Obtener la ubicación utilizando un componente HTML5 en JavaScript
    location = get_user_location()

    if location is None:
        st.error("❌ No se pudo obtener la ubicación.")
        return

    lat, lon = location

    # Spinner mientras se carga el mapa
    with st.spinner("⏳ Cargando mapa..."):
        # Crear el mapa con la latitud y longitud
        m = folium.Map(location=[lat, lon], zoom_start=12)
        marker_cluster = MarkerCluster().add_to(m)

        # Agregar los marcadores al clúster
        for _, row in df.iterrows():
            popup_text = f"🏠 {row['address_id']} - 📍 {row['latitud']}, {row['longitud']}"
            folium.Marker(
                location=[row['latitud'], row['longitud']],
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
        #st.write(f"✅ Las coordenadas del punto seleccionado son: **{last_click}**")

        # Spinner mientras carga la información del formulario
        with st.spinner("⏳ Cargando formulario..."):
            mostrar_formulario(last_click)

def get_user_location():
    """Obtiene la ubicación del usuario a través de un componente de JavaScript."""
    location = components.html("""
        <script>
            if (navigator.geolocation) {
                navigator.geolocation.getCurrentPosition(function(position) {
                    window.location.href = "?lat=" + position.coords.latitude + "&lon=" + position.coords.longitude;
                });
            }
        </script>
    """, height=0)

    # Verificamos si la URL tiene los parámetros de latitud y longitud
    if "lat" in st.query_params and "lon" in st.query_params:
        lat = float(st.query_params["lat"][0])
        lon = float(st.query_params["lon"][0])
        return lat, lon

    return None

def validar_email(email):
    return re.match(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)

def mostrar_formulario(click_data):
    """Muestra un formulario para enviar una oferta basado en el clic del mapa."""
    st.subheader("📄 Enviar Oferta")

    popup_text = click_data.get("popup", "")
    address_id_value = popup_text.split(" - ")[0] if " - " in popup_text else "N/D"
    lat_value = click_data.get("lat", "N/D")
    lng_value = click_data.get("lng", "N/D")

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

