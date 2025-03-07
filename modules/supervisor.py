import streamlit as st
import pandas as pd
import sqlite3
import io
from datetime import datetime
from streamlit_option_menu import option_menu
from modules.cookie_instance import controller  # <-- Importa la instancia central

cookie_name = "my_app"

def log_trazabilidad(usuario, accion, detalles):
    conn = sqlite3.connect("data/usuarios.db")
    cursor = conn.cursor()
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT INTO trazabilidad (usuario_id, accion, detalles, fecha)
        VALUES (?, ?, ?, ?)
    """, (usuario, accion, detalles, fecha))
    conn.commit()
    conn.close()

def supervisor_dashboard():
    st.title("📁 Panel del Supervisor")

    with st.sidebar:
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

        st.sidebar.write(f"Bienvenido, {st.session_state['username']}")
        st.sidebar.markdown("---")
        menu_opcion = option_menu(
            menu_title=None,
            options=["Datos UIS", "Ofertas Comerciales", "Viabilidades"],
            icons=["graph-up", "bar-chart", "check-circle"],
            menu_icon="list",
            default_index=0,
            styles={
                "container": {"padding": "0px", "background-color": "#262730"},
                "icon": {"color": "#ffffff", "font-size": "18px"},
                "nav-link": {
                    "color": "#ffffff", "font-size": "16px", "text-align": "left", "margin": "0px"
                },
                "nav-link-selected": {
                    "background-color": "#0073e6", "color": "white"
                }
            }
        )

    detalles = f"El supervisor seleccionó la vista '{menu_opcion}'."
    log_trazabilidad(st.session_state["username"], "Selección de vista", detalles)

    st.write("Desde aquí puedes visualizar los datos y descargarlos.")

    with st.sidebar:
        if st.button("Cerrar sesión"):
            detalles = f"El supervisor {st.session_state.get('username', 'N/A')} cerró sesión."
            log_trazabilidad(st.session_state.get("username", "N/A"), "Cierre sesión", detalles)

            # Eliminar las cookies si existen
            if controller.get(f'{cookie_name}_username'):
                controller.set(f'{cookie_name}_username', '', max_age=0, path='/')
            if controller.get(f'{cookie_name}_role'):
                controller.set(f'{cookie_name}_role', '', max_age=0, path='/')

            # En lugar de limpiar todo el session_state, reiniciamos las variables críticas
            st.session_state["login_ok"] = False
            st.session_state["username"] = ""
            st.session_state["role"] = ""

            st.success("✅ Has cerrado sesión correctamente. Redirigiendo al login...")
            st.rerun()

    if "data" in st.session_state:
        del st.session_state["data"]

    with st.spinner("Cargando datos... Esto puede tomar unos segundos."):
        try:
            conn = sqlite3.connect("data/usuarios.db")
            query_tables = "SELECT name FROM sqlite_master WHERE type='table';"
            tables = pd.read_sql(query_tables, conn)

            if menu_opcion == "Datos UIS":
                if 'datos_uis' not in tables['name'].values:
                    st.error("❌ La tabla 'datos_uis' no se encuentra en la base de datos.")
                    conn.close()
                    return
                query = "SELECT * FROM datos_uis"
            elif menu_opcion == "Ofertas Comerciales":
                if 'ofertas_comercial' not in tables['name'].values:
                    st.error("❌ La tabla 'ofertas_comercial' no se encuentra en la base de datos.")
                    conn.close()
                    return
                query = "SELECT * FROM ofertas_comercial"
            elif menu_opcion == "Viabilidades":
                if 'viabilidades' not in tables['name'].values:
                    st.error("❌ La tabla 'viabilidades' no se encuentra en la base de datos.")
                    conn.close()
                    return
                query = "SELECT * FROM viabilidades"

            data = pd.read_sql(query, conn)
            conn.close()

            if data.empty:
                st.error("❌ No se encontraron datos en la base de datos.")
                return

        except Exception as e:
            st.error(f"❌ Error al cargar datos de la base de datos: {e}")
            return

    if data.columns.duplicated().any():
        st.warning("¡Se encontraron columnas duplicadas! Se eliminarán las duplicadas.")
        data = data.loc[:, ~data.columns.duplicated()]

    st.session_state["data"] = data

    st.subheader("Filtrar Columnas")
    columnas = st.multiselect("Selecciona las columnas a mostrar", data.columns.tolist(), default=data.columns.tolist())

    st.subheader("Datos Cargados")
    st.dataframe(data[columnas], use_container_width=True)

    st.subheader("Descargar Datos")
    descarga_opcion = st.radio("¿Cómo quieres descargar los datos?", ["CSV", "Excel"])

    if descarga_opcion == "CSV":
        detalles = f"El supervisor descargó los datos en formato CSV."
        log_trazabilidad(st.session_state["username"], "Descarga de datos", detalles)
        st.download_button(
            label="Descargar como CSV",
            data=data[columnas].to_csv(index=False).encode(),
            file_name="viabilidades.csv",
            mime="text/csv"
        )
    elif descarga_opcion == "Excel":
        detalles = f"El supervisor descargó los datos en formato Excel."
        log_trazabilidad(st.session_state["username"], "Descarga de datos", detalles)
        with st.spinner("Generando archivo Excel... Esto puede tardar unos segundos."):
            towrite = io.BytesIO()
            with pd.ExcelWriter(towrite, engine='xlsxwriter') as writer:
                data[columnas].to_excel(writer, index=False, sheet_name="Viabilidades")
            towrite.seek(0)
            st.download_button(
                label="Descargar como Excel",
                data=towrite,
                file_name="viabilidades.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    st.info("Recuerda que, dependiendo del tamaño de los datos, la descarga puede tardar algunos segundos.")

if __name__ == "__main__":
    supervisor_dashboard()
