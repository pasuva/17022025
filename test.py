import streamlit as st
import pandas as pd
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode
import folium
from streamlit_folium import st_folium

# Datos de ejemplo
df = pd.DataFrame({
    "Ticket": ["TKT-001", "TKT-002", "TKT-003"],
    "Estado": ["Abierto", "Cerrado", "Pendiente"],
    "latitud": [40.712776, 40.730610, 40.735657],
    "longitud": [-74.005974, -73.935242, -73.991211],
    "is_duplicate": [False, True, False],
    "apartment_id": ["A1", "A2", "A3"]
})

# Inicializar session_state
if "map_center" not in st.session_state:
    st.session_state.map_center = [40.7128, -74.0060]
if "map_zoom" not in st.session_state:
    st.session_state.map_zoom = 12
if "selected_index" not in st.session_state:
    st.session_state.selected_index = None

# Configurar AgGrid (CON VERSIÓN CORREGIDA)
gb = GridOptionsBuilder.from_dataframe(df)
gb.configure_selection(
    selection_mode='single',
    use_checkbox=True,
    pre_selected_rows=[st.session_state.selected_index] if st.session_state.selected_index is not None else []
)
gridOptions = gb.build()

# Mostrar tabla
grid_response = AgGrid(
    df,
    gridOptions=gridOptions,
    height=400,
    theme='alpine',
    update_mode=GridUpdateMode.SELECTION_CHANGED,
    data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
    fit_columns_on_grid_load=True,
    key="my_grid"  # Key único para persistencia
)

# Procesar selección (VERSIÓN 100% FUNCIONAL)
selected = pd.DataFrame(grid_response["selected_rows"])

# Siempre es un DataFrame. Verificar si está vacío
if not selected.empty:
    # Acceder a los datos CORRECTAMENTE con .iloc
    ticket_seleccionado = selected.iloc[0]["Ticket"]
    selected_index = df.index[df["Ticket"] == ticket_seleccionado].tolist()[0]

    # Actualizar session_state
    st.session_state.selected_index = selected_index
    st.session_state.map_center = [
        selected.iloc[0]["latitud"],
        selected.iloc[0]["longitud"]
    ]
    st.session_state.map_zoom = 14
else:
    st.session_state.selected_index = None

# Mostrar detalles del ticket
if st.session_state.selected_index is not None:
    selected_row = df.iloc[st.session_state.selected_index]
    st.subheader(f"📝 Formulario para Ticket: {selected_row['Ticket']}")
    st.write(f"**Estado:** {selected_row['Estado']}")
    st.write(f"**Apartamento ID:** {selected_row['apartment_id']}")
    st.write(f"**Viabilidad duplicada:** {selected_row['is_duplicate']}")
else:
    st.info("Selecciona una fila en la tabla para ver detalles.")


# Dibujar mapa
def draw_map(center, zoom):
    m = folium.Map(location=center, zoom_start=zoom, tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
                   attr="Google")
    for _, row in df.iterrows():
        folium.Marker(
            location=[row['latitud'], row['longitud']],
            popup=f"Ticket: {row['Ticket']}",
            icon=folium.Icon(
                color='blue' if (st.session_state.selected_index is not None and
                                 row['Ticket'] == df.iloc[st.session_state.selected_index]['Ticket'])
                else 'gray'
            )
        ).add_to(m)
    return m


st.subheader("🗺️ Mapa de Viabilidad")
m = draw_map(st.session_state.map_center, st.session_state.map_zoom)
st_folium(m, height=500, width=700)