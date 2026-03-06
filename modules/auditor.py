# auditor.py
# Módulo para auditoría de facturación comparando contratos internos con fichero del partner.

import streamlit as st
import pandas as pd
import io, sqlite3
import sqlitecloud
from datetime import datetime
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
import warnings
warnings.filterfilterwarnings("ignore", category=UserWarning)

# -------------------------------------------------------------------
# Funciones de conexión y trazabilidad (copiadas del main para autonomía)
# -------------------------------------------------------------------
def obtener_conexion():
    """Retorna una nueva conexión a la base de datos SQLite Cloud."""
    try:
        conn = sqlitecloud.connect(
            "sqlitecloud://ceafu04onz.g6.sqlite.cloud:8860/usuarios.db?apikey=Qo9m18B9ONpfEGYngUKm99QB5bgzUTGtK7iAcThmwvY"
        )
        return conn
    except sqlite3.Error as e:
        print(f"Error al conectar con la base de datos: {e}")
        return None

def log_trazabilidad(usuario, accion, detalles):
    """Inserta un registro en la tabla de trazabilidad (opcional)."""
    try:
        conn = obtener_conexion()
        cursor = conn.cursor()
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT INTO trazabilidad (usuario_id, accion, detalles, fecha)
            VALUES (?, ?, ?, ?)
        """, (usuario, accion, detalles, fecha))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error registrando trazabilidad: {e}")

# -------------------------------------------------------------------
# Carga de datos desde la base de datos (seguimiento_contratos)
# -------------------------------------------------------------------
@st.cache_data(ttl=600, show_spinner="Cargando contratos desde la BD...")
def cargar_contratos_bd() -> pd.DataFrame:
    """Carga todos los registros de la tabla seguimiento_contratos."""
    conn = obtener_conexion()
    if conn is None:
        st.error("No se pudo conectar a la base de datos.")
        return pd.DataFrame()
    try:
        query = "SELECT * FROM seguimiento_contratos"
        df = pd.read_sql(query, conn)
        # Normalizar nombres de columnas a minúsculas para facilitar manejo
        df.columns = [c.lower() for c in df.columns]
        return df
    except Exception as e:
        st.error(f"Error al cargar contratos: {e}")
        return pd.DataFrame()
    finally:
        conn.close()

# -------------------------------------------------------------------
# Procesamiento de la comparación
# -------------------------------------------------------------------
def procesar_comparacion(df_bd: pd.DataFrame, df_partner: pd.DataFrame, col_id: str = "billing"):
    """
    Compara dos DataFrames usando la columna 'billing' como identificador.
    Devuelve tres DataFrames: coincidentes, solo_bd, solo_partner.
    """
    if df_bd.empty or df_partner.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    # Asegurar que la columna existe en ambos
    if col_id not in df_bd.columns:
        st.error(f"La columna '{col_id}' no existe en los datos de la base de datos.")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    if col_id not in df_partner.columns:
        st.error(f"La columna '{col_id}' no existe en el fichero subido.")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    # Normalizar a string y limpiar espacios
    df_bd[col_id] = df_bd[col_id].astype(str).str.strip()
    df_partner[col_id] = df_partner[col_id].astype(str).str.strip()

    # Realizar merge para identificar coincidencias
    merged = df_bd.merge(df_partner, on=col_id, how='outer', indicator=True)

    coincidentes = merged[merged['_merge'] == 'both']
    solo_bd = merged[merged['_merge'] == 'left_only']
    solo_partner = merged[merged['_merge'] == 'right_only']

    # Eliminar columna auxiliar
    coincidentes = coincidentes.drop(columns=['_merge'])
    solo_bd = solo_bd.drop(columns=['_merge'])
    solo_partner = solo_partner.drop(columns=['_merge'])

    return coincidentes, solo_bd, solo_partner

# -------------------------------------------------------------------
# Función principal de la sección de auditoría
# -------------------------------------------------------------------
def mostrar_auditoria():
    """Página de auditoría de facturación: comparación con fichero del partner."""

    st.markdown("""
        <style>
        .block-container { padding-top: 1rem; }
        </style>
    """, unsafe_allow_html=True)

    # Submenú horizontal (similar al estilo de otras secciones)
    sub_seccion = st.radio(
        "Selecciona una vista",
        ["Cargar fichero", "Informe comparativo"],
        horizontal=True,
        label_visibility="collapsed"
    )

    # Cargar datos de la BD (cacheados)
    df_bd = cargar_contratos_bd()

    if df_bd.empty:
        st.warning("No se pudieron cargar contratos desde la base de datos.")
        return

    # Mostrar información básica de la BD
    st.sidebar.markdown("### 📊 Datos internos")
    st.sidebar.info(f"Total contratos en BD: **{len(df_bd):,}**")
    if 'billing' in df_bd.columns:
        st.sidebar.info(f"Billing no nulos: **{df_bd['billing'].notna().sum():,}**")
    else:
        st.sidebar.warning("La columna 'billing' no existe en la BD.")

    # -------------------------------------------------------------------
    # Pestaña 1: Cargar fichero del partner
    # -------------------------------------------------------------------
    if sub_seccion == "Cargar fichero":
        st.header("📁 Cargar fichero del partner")
        st.markdown("Sube el archivo Excel o CSV que has recibido del partner. Debe contener una columna llamada **billing** como identificador.")

        uploaded_file = st.file_uploader(
            "Selecciona archivo",
            type=["xlsx", "xls", "csv"],
            key="auditor_file"
        )

        if uploaded_file is not None:
            try:
                # Leer según extensión
                if uploaded_file.name.endswith('.csv'):
                    df_partner = pd.read_csv(uploaded_file)
                else:
                    df_partner = pd.read_excel(uploaded_file)

                # Normalizar nombres de columnas a minúsculas
                df_partner.columns = [c.lower() for c in df_partner.columns]

                st.success(f"Fichero cargado correctamente: {len(df_partner)} filas.")
                st.dataframe(df_partner.head(10), width='stretch')

                # Guardar en session_state para usarlo en la otra pestaña
                st.session_state['df_partner'] = df_partner
                st.session_state['partner_filename'] = uploaded_file.name

                st.info("Ahora ve a la pestaña **Informe comparativo** para ver el análisis.")
            except Exception as e:
                st.error(f"Error al leer el archivo: {e}")

    # -------------------------------------------------------------------
    # Pestaña 2: Informe comparativo
    # -------------------------------------------------------------------
    else:  # sub_seccion == "Informe comparativo"
        st.header("📋 Informe comparativo")

        # Verificar si tenemos datos del partner
        if 'df_partner' not in st.session_state or st.session_state['df_partner'] is None:
            st.warning("Primero debes cargar un fichero del partner en la pestaña 'Cargar fichero'.")
            return

        df_partner = st.session_state['df_partner']
        partner_filename = st.session_state.get('partner_filename', 'fichero_partner')

        # Realizar la comparación
        with st.spinner("Comparando datos..."):
            coincidentes, solo_bd, solo_partner = procesar_comparacion(df_bd, df_partner, col_id='billing')

        # -------------------------------------------------------------------
        # Métricas resumen
        # -------------------------------------------------------------------
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Contratos en BD", len(df_bd))
        with col2:
            st.metric("Registros partner", len(df_partner))
        with col3:
            st.metric("Coincidentes", len(coincidentes))
        with col4:
            st.metric("Solo en BD", len(solo_bd))
        st.caption(f"Solo en partner: {len(solo_partner)}")

        # -------------------------------------------------------------------
        # Pestañas para cada categoría
        # -------------------------------------------------------------------
        if len(coincidentes) > 0 or len(solo_bd) > 0 or len(solo_partner) > 0:
            tab1, tab2, tab3 = st.tabs([
                f"✅ Coincidentes ({len(coincidentes)})",
                f"🔵 Solo en BD ({len(solo_bd)})",
                f"🟠 Solo en partner ({len(solo_partner)})"
            ])

            # Función auxiliar para mostrar tabla con AgGrid
            def mostrar_tabla_con_aggrid(df, key_suffix):
                if df.empty:
                    st.info("No hay registros en esta categoría.")
                    return
                # Seleccionar columnas para mostrar (podríamos permitir elegir)
                cols_mostrar = df.columns.tolist()
                # Si hay muchas columnas, limitar a las más relevantes
                columnas_importantes = ['billing', 'num_contrato', 'cliente', 'estado', 'fecha_inicio_contrato', 'comercial']
                cols_mostrar = [c for c in columnas_importantes if c in df.columns] + [c for c in cols_mostrar if c not in columnas_importantes][:5]
                df_display = df[cols_mostrar].copy()

                gb = GridOptionsBuilder.from_dataframe(df_display)
                gb.configure_default_column(
                    filter=True,
                    floatingFilter=True,
                    sortable=True,
                    resizable=True,
                    minWidth=100,
                    flex=1
                )
                gb.configure_pagination(paginationAutoPageSize=True)
                gridOptions = gb.build()

                AgGrid(
                    df_display,
                    gridOptions=gridOptions,
                    enable_enterprise_modules=True,
                    update_mode=GridUpdateMode.NO_UPDATE,
                    height=400,
                    theme='alpine-dark',
                    key=f"grid_{key_suffix}"
                )

            with tab1:
                mostrar_tabla_con_aggrid(coincidentes, "coincidentes")
            with tab2:
                mostrar_tabla_con_aggrid(solo_bd, "solo_bd")
            with tab3:
                mostrar_tabla_con_aggrid(solo_partner, "solo_partner")

            # -------------------------------------------------------------------
            # Botones de descarga
            # -------------------------------------------------------------------
            col_d1, col_d2, col_d3 = st.columns(3)
            with col_d1:
                # Descargar informe completo Excel
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df_bd.to_excel(writer, sheet_name='Contratos_BD', index=False)
                    df_partner.to_excel(writer, sheet_name='Fichero_Partner', index=False)
                    coincidentes.to_excel(writer, sheet_name='Coincidentes', index=False)
                    solo_bd.to_excel(writer, sheet_name='Solo_BD', index=False)
                    solo_partner.to_excel(writer, sheet_name='Solo_Partner', index=False)
                output.seek(0)

                st.download_button(
                    label="📥 Descargar informe completo (Excel)",
                    data=output,
                    file_name=f"auditoria_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )

            with col_d2:
                # Descargar solo discrepancias (solo BD y solo partner)
                output_disc = io.BytesIO()
                with pd.ExcelWriter(output_disc, engine='xlsxwriter') as writer:
                    solo_bd.to_excel(writer, sheet_name='Solo_BD', index=False)
                    solo_partner.to_excel(writer, sheet_name='Solo_Partner', index=False)
                output_disc.seek(0)

                st.download_button(
                    label="📥 Descargar solo discrepancias",
                    data=output_disc,
                    file_name=f"discrepancias_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )

            with col_d3:
                if st.button("🔄 Refrescar datos de BD", use_container_width=True):
                    st.cache_data.clear()
                    st.rerun()

        else:
            st.info("No hay datos para mostrar tras la comparación.")

        # -------------------------------------------------------------------
        # Análisis adicional: estados de los coincidentes
        # -------------------------------------------------------------------
        if len(coincidentes) > 0 and 'estado' in coincidentes.columns:
            with st.expander("🔍 Análisis de estados en los coincidentes"):
                st.markdown("Distribución de estados de los contratos que sí aparecen en el fichero del partner:")
                estado_counts = coincidentes['estado'].value_counts().reset_index()
                estado_counts.columns = ['Estado', 'Cantidad']
                st.dataframe(estado_counts, width='stretch', hide_index=True)

                # Posible alerta: si hay estados no facturables (ej. 'Cancelado', 'Resuelto')
                estados_no_facturables = ['Cancelado', 'Resuelto', 'Anulado']
                problematicos = coincidentes[coincidentes['estado'].isin(estados_no_facturables)]
                if not problematicos.empty:
                    st.warning(f"⚠️ Se encontraron {len(problematicos)} contratos con estado no facturable en los coincidentes. Revisa si se está cobrando indebidamente.")
                    st.dataframe(problematicos[['billing', 'num_contrato', 'estado']], width='stretch')

        # Registrar en trazabilidad
        log_trazabilidad(
            st.session_state.get("username", "auditor"),
            "Auditoría de facturación",
            f"Comparación realizada con fichero {partner_filename}. Coincidentes={len(coincidentes)}, Solo BD={len(solo_bd)}, Solo Partner={len(solo_partner)}"
        )

# -------------------------------------------------------------------
# Para pruebas independientes (descomentar si se ejecuta solo)
# -------------------------------------------------------------------
# if __name__ == "__main__":
#     st.set_page_config(page_title="Auditoría de facturación", layout="wide")
#     mostrar_auditoria()