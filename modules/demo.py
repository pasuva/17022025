import streamlit as st
import pandas as pd
import folium
from folium.plugins import MarkerCluster, Geocoder, Draw
from branca.element import Template, MacroElement
from streamlit_folium import st_folium
import sqlitecloud
import time
from modules import login
from streamlit_cookies_controller import CookieController

cookie_name = "my_app"


# Función para obtener conexión a la base de datos
def get_db_connection():
    return sqlitecloud.connect(
        "sqlitecloud://ceafu04onz.g6.sqlite.cloud:8860/usuarios.db?apikey=Qo9m18B9ONpfEGYngUKm99QB5bgzUTGtK7iAcThmwvY"
    )


def demo_dashboard():
    """Dashboard de demostración para visualización de puntos en mapa"""

    st.set_page_config(page_title="Dashboard Demo - Verde tu Operador", layout="wide")

    st.markdown(
        """
        <style>
        .footer {
            position: fixed;
            left: 0;
            bottom: 0;
            width: 100%;
            background-color: #F7FBF9;
            color: black;
            text-align: center;
            padding: 8px 0;
            font-size: 14px;
            font-family: 'Segoe UI', sans-serif;
            z-index: 999;
        }
        </style>
        <div class="footer">
            <p>© 2025 Verde tu operador · Desarrollado para uso interno</p>
        </div>
        """,
        unsafe_allow_html=True
    )

    # Verificar autenticación
    if "username" not in st.session_state or not st.session_state.get("username"):
        st.warning("⚠️ No has iniciado sesión. Por favor, inicia sesión para continuar.")
        time.sleep(1.5)
        try:
            login.login()
        except Exception:
            pass
        return

    # Verificar que el usuario tenga rol demo
    if st.session_state.get("role") != "demo":
        st.toast("❌ No tienes permisos para acceder al dashboard de demostración.")
        st.toast("🔐 Esta área es solo para usuarios con rol 'demo'")
        with st.sidebar:
            if st.button("Cerrar sesión"):
                controller = CookieController(key="cookies")
                if controller.get(f'{cookie_name}_session_id'):
                    controller.set(f'{cookie_name}_session_id', '', max_age=0, path='/')
                if controller.get(f'{cookie_name}_username'):
                    controller.set(f'{cookie_name}_username', '', max_age=0, path='/')
                if controller.get(f'{cookie_name}_role'):
                    controller.set(f'{cookie_name}_role', '', max_age=0, path='/')
                st.session_state["login_ok"] = False
                st.session_state["username"] = ""
                st.session_state["role"] = ""
                st.session_state["session_id"] = ""
                st.toast("✅ Has cerrado sesión correctamente.")
                st.rerun()
        return

    # --- BARRA LATERAL CON INFO DEL USUARIO ---
    with st.sidebar:
        st.sidebar.markdown("""
            <style>
                .user-circle {
                    width: 100px;
                    height: 100px;
                    border-radius: 50%;
                    background-color: #4CAF50;
                    color: white;
                    font-size: 50px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin: 0 auto 10px auto;
                    text-align: center;
                }
                .user-info {
                    text-align: center;
                    font-size: 16px;
                    color: #333;
                    margin-bottom: 10px;
                }
                .welcome-msg {
                    text-align: center;
                    font-weight: bold;
                    font-size: 18px;
                    margin-top: 0;
                }
            </style>

            <div class="user-circle">👁️</div>
            <div class="user-info">Rol: Demo</div>
            <div class="welcome-msg">Bienvenido, <strong>{username}</strong></div>
            <hr>
            """.replace("{username}", st.session_state.get('username', 'N/A')), unsafe_allow_html=True)

        # Botón de cerrar sesión
        if st.button("🚪 Cerrar sesión"):
            controller = CookieController(key="cookies")
            if controller.get(f'{cookie_name}_session_id'):
                controller.set(f'{cookie_name}_session_id', '', max_age=0, path='/')
            if controller.get(f'{cookie_name}_username'):
                controller.set(f'{cookie_name}_username', '', max_age=0, path='/')
            if controller.get(f'{cookie_name}_role'):
                controller.set(f'{cookie_name}_role', '', max_age=0, path='/')
            st.session_state["login_ok"] = False
            st.session_state["username"] = ""
            st.session_state["role"] = ""
            st.session_state["session_id"] = ""
            st.toast("✅ Has cerrado sesión correctamente.")
            st.rerun()

    # --- CONTENIDO PRINCIPAL ---
    # --- FILTROS ---
    with st.sidebar:
        st.header("🔍 Filtros de Visualización")

        # ACORDEÓN para la información del modo demostración
        with st.expander("ℹ️ Información del Modo Demo", expanded=False):
            st.markdown("""
                **💡 Modo Demostración**

                Este dashboard es solo para visualización y demostraciones. 
                No se permiten modificaciones de datos.

                **Características disponibles:**
                - Visualización de puntos en mapa
                - Filtrado por ubicación geográfica
                - Filtrado por CTO y tipo OLT
                - Selección de área en el mapa
                - Descarga de datos en CSV
                - Estadísticas básicas

                **Restricciones:**
                - No se pueden modificar datos
                - No se pueden crear ofertas comerciales
                - No se pueden gestionar viabilidades
                - No se pueden generar precontratos
                """)

        with st.spinner("⏳ Cargando filtros..."):
            try:
                conn = get_db_connection()
                # Cargar provincias
                provincias = pd.read_sql("SELECT DISTINCT provincia FROM datos_uis ORDER BY provincia", conn)[
                    "provincia"].dropna().tolist()

                # Cargar tipos de OLT rental (solo CTO VERDE y CTO COMPARTIDA)
                tipos_olt = pd.read_sql(
                    "SELECT DISTINCT tipo_olt_rental FROM datos_uis WHERE tipo_olt_rental IS NOT NULL ORDER BY tipo_olt_rental",
                    conn)[
                    "tipo_olt_rental"].dropna().tolist()

                # FILTRAR: Solo permitir CTO VERDE y CTO COMPARTIDA, excluir preventa y otros
                tipos_olt_permitidos = ["CTO VERDE", "CTO COMPARTIDA"]
                tipos_olt = [tipo for tipo in tipos_olt if tipo in tipos_olt_permitidos]

                conn.close()
            except Exception as e:
                st.error(f"❌ Error al cargar filtros: {e}")
                return

        # Filtro de provincia
        provincia_sel = st.selectbox("🌍 Provincia", ["Todas"] + provincias, key="demo_provincia")

        # Filtro de municipio (dependiente de provincia)
        municipios = []
        if provincia_sel != "Todas":
            conn = get_db_connection()
            municipios = pd.read_sql(
                "SELECT DISTINCT municipio FROM datos_uis WHERE provincia = ? ORDER BY municipio",
                conn, params=(provincia_sel,)
            )["municipio"].dropna().tolist()
            conn.close()
        municipio_sel = st.selectbox("🏘️ Municipio", ["Todos"] + municipios,
                                     key="demo_municipio") if municipios else "Todos"

        # Filtro de población (dependiente de municipio)
        poblaciones = []
        if municipio_sel != "Todos":
            conn = get_db_connection()
            poblaciones = pd.read_sql(
                "SELECT DISTINCT poblacion FROM datos_uis WHERE provincia = ? AND municipio = ? ORDER BY poblacion",
                conn, params=(provincia_sel, municipio_sel)
            )["poblacion"].dropna().tolist()
            conn.close()
        poblacion_sel = st.selectbox("🏡 Población", ["Todas"] + poblaciones,
                                     key="demo_poblacion") if poblaciones else "Todas"

        # Filtros avanzados
        st.subheader("Filtros Avanzados")

        # Filtro de CTO (dependiente de provincia, municipio y población)
        ctos = []
        # Construir query para CTOs basado en los filtros seleccionados
        cto_query = "SELECT DISTINCT cto FROM datos_uis WHERE cto IS NOT NULL AND cto != ''"
        cto_params = []

        if provincia_sel != "Todas":
            cto_query += " AND provincia = ?"
            cto_params.append(provincia_sel)
        if municipio_sel != "Todos":
            cto_query += " AND municipio = ?"
            cto_params.append(municipio_sel)
        if poblacion_sel != "Todas":
            cto_query += " AND poblacion = ?"
            cto_params.append(poblacion_sel)

        cto_query += " ORDER BY cto"

        if cto_params:  # Solo ejecutar si hay algún filtro aplicado
            conn = get_db_connection()
            ctos = pd.read_sql(cto_query, conn, params=cto_params)["cto"].dropna().tolist()
            conn.close()
        else:
            # Si no hay filtros, cargar todas las CTOs
            conn = get_db_connection()
            ctos = \
                pd.read_sql("SELECT DISTINCT cto FROM datos_uis WHERE cto IS NOT NULL AND cto != '' ORDER BY cto",
                            conn)[
                    "cto"].dropna().tolist()
            conn.close()

        cto_filter = st.selectbox(
            "📡 CTO",
            ["Todas"] + ctos,
            key="demo_cto"
        )

        # Filtro de Tipo OLT Rental (solo CTO VERDE y CTO COMPARTIDA)
        tipo_olt_filter = st.selectbox(
            "🏢 Tipo OLT Rental",
            ["Todos"] + tipos_olt,
            key="demo_tipo_olt"
        )

        # Botones de acción
        col1, col2 = st.columns(2)
        with col1:
            aplicar_filtros = st.button("🔍 Aplicar Filtros", type="primary", use_container_width=True)
        with col2:
            limpiar_filtros = st.button("🧹 Limpiar", use_container_width=True)

        # Nueva funcionalidad: Filtro por área dibujada - COMPLETAMENTE INDEPENDIENTE
        st.markdown("---")
        st.subheader("🗺️ Filtro por Área")

        st.info(
            "💡 **Filtro independiente:** Este filtro funciona por separado de los filtros de campos anteriores")

        # Inicializar el estado del área dibujada si no existe
        if "drawn_bounds" not in st.session_state:
            st.session_state.drawn_bounds = None
        if "apply_area_filter" not in st.session_state:
            st.session_state.apply_area_filter = False
        if "area_filtered_df" not in st.session_state:
            st.session_state.area_filtered_df = None

        # Mostrar información del área actual si existe
        if st.session_state.drawn_bounds:
            bounds = st.session_state.drawn_bounds
            st.info(f"📍 Área seleccionada: \n"
                    f"Lat: {bounds['south']:.4f} a {bounds['north']:.4f}\n"
                    f"Lon: {bounds['west']:.4f} a {bounds['east']:.4f}")

        # NUEVO: Filtro de tipo OLT para el área
        area_tipo_olt_filter = st.selectbox(
            "🏢 Tipo OLT en el Área",
            ["Todos", "CTO VERDE", "CTO COMPARTIDA"],
            key="area_tipo_olt"
        )

        col3, col4 = st.columns(2)
        with col3:
            if st.button("📍 Cargar datos del área", type="primary", use_container_width=True):
                if st.session_state.drawn_bounds:
                    st.session_state.apply_area_filter = True
                    # Cargar datos específicos del área
                    with st.spinner("⏳ Cargando datos del área..."):
                        try:
                            bounds = st.session_state.drawn_bounds
                            conn = get_db_connection()

                            # Query para cargar datos SOLO del área seleccionada
                            query = """
                                SELECT 
                                    apartment_id, provincia, municipio, poblacion, vial, numero, letra, cp,
                                    latitud, longitud, olt, cto, cto_id, tipo_olt_rental
                                FROM datos_uis 
                                WHERE latitud BETWEEN ? AND ? 
                                  AND longitud BETWEEN ? AND ?
                            """
                            params = [
                                bounds['south'], bounds['north'],
                                bounds['west'], bounds['east']
                            ]

                            # Añadir filtro por tipo OLT si no es "Todos"
                            if area_tipo_olt_filter != "Todos":
                                query += " AND tipo_olt_rental = ?"
                                params.append(area_tipo_olt_filter)
                            else:
                                # Si es "Todos", solo mostrar CTO VERDE y CTO COMPARTIDA (excluir preventa)
                                query += " AND tipo_olt_rental IN ('CTO VERDE', 'CTO COMPARTIDA')"

                            area_df = pd.read_sql(query, conn, params=params)
                            conn.close()

                            if area_df.empty:
                                st.warning("⚠️ No hay datos en el área seleccionada.")
                                st.session_state.area_filtered_df = None
                            else:
                                st.session_state.area_filtered_df = area_df
                                st.session_state.demo_filtered_df = None  # Limpiar filtros de campo
                                st.success(f"✅ Se cargaron {len(area_df)} puntos del área seleccionada")

                        except Exception as e:
                            st.error(f"❌ Error al cargar datos del área: {e}")
                else:
                    st.warning("⚠️ Primero debes dibujar un área en el mapa")

        with col4:
            if st.button("🗑️ Limpiar filtro de área", use_container_width=True):
                st.session_state.apply_area_filter = False
                st.session_state.drawn_bounds = None
                st.session_state.area_filtered_df = None
                st.rerun()

    # --- APLICAR FILTROS DE CAMPOS ---
    if aplicar_filtros:
        with st.spinner("⏳ Cargando datos filtrados..."):
            try:
                conn = get_db_connection()
                query = """
                    SELECT 
                        apartment_id, provincia, municipio, poblacion, vial, numero, letra, cp,
                        latitud, longitud, olt, cto, cto_id, tipo_olt_rental
                    FROM datos_uis 
                    WHERE 1=1
                """
                params = []

                if provincia_sel != "Todas":
                    query += " AND provincia = ?"
                    params.append(provincia_sel)
                if municipio_sel != "Todos":
                    query += " AND municipio = ?"
                    params.append(municipio_sel)
                if poblacion_sel != "Todas":
                    query += " AND poblacion = ?"
                    params.append(poblacion_sel)
                if cto_filter != "Todas":
                    query += " AND cto = ?"
                    params.append(cto_filter)
                if tipo_olt_filter != "Todos":
                    query += " AND tipo_olt_rental = ?"
                    params.append(tipo_olt_filter)

                df = pd.read_sql(query, conn, params=params)
                conn.close()

                if df.empty:
                    st.warning("⚠️ No hay datos para los filtros seleccionados.")
                    st.session_state.demo_filtered_df = None
                    st.session_state.area_filtered_df = None  # Limpiar filtro de área
                else:
                    st.session_state.demo_filtered_df = df
                    st.session_state.area_filtered_df = None  # Limpiar filtro de área
                    st.success(f"✅ Se cargaron {len(df)} puntos en el mapa")

            except Exception as e:
                st.error(f"❌ Error al cargar los datos: {e}")

    # --- LIMPIAR FILTROS ---
    if limpiar_filtros:
        if "demo_filtered_df" in st.session_state:
            del st.session_state.demo_filtered_df
        if "apply_area_filter" in st.session_state:
            st.session_state.apply_area_filter = False
        if "drawn_bounds" in st.session_state:
            st.session_state.drawn_bounds = None
        if "area_filtered_df" in st.session_state:
            del st.session_state.area_filtered_df
        st.rerun()

    # --- VISUALIZACIÓN DEL MAPA ---
    # Determinar qué datos mostrar - FILTROS INDEPENDIENTES
    df_to_show = None

    # Prioridad: 1. Filtro por área, 2. Filtros de campos
    if st.session_state.get("area_filtered_df") is not None:
        df_to_show = st.session_state.area_filtered_df
        st.info("📊 **Visualizando:** Datos filtrados por ÁREA GEOGRÁFICA")
    elif st.session_state.get("demo_filtered_df") is not None:
        df_to_show = st.session_state.demo_filtered_df
        st.info("📊 **Visualizando:** Datos filtrados por CAMPOS")
    else:
        st.info("👆 **Selecciona un método de filtrado:** Usa los filtros de campos o dibuja un área en el mapa")

    # --- DEBUG GEO EN BARRA LATERAL ---
    with st.sidebar:
        # Solo mostrar debug si hay datos
        if df_to_show is not None:
            # Verificar coordenadas en el área seleccionada
            bounds = st.session_state.get("drawn_bounds")
            if bounds:
                lat_min, lat_max = bounds['south'], bounds['north']
                lon_min, lon_max = bounds['west'], bounds['east']

                # Contar puntos en el área (si estamos usando filtro de área)
                if st.session_state.get("area_filtered_df") is not None:
                    in_area = df_to_show[
                        (df_to_show['latitud'] >= lat_min) &
                        (df_to_show['latitud'] <= lat_max) &
                        (df_to_show['longitud'] >= lon_min) &
                        (df_to_show['longitud'] <= lon_max)
                        ]

            # Verificar calidad de datos geográficos
            null_lat = df_to_show['latitud'].isnull().sum()
            null_lon = df_to_show['longitud'].isnull().sum()

            # Verificar coordenadas fuera de rango (para España)
            invalid_coords = df_to_show[
                (df_to_show['latitud'] < 35) | (df_to_show['latitud'] > 44) |
                (df_to_show['longitud'] < -10) | (df_to_show['longitud'] > 5)
                ]
    if df_to_show is not None:
        df_display = df_to_show

        # Configuración del mapa
        if len(df_display) == 1:
            lat, lon = df_display['latitud'].iloc[0], df_display['longitud'].iloc[0]
            m = folium.Map(location=[lat, lon], zoom_start=18, max_zoom=21,
                           tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}", attr="Google")
        else:
            lat, lon = df_display['latitud'].mean(), df_display['longitud'].mean()
            m = folium.Map(location=[lat, lon], zoom_start=12, max_zoom=21,
                           tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}", attr="Google")
            bounds_data = [[df_display['latitud'].min(), df_display['longitud'].min()],
                           [df_display['latitud'].max(), df_display['longitud'].max()]]
            m.fit_bounds(bounds_data)

        # Añadir geocoder para búsqueda
        Geocoder().add_to(m)

        # Añadir herramientas de dibujo
        draw_options = {
            'rectangle': {
                'shapeOptions': {
                    'color': '#3388ff',
                    'fillColor': '#3388ff',
                    'fillOpacity': 0.2
                }
            },
            'polygon': {
                'shapeOptions': {
                    'color': '#3388ff',
                    'fillColor': '#3388ff',
                    'fillOpacity': 0.2
                }
            },
            'circle': False,
            'marker': False,
            'circlemarker': False,
            'polyline': False
        }

        draw = Draw(
            export=False,
            position="topleft",
            draw_options=draw_options
        )
        draw.add_to(m)

        # Capa de clusters para muchos puntos
        if len(df_display) < 500:
            cluster_layer = m
        else:
            cluster_layer = MarkerCluster(maxClusterRadius=5, minClusterSize=3).add_to(m)

        # Añadir marcadores
        coord_counts = {}
        for _, row in df_display.iterrows():
            coord = (row['latitud'], row['longitud'])
            coord_counts[coord] = coord_counts.get(coord, 0) + 1

        for _, row in df_display.iterrows():
            # Determinar color del marcador solo por tipo OLT
            tipo_olt_val = str(row.get("tipo_olt_rental", "")).strip()

            if tipo_olt_val == "CTO VERDE":
                marker_color = 'darkgreen'
            elif tipo_olt_val == "CTO COMPARTIDA":
                marker_color = 'purple'
            else:
                # Para otros tipos, usar gris para que no aparezca en la leyenda
                marker_color = 'gray'

            # Texto del popup (simplificado - solo información esencial)
            popup_text = f"""
            <div style="min-width: 250px">
                <h4>🏢 ID: {row['apartment_id']}</h4>
                <hr>
                <b>📍 Ubicación:</b><br>
                {row['provincia']}, {row['municipio']}<br>
                {row['vial']} {row['numero']}{row['letra'] or ''}<br>
                CP: {row['cp']}<br>
                📍 {row['latitud']:.6f}, {row['longitud']:.6f}<br>
                <br>
                <b>🔧 Infraestructura:</b><br>
                🏢 OLT: {row.get('olt', 'N/D')}<br>
                📡 CTO: {row.get('cto', 'N/D')}<br>
                🔢 CTO ID: {row.get('cto_id', 'N/D')}<br>
                🏭 Tipo OLT: {row.get('tipo_olt_rental', 'N/D')}<br>
            </div>
            """

            # Ajustar posición para marcadores superpuestos
            coord = (row['latitud'], row['longitud'])
            offset_factor = coord_counts[coord]
            if offset_factor > 1:
                lat_offset = offset_factor * 0.00003
                lon_offset = offset_factor * -0.00003
            else:
                lat_offset, lon_offset = 0, 0

            new_lat = row['latitud'] + lat_offset
            new_lon = row['longitud'] + lon_offset
            coord_counts[coord] -= 1

            # Añadir marcadores
            folium.Marker(
                location=[new_lat, new_lon],
                popup=folium.Popup(popup_text, max_width=300),
                tooltip=f"🏢 {row['apartment_id']} - {row['vial']} {row['numero']}",
                icon=folium.Icon(color=marker_color, icon='info-sign')
            ).add_to(cluster_layer)

        # Añadir leyenda simplificada (solo CTO VERDE y CTO COMPARTIDA)
        legend = """
            {% macro html(this, kwargs) %}
            <div style="
                position: fixed; 
                bottom: 50px; left: 50px; width: 180px; 
                z-index:9999; 
                font-size:14px;
                background-color: white;
                color: black;
                border:2px solid grey;
                border-radius:8px;
                padding: 10px;
                box-shadow: 2px 2px 6px rgba(0,0,0,0.3);
            ">
            <b>🎨 Leyenda de Colores</b><br>
            <i style="color:darkgreen;">●</i> CTO VERDE<br>
            <i style="color:purple;">●</i> CTO COMPARTIDA<br>
            </div>
            {% endmacro %}
        """
        macro = MacroElement()
        macro._template = Template(legend)
        m.get_root().add_child(macro)

        # Mostrar mapa y capturar interacciones
        with st.spinner("⏳ Renderizando mapa..."):
            map_data = st_folium(
                m,
                height=700,
                width="100%",
                key="demo_map",
                returned_objects=["last_active_drawing", "bounds"]
            )

        # **PROCESAMIENTO DEL ÁREA DIBUJADA**
        if (map_data and map_data.get("last_active_drawing") and
                map_data["last_active_drawing"].get("geometry")):

            geometry = map_data["last_active_drawing"]["geometry"]

            if geometry["type"] in ["Polygon", "Rectangle"]:
                # Para Polygon y Rectangle, las coordenadas están anidadas
                if geometry["type"] == "Polygon":
                    coords = geometry["coordinates"][0]  # Primer anillo del polígono
                else:  # Rectangle
                    coords = geometry["coordinates"][0]

                lats = [coord[1] for coord in coords]
                lons = [coord[0] for coord in coords]

                new_bounds = {
                    'north': max(lats),
                    'south': min(lats),
                    'east': max(lons),
                    'west': min(lons)
                }

                # Actualizar estado
                st.session_state.drawn_bounds = new_bounds

                # Mostrar información detallada
                st.toast(f"""
                📍 Área seleccionada: 
                Lat: {new_bounds['south']:.4f} a {new_bounds['north']:.4f}
                Lon: {new_bounds['west']:.4f} a {new_bounds['east']:.4f}
                """)

        # --- TABLA DE DATOS ---
        st.subheader("📋 Datos Detallados")

        # Seleccionar columnas para mostrar (solo información esencial)
        columnas_mostrar = [
            'apartment_id', 'provincia', 'municipio', 'poblacion', 'vial', 'numero', 'letra', 'cp',
            'olt', 'cto', 'cto_id', 'tipo_olt_rental', 'latitud', 'longitud'
        ]

        df_table_display = df_display[columnas_mostrar].copy()
        st.dataframe(df_table_display, use_container_width=True)

        # Botón de descarga
        csv = df_table_display.to_csv(index=False)
        st.download_button(
            label="📥 Descargar datos como CSV",
            data=csv,
            file_name=f"datos_demo_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
        )

    else:
        # Mapa vacío inicial
        m = folium.Map(location=[40.4168, -3.7038], zoom_start=6, max_zoom=21,
                       tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}", attr="Google")
        Geocoder().add_to(m)

        # Añadir herramientas de dibujo incluso cuando no hay datos
        draw_options = {
            'rectangle': {
                'shapeOptions': {
                    'color': '#3388ff',
                    'fillColor': '#3388ff',
                    'fillOpacity': 0.2
                }
            },
            'polygon': {
                'shapeOptions': {
                    'color': '#3388ff',
                    'fillColor': '#3388ff',
                    'fillOpacity': 0.2
                }
            },
            'circle': False,
            'marker': False,
            'circlemarker': False,
            'polyline': False
        }

        draw = Draw(
            export=False,
            position="topleft",
            draw_options=draw_options
        )
        draw.add_to(m)

        # Mostrar mapa y capturar dibujos incluso sin datos
        map_data = st_folium(
            m,
            height=500,
            width="100%",
            key="demo_map_empty",
            returned_objects=["last_active_drawing", "bounds"]
        )

        # Procesar área dibujada incluso sin datos para pre-cargar el estado
        if (map_data and map_data.get("last_active_drawing") and
                map_data["last_active_drawing"].get("geometry")):

            geometry = map_data["last_active_drawing"]["geometry"]
            if geometry["type"] in ["Polygon", "Rectangle"]:
                # Para Polygon y Rectangle, las coordenadas están anidadas
                if geometry["type"] == "Polygon":
                    coords = geometry["coordinates"][0]  # Primer anillo del polígono
                else:  # Rectangle
                    coords = geometry["coordinates"][0]

                lats = [coord[1] for coord in coords]
                lons = [coord[0] for coord in coords]

                new_bounds = {
                    'north': max(lats),
                    'south': min(lats),
                    'east': max(lons),
                    'west': min(lons)
                }

                st.session_state.drawn_bounds = new_bounds
                st.toast(f"""
                📍 Área seleccionada: 
                Lat: {new_bounds['south']:.4f} a {new_bounds['north']:.4f}
                Lon: {new_bounds['west']:.4f} a {new_bounds['east']:.4f}

                Haz clic en 'Cargar datos del área' para ver los puntos en esta zona
                """)


if __name__ == "__main__":
    demo_dashboard()