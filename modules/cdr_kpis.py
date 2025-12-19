# cdr_kpis.py
from datetime import datetime

import pandas as pd
import gspread
import os
import json
import streamlit as st
from google.oauth2.service_account import Credentials
# Añadir al principio del archivo, después de los imports existentes:
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib import colors
from reportlab.lib.units import inch
import tempfile

# ==================== CONFIGURACIÓN DEPARTAMENTAL ====================
# Diccionario de mapeo: Extensión -> Departamento
MAPEO_DEPARTAMENTOS = {
    '1001': 'Administración',
    '1002': 'Comercial',
    '1003': 'Soporte Técnico',
    # Añade aquí todas las extensiones que conozcas
}


def asignar_departamento(numero):
    """Asigna un departamento a un número de extensión o externo."""
    # Busca en el mapeo
    if str(numero) in MAPEO_DEPARTAMENTOS:
        return MAPEO_DEPARTAMENTOS[str(numero)]
    # Heurística para números externos (ajústala)
    elif str(numero).isdigit() and len(str(numero)) >= 9:
        return 'Externo (Teléfono)'
    elif str(numero).startswith('s') or str(numero) == 's':  # Como en tu ejemplo
        return 'Servicio/IVR'
    else:
        return 'Desconocido/Externo'


def clasificar_interaccion(fila):
    """Clasifica el tipo de interacción entre departamentos."""
    origen = fila['dept_origen']
    destino = fila['dept_destino']

    if origen == destino and origen in ['Administración', 'Comercial', 'Soporte Técnico']:
        return 'Interna (mismo dept)'
    elif origen in ['Administración', 'Comercial', 'Soporte Técnico'] and destino in ['Administración', 'Comercial',
                                                                                      'Soporte Técnico']:
        return 'Colaboración (dept a dept)'
    elif origen in ['Administración', 'Comercial', 'Soporte Técnico'] and destino == 'Externo (Teléfono)':
        return 'Llamada Saliente'
    elif origen == 'Externo (Teléfono)' and destino in ['Administración', 'Comercial', 'Soporte Técnico']:
        return 'Llamada Entrante'
    else:
        return 'Otra'

def cargar_y_procesar_cdr():
    try:
        # --- Detectar entorno y elegir archivo de credenciales ---
        # (Usamos la misma lógica que en cargar_contratos_google)
        posibles_rutas = [
            "modules/carga-contratos-verde-c5068516c7cf.json",  # Render: secret file
            "/etc/secrets/carga-contratos-verde-c5068516c7cf.json",  # Otra ruta posible en Render
            os.path.join(os.path.dirname(__file__), "carga-contratos-verde-c5068516c7cf.json"),  # Local
        ]

        ruta_credenciales = None
        for r in posibles_rutas:
            if os.path.exists(r):
                ruta_credenciales = r
                break

        if not ruta_credenciales and "GOOGLE_APPLICATION_CREDENTIALS_JSON" in os.environ:
            # Si no hay archivo pero sí variable de entorno
            creds_dict = json.loads(os.environ["GOOGLE_APPLICATION_CREDENTIALS_JSON"])
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
            creds = Credentials.from_service_account_info(creds_dict, scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive"
            ])
        elif ruta_credenciales:
            print(f"🔑 Usando credenciales desde: {ruta_credenciales}")
            creds = Credentials.from_service_account_file(
                ruta_credenciales,
                scopes=[
                    "https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive"
                ]
            )
        else:
            raise ValueError("❌ No se encontraron credenciales de Google Service Account.")

        # Crear cliente
        client = gspread.authorize(creds)

        # --- Abrir la hoja de Google Sheets del CDR ---
        # NOTA: Debes ajustar el nombre de la hoja y la pestaña según tu caso
        sheet = client.open("CDR VERDE PBX").worksheet("CDR VERDE PBX")
        data = sheet.get_all_records()

        if not data:
            print("⚠️ Hoja cargada pero sin registros. Revisa si la primera fila tiene encabezados correctos.")
            return pd.DataFrame(), {}

        df = pd.DataFrame(data)

        # --- Procesamiento específico del CDR ---
        # 1. Normalizar nombres de columnas (como en tu función de contratos)
        df.columns = df.columns.map(lambda x: str(x).strip().upper() if x is not None else "")

        # 2. Mapeo de columnas a nombres más manejables (opcional, pero recomendable)
        # Aquí debes definir el mapeo según las columnas de tu CDR.
        # Ejemplo basado en la muestra que mostraste:
        column_mapping = {
            'CALLDATE': 'calldate',
            'CLID': 'clid',
            'SRC': 'src',
            'DST': 'dst',
            'DCONTEXT': 'dcontext',
            'CHANNEL': 'channel',
            'DSTCHANNEL': 'dstchannel',
            'LASTAPP': 'lastapp',
            'LASTDATA': 'lastdata',
            'DURATION': 'duration',
            'BILLSEC': 'billsec',
            'DISPOSITION': 'disposition',
            'AMAFLAGS': 'amaflags',
            'ACCOUNTCODE': 'accountcode',
            'UNIQUEID': 'uniqueid',
            'USERFIELD': 'userfield',
            'DID': 'did',
            'CNUM': 'cnum',
            'CNAM': 'cnam',
            'OUTBOUND_CNUM': 'outbound_cnum',
            'OUTBOUND_CNAM': 'outbound_cnam',
            'DST_CNAM': 'dst_cnam',
            'RECORDINGFILE': 'recordingfile',
            'LINKEDID': 'linkedid',
            'PEERACCOUNT': 'peeraccount',
            'SEQUENCE': 'sequence'
        }

        # Renombrar las columnas según el mapeo (solo las que existan)
        df.rename(columns={col: column_mapping[col] for col in column_mapping if col in df.columns}, inplace=True)

        # 3. Convertir tipos de datos
        if 'calldate' in df.columns:
            df['calldate'] = pd.to_datetime(df['calldate'], dayfirst=True, errors='coerce')

        # Convertir columnas numéricas
        numeric_cols = ['duration', 'billsec']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        # 4. Calcular KPIs
        kpis = calcular_kpis_cdr(df)

        return df, kpis

    except Exception as e:
        print(f"❌ Error en cargar_y_procesar_cdr: {e}")
        return None, None


# ==================== FUNCIONES DE CÁLCULO DE KPIS ====================
def calcular_kpis_cdr(df):
    if df.empty:
        return {}

    kpis = {
        'total_llamadas': len(df),
        'llamadas_contestadas': len(df[df['disposition'] == 'ANSWERED']) if 'disposition' in df.columns else 0,
        'llamadas_no_contestadas': len(
            df[df['disposition'].isin(['NO ANSWER', 'BUSY', 'FAILED'])]) if 'disposition' in df.columns else 0,
        'duracion_total_segundos': df['duration'].sum() if 'duration' in df.columns else 0,
        'duracion_promedio_segundos': df['duration'].mean() if 'duration' in df.columns else 0,
        'facturacion_total_segundos': df['billsec'].sum() if 'billsec' in df.columns else 0,
        'extensiones_unicas': df['src'].nunique() if 'src' in df.columns else 0,
    }

    # Si hay columna de fecha, agregar KPIs por tiempo
    if 'calldate' in df.columns and not df['calldate'].isnull().all():
        df['fecha'] = df['calldate'].dt.date
        llamadas_por_dia = df.groupby('fecha').size().to_dict()
        kpis['llamadas_por_dia'] = llamadas_por_dia

    return kpis


def calcular_kpis_cdr_ampliada(df):
    if df.empty:
        return {}

    # 1. Comienza con los KPIs básicos que ya tenías
    kpis = calcular_kpis_cdr(df)

    # 2. KPIs de EFICIENCIA OPERATIVA
    # Tasa de respuesta y abandono
    if 'disposition' in df.columns:
        total = len(df)
        contestadas = len(df[df['disposition'] == 'ANSWERED'])
        no_contestadas = len(df[df['disposition'].isin(['NO ANSWER', 'BUSY'])])
        fallidas = len(df[df['disposition'] == 'FAILED'])

        kpis['tasa_respuesta'] = (contestadas / total * 100) if total > 0 else 0
        kpis['tasa_abandono'] = (no_contestadas / total * 100) if total > 0 else 0
        kpis['llamadas_fallidas'] = fallidas

    # 3. KPIs de DISTRIBUCIÓN TEMPORAL (Patrones de uso)
    if 'calldate' in df.columns:
        df['hora'] = df['calldate'].dt.hour
        df['dia_semana'] = df['calldate'].dt.day_name()
        df['es_fin_semana'] = df['calldate'].dt.weekday >= 5  # 5=Sábado, 6=Domingo

        # Llamadas por franja horaria (para identificar picos)
        llamadas_por_hora = df.groupby('hora').size()
        kpis['llamadas_por_hora_dict'] = llamadas_por_hora.to_dict()
        kpis['hora_pico'] = llamadas_por_hora.idxmax() if not llamadas_por_hora.empty else None
        kpis['llamadas_hora_pico'] = llamadas_por_hora.max() if not llamadas_por_hora.empty else 0

        # Llamadas por día de la semana
        dias_orden = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        llamadas_por_dia = df['dia_semana'].value_counts()
        llamadas_por_dia = llamadas_por_dia.reindex(dias_orden, fill_value=0)
        kpis['llamadas_por_dia_dict'] = llamadas_por_dia.to_dict()
        kpis['dia_mas_activo'] = llamadas_por_dia.idxmax() if not llamadas_por_dia.empty else None

        # Distribución fin de semana vs. laborable
        kpis['llamadas_fin_semana'] = df['es_fin_semana'].sum()
        kpis['llamadas_laborables'] = len(df) - kpis['llamadas_fin_semana']

    # 4. KPIs de ANÁLISIS DE ORIGEN Y DESTINO
    if 'src' in df.columns:
        # Top extensiones que más llaman
        top_origen = df['src'].value_counts().head(10)
        kpis['top_origen_dict'] = top_origen.to_dict()
        kpis['extension_mas_activa'] = top_origen.index[0] if not top_origen.empty else None
        kpis['llamadas_extension_top'] = top_origen.iloc[0] if not top_origen.empty else 0

    if 'dst' in df.columns:
        # Top destinos más llamados
        top_destino = df['dst'].value_counts().head(10)
        kpis['top_destino_dict'] = top_destino.to_dict()
        kpis['destino_mas_frecuente'] = top_destino.index[0] if not top_destino.empty else None

        # Identificar si la llamada fue interna (ambos extremos son extensiones) o externa
        def es_extension(x):
            try:
                return str(x).isdigit() and 1000 <= int(x) <= 9999  # Ejemplo: extensiones de 4 dígitos
            except:
                return False

        # Contar llamadas internas (src y dst son extensiones)
        df['es_interna'] = df.apply(lambda fila: es_extension(fila.get('src')) and es_extension(fila.get('dst')),
                                    axis=1)
        kpis['llamadas_internas'] = df['es_interna'].sum()
        kpis['llamadas_externas'] = len(df) - kpis['llamadas_internas']

    # 5. KPIs de FACTURACIÓN Y COSTE (si aplica)
    if 'billsec' in df.columns:
        # Tiempo total facturable (en minutos, para mayor claridad)
        kpis['minutos_facturables'] = df['billsec'].sum() / 60.0

        # Relación entre duración real y tiempo facturado (para eficiencia)
        if 'duration' in df.columns:
            # Evitar división por cero: usar sólo llamadas con duración > 0
            df_con_duracion = df[df['duration'] > 0]
            if not df_con_duracion.empty:
                kpis['ratio_facturacion_vs_duracion'] = (
                        df_con_duracion['billsec'].sum() / df_con_duracion['duration'].sum())

    # 6. KPIs POR DEPARTAMENTO
    df['dept_origen'] = df['src'].apply(asignar_departamento)
    df['dept_destino'] = df['dst'].apply(asignar_departamento)

    # Resumen de actividad por departamento (como origen de la llamada)
    actividad_por_depto = df['dept_origen'].value_counts()
    kpis['actividad_por_depto_dict'] = actividad_por_depto.to_dict()

    # Duración total y promedio por departamento (origen)
    if 'duration' in df.columns:
        duracion_por_depto = df.groupby('dept_origen')['duration'].agg(['sum', 'mean', 'count'])
        kpis['duracion_por_depto_df'] = duracion_por_depto.reset_index().rename(
            columns={'sum': 'duracion_total_seg', 'mean': 'duracion_promedio_seg', 'count': 'llamadas'}
        )

    # Tasa de respuesta por departamento (si el origen es un departamento interno)
    if 'disposition' in df.columns:
        for dept in ['Administración', 'Comercial', 'Soporte Técnico']:
            df_dept = df[df['dept_origen'] == dept]
            if not df_dept.empty:
                total_dept = len(df_dept)
                contestadas_dept = len(df_dept[df_dept['disposition'] == 'ANSWERED'])
                kpis[f'tasa_respuesta_{dept.lower().replace(" ", "_")}'] = (
                        contestadas_dept / total_dept * 100) if total_dept > 0 else 0

    # 7. ANÁLISIS DE INTERACCIÓN ENTRE DEPARTAMENTOS
    if 'dept_origen' in df.columns and 'dept_destino' in df.columns:
        df['tipo_interaccion'] = df.apply(clasificar_interaccion, axis=1)

        # Resumen de tipos de interacción
        kpis['interacciones_por_tipo_dict'] = df['tipo_interaccion'].value_counts().to_dict()

        # Matriz de colaboración entre departamentos (para un heatmap)
        colaboracion = df[
            (df['dept_origen'].isin(['Administración', 'Comercial', 'Soporte Técnico'])) &
            (df['dept_destino'].isin(['Administración', 'Comercial', 'Soporte Técnico']))
            ]
        if not colaboracion.empty:
            matriz_colab = pd.crosstab(colaboracion['dept_origen'], colaboracion['dept_destino'])
            kpis['matriz_colaboracion_df'] = matriz_colab

    # 8. DATA FRAMES para visualizaciones específicas
    if 'disposition' in df.columns and not df['disposition'].isnull().all():
        df_resumen = df['disposition'].value_counts().reset_index()
        df_resumen.columns = ['disposition', 'count']
        df_resumen['percentage'] = (df_resumen['count'] / df_resumen['count'].sum() * 100).round(1)
        kpis['df_resumen_disposition'] = df_resumen
    else:
        kpis['df_resumen_disposition'] = None

    return kpis


# ==================== FUNCIÓN DE VISUALIZACIÓN EN STREAMLIT ====================
from io import BytesIO
import os
import tempfile
from datetime import datetime
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
import numpy as np
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT


def mostrar_cdrs():
    """FUNCIÓN PRINCIPAL: Muestra toda la sección de CDRs en Streamlit."""

    # Función auxiliar para hacer serializable el diccionario de KPIs
    def fix_keys_for_json(obj):
        """
        Convierte las claves de un diccionario a string para que sea serializable en JSON.
        """
        if isinstance(obj, dict):
            new_dict = {}
            for key, value in obj.items():
                # Convertir la clave a string si no es de un tipo básico
                if not isinstance(key, (str, int, float, bool, type(None))):
                    key = str(key)
                new_dict[key] = fix_keys_for_json(value)
            return new_dict
        elif isinstance(obj, list):
            return [fix_keys_for_json(item) for item in obj]
        else:
            return obj

    # Inicializar estados en session_state - CORREGIDO: Añadir df_cdr_original
    if 'pdf_generado' not in st.session_state:
        st.session_state.pdf_generado = False
    if 'pdf_bytes' not in st.session_state:
        st.session_state.pdf_bytes = None
    if 'pdf_filename' not in st.session_state:
        st.session_state.pdf_filename = None
    if 'datos_cargados' not in st.session_state:
        st.session_state.datos_cargados = False
    if 'df_cdr_original' not in st.session_state:  # AÑADIDO: Inicializar df_cdr_original
        st.session_state.df_cdr_original = None

    # Botón para cargar y procesar
    if st.button("Cargar y analizar CDR"):
        with st.spinner("Cargando datos desde Google Sheets..."):
            df_cdr, _ = cargar_y_procesar_cdr()  # Obtén el DataFrame

            # FILTRAR SOLO LAS LLAMADAS QUE TIENEN DURACIÓN O ESTADO (no son solo intentos)
            # Guardar el DataFrame original para referencia
            st.session_state.df_cdr_original = df_cdr.copy()

            # Crear un DataFrame filtrado con solo las llamadas que tienen información de duración/estado
            # Primero, crear una máscara para identificar registros que son llamadas reales
            mask = (
                    (df_cdr['duration'].notna() & (df_cdr['duration'].astype(str).str.strip() != '')) |
                    (df_cdr['billsec'].notna() & (df_cdr['billsec'].astype(str).str.strip() != '')) |
                    (df_cdr['disposition'].notna() & (df_cdr['disposition'].astype(str).str.strip() != ''))
            )

            # Aplicar la máscara
            df_filtrado = df_cdr[mask].copy()

            # Convertir columnas numéricas
            for col in ['duration', 'billsec']:
                if col in df_filtrado.columns:
                    # Reemplazar valores vacíos o inválidos por 0
                    df_filtrado[col] = pd.to_numeric(df_filtrado[col].replace('', 0).fillna(0), errors='coerce')

            # Calcular los KPIs ampliados CON EL DATAFRAME FILTRADO
            kpis = calcular_kpis_cdr_ampliada(df_filtrado)

            # Agregar información adicional sobre el filtrado
            kpis['total_registros'] = len(df_cdr)
            kpis['llamadas_filtradas'] = len(df_filtrado)
            kpis['intentos_no_completados'] = len(df_cdr) - len(df_filtrado)

            # Guardar en session_state
            st.session_state.df_cdr = df_filtrado
            st.session_state.kpis = kpis
            st.session_state.datos_cargados = True
            st.session_state.pdf_generado = False  # Resetear estado PDF

        if df_cdr is not None and not df_cdr.empty:
            st.success(
                f"✅ Datos cargados correctamente. Total registros: {len(df_cdr)} | Llamadas con información: {len(df_filtrado)} | Intentos no completados: {len(df_cdr) - len(df_filtrado)}")
            st.rerun()  # Forzar actualización para mostrar el PDF
        else:
            st.error("No se pudieron cargar los datos o no hay registros.")

    # Mostrar contenido solo si los datos están cargados
    if st.session_state.get('datos_cargados', False) and 'df_cdr' in st.session_state:
        df_cdr = st.session_state.df_cdr
        df_cdr_original = st.session_state.df_cdr_original  # Ahora está inicializado
        kpis = st.session_state.kpis

        # Información sobre el filtrado
        with st.expander("ℹ️ Información sobre el filtrado de datos"):
            st.write(f"""
            **Total de registros en el CDR:** {kpis.get('total_registros', 0)}
            **Llamadas analizadas (con información):** {kpis.get('llamadas_filtradas', 0)}
            **Intentos/registros sin información completa:** {kpis.get('intentos_no_completados', 0)}

            *Nota: Solo se analizan las llamadas que tienen información de duración, tiempo facturable o estado (disposition).*
            """)

        # SECCIÓN DE EXPORTACIÓN
        col1, col2, col3 = st.columns(3)

        with col1:
            # Botón para generar y descargar PDF CON GRÁFICOS
            if st.button("📄 Generar PDF con Gráficos", use_container_width=True, key="generar_pdf_btn"):
                with st.spinner("Generando PDF con gráficos..."):
                    # Generar PDF en memoria CON GRÁFICOS
                    pdf_bytes = generar_pdf_kpis_con_graficos(kpis, df_cdr)

                    # Guardar en session_state
                    st.session_state.pdf_bytes = pdf_bytes
                    st.session_state.pdf_filename = f"informe_cdr_con_graficos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                    st.session_state.pdf_generado = True

                    # Forzar actualización inmediata
                    st.rerun()

        # Mostrar botón de descarga si el PDF está generado
        if st.session_state.pdf_generado and st.session_state.pdf_bytes:
            st.download_button(
                label="⬇️ Descargar PDF con Gráficos",
                data=st.session_state.pdf_bytes,
                file_name=st.session_state.pdf_filename,
                mime="application/pdf",
                use_container_width=True,
                key="descargar_pdf"
            )

        # Crear pestañas para organizar la información (AHORA CON 5 PESTAÑAS)
        tab1, tab2, tab3, tab4, tab5 = st.tabs(
            ["📈 Resumen General", "🕒 Patrones", "📞 Origen y Destino", "🏢 Análisis por Departamento", "📋 Detalles"])

        with tab1:  # Pestaña 1: Resumen General
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Llamadas Totales", kpis.get('total_llamadas', 0))
            with col2:
                st.metric("Llamadas Internas", kpis.get('llamadas_internas', 0))
            with col3:
                st.metric("Tasa de Respuesta", f"{kpis.get('tasa_respuesta', 0):.1f}%")
            with col4:
                st.metric("Duración Promedio", f"{kpis.get('duracion_promedio_segundos', 0):.1f} s")


            # Gráfico de llamadas por día (KPI básico)
            if 'llamadas_por_dia' in kpis:
                st.subheader("Llamadas por Día")
                df_por_dia = pd.DataFrame(list(kpis['llamadas_por_dia'].items()), columns=['Fecha', 'Llamadas'])
                st.bar_chart(df_por_dia.set_index('Fecha'))

        with tab2:  # Pestaña 2: Patrones Temporales

            # Usar Altair para gráfico apilado
            import altair as alt

            # Preparar datos
            df_cdr['hora'] = pd.to_datetime(df_cdr['calldate']).dt.hour
            dept_internos = ['Administración', 'Comercial', 'Soporte Técnico']

            # Crear categoría para llamadas sin departamento conocido
            df_cdr['dept_categoria'] = df_cdr['dept_origen'].apply(
                lambda x: x if x in dept_internos else 'Otros / Sin Extensión'
            )

            # Usar todos los datos, ya no filtrar
            chart_data = df_cdr.groupby(['hora', 'dept_categoria']).size().reset_index(name='count')

            # Orden personalizado para la leyenda
            orden_categorias = dept_internos + ['Otros / Sin Extensión']
            chart_data['dept_categoria'] = pd.Categorical(
                chart_data['dept_categoria'],
                categories=orden_categorias,
                ordered=True
            )

            # Crear gráfico apilado con mejoras visuales
            chart = alt.Chart(chart_data).mark_bar().encode(
                x=alt.X('hora:O', title='Hora del Día', axis=alt.Axis(labelAngle=0)),
                y=alt.Y('count:Q', title='Número de Llamadas', stack='zero'),
                color=alt.Color(
                    'dept_categoria:N',
                    title='Departamento / Categoría',
                    scale=alt.Scale(
                        # Asignar colores específicos, gris para "Otros"
                        domain=orden_categorias,
                        range=['#1f77b4', '#ff7f0e', '#2ca02c', '#7f7f7f']  # Azul, naranja, verde, gris
                    ),
                    sort=orden_categorias  # Mantener orden en leyenda
                ),
                tooltip=['hora:O', 'dept_categoria:N', 'count:Q']
            ).properties(
                width=700,
                height=400,
                title='Llamadas por Franja Horaria y Departamento'
            ).configure_legend(
                titleFontSize=12,
                labelFontSize=11
            ).configure_axis(
                labelFontSize=11,
                titleFontSize=12
            )

            st.altair_chart(chart, use_container_width=True)

            # Usar Altair para gráfico apilado
            import altair as alt

            # Alternativa simple
            df_cdr['dia_semana'] = pd.to_datetime(df_cdr['calldate']).dt.strftime('%A')
            # Luego reemplazar en inglés si es necesario
            dias_traduccion = {
                'Monday': 'Lunes',
                'Tuesday': 'Martes',
                'Wednesday': 'Miércoles',
                'Thursday': 'Jueves',
                'Friday': 'Viernes',
                'Saturday': 'Sábado',
                'Sunday': 'Domingo'
            }
            df_cdr['dia_semana'] = df_cdr['dia_semana'].map(dias_traduccion)

            # Preparar datos
            #df_cdr['dia_semana'] = pd.to_datetime(df_cdr['calldate']).dt.day_name('spanish')  # Días en español
            dept_internos = ['Administración', 'Comercial', 'Soporte Técnico']

            # Crear categoría para llamadas sin departamento conocido
            df_cdr['dept_categoria'] = df_cdr['dept_origen'].apply(
                lambda x: x if x in dept_internos else 'Otros / Sin Extensión'
            )

            # Agrupar datos por día y categoría
            chart_data = df_cdr.groupby(['dia_semana', 'dept_categoria']).size().reset_index(name='count')

            # Ordenar días de la semana correctamente
            dias_orden = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
            chart_data['dia_semana'] = pd.Categorical(
                chart_data['dia_semana'],
                categories=dias_orden,
                ordered=True
            )
            chart_data = chart_data.sort_values('dia_semana')

            # Orden personalizado para la leyenda
            orden_categorias = dept_internos + ['Otros / Sin Extensión']
            chart_data['dept_categoria'] = pd.Categorical(
                chart_data['dept_categoria'],
                categories=orden_categorias,
                ordered=True
            )

            # Crear gráfico apilado con mejoras visuales
            chart = alt.Chart(chart_data).mark_bar().encode(
                x=alt.X('dia_semana:N',
                        title='Día de la Semana',
                        axis=alt.Axis(labelAngle=0),
                        sort=dias_orden),
                y=alt.Y('count:Q',
                        title='Número de Llamadas',
                        stack='zero'),
                color=alt.Color(
                    'dept_categoria:N',
                    title='Departamento / Categoría',
                    scale=alt.Scale(
                        domain=orden_categorias,
                        range=['#1f77b4', '#ff7f0e', '#2ca02c', '#7f7f7f']  # Azul, naranja, verde, gris
                    ),
                    sort=orden_categorias
                ),
                tooltip=['dia_semana:N', 'dept_categoria:N', 'count:Q']
            ).properties(
                width=700,
                height=400,
                title='Llamadas por Día de la Semana y Departamento'
            ).configure_legend(
                titleFontSize=12,
                labelFontSize=11
            ).configure_axis(
                labelFontSize=11,
                titleFontSize=12
            )

            st.altair_chart(chart, use_container_width=True)

        with tab3:  # Pestaña 3: Origen y Destino
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Top 5 Extensiones de Origen")
                if 'top_origen_dict' in kpis:
                    df_origen = pd.DataFrame(list(kpis['top_origen_dict'].items()),
                                             columns=['Extensión', 'Llamadas']).head(5)
                    st.dataframe(df_origen, use_container_width=True)

            with col2:
                st.subheader("Top 5 Destinos")
                if 'top_destino_dict' in kpis:
                    df_destino = pd.DataFrame(list(kpis['top_destino_dict'].items()),
                                              columns=['Destino', 'Llamadas']).head(5)
                    st.dataframe(df_destino, use_container_width=True)

            # Métricas de distribución
            st.subheader("Distribución Interna/Externa")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Llamadas Internas", kpis.get('llamadas_internas', 0))
            with col2:
                st.metric("Llamadas Externas", kpis.get('llamadas_externas', 0))
            with col3:
                total = kpis.get('llamadas_internas', 0) + kpis.get('llamadas_externas', 0)
                porcentaje_internas = (kpis.get('llamadas_internas', 0) / total * 100) if total > 0 else 0
                st.metric("% Internas", f"{porcentaje_internas:.1f}%")

        with tab4:  # Pestaña 4: Análisis por Departamento (NUEVA)
            st.subheader("Actividad por Departamento")

            if 'actividad_por_depto_dict' in kpis:
                df_dept = pd.DataFrame(list(kpis['actividad_por_depto_dict'].items()),
                                       columns=['Departamento', 'Llamadas'])
                # Filtrar solo departamentos internos para el gráfico
                dept_internos = ['Administración', 'Comercial', 'Soporte Técnico']
                df_dept_filtrado = df_dept[df_dept['Departamento'].isin(dept_internos)]

                if not df_dept_filtrado.empty:
                    st.bar_chart(df_dept_filtrado.set_index('Departamento'))

            # Métricas comparativas por departamento
            st.subheader("Comparativa de Rendimiento")
            if 'duracion_por_depto_df' in kpis:
                df_duracion = kpis['duracion_por_depto_df']
                df_duracion_internos = df_duracion[
                    df_duracion['dept_origen'].isin(['Administración', 'Comercial', 'Soporte Técnico'])]

                cols = st.columns(len(df_duracion_internos))
                for idx, (_, fila) in enumerate(df_duracion_internos.iterrows()):
                    with cols[idx]:
                        st.metric(
                            label=f"{fila['dept_origen']}",
                            value=f"{fila['llamadas']} llamadas",
                            delta=f"Prom: {fila['duracion_promedio_seg']:.0f}s"
                        )

            # Matriz de colaboración entre departamentos
            st.subheader("Interacción entre Departamentos")
            if 'matriz_colaboracion_df' in kpis:
                st.write("¿Cómo colaboran los equipos entre sí? (Origen → Destino)")
                matriz = kpis['matriz_colaboracion_df']
                st.dataframe(matriz.style.background_gradient(cmap='Blues'), use_container_width=True)

            # Tipos de interacción
            st.subheader("Distribución por Tipo de Llamada")
            if 'interacciones_por_tipo_dict' in kpis:
                df_tipo = pd.DataFrame(list(kpis['interacciones_por_tipo_dict'].items()),
                                       columns=['Tipo de Interacción', 'Cantidad'])
                st.bar_chart(df_tipo.set_index('Tipo de Interacción'))

        with tab5:  # Pestaña 5: Detalles y Datos Crudos
            st.subheader("Estado de las Llamadas")
            if kpis.get('df_resumen_disposition') is not None:
                st.dataframe(kpis['df_resumen_disposition'], use_container_width=True)

            st.subheader("Muestra de los Datos Crudos (Llamadas con información)")
            st.dataframe(df_cdr.head(20), use_container_width=True)

            # Solo mostrar expander si df_cdr_original existe y no es None
            if df_cdr_original is not None:
                with st.expander("Ver registros completos (incluyendo intentos)"):
                    st.subheader("Todos los registros del CDR")
                    st.dataframe(df_cdr_original.head(50), use_container_width=True)
                    st.caption(f"Mostrando 50 de {len(df_cdr_original)} registros totales")
            else:
                st.info(
                    "No hay registros originales disponibles. Presiona 'Cargar y analizar CDR' para cargar los datos.")


def generar_pdf_kpis_con_graficos(kpis, df=None):
    """Genera un PDF con los KPIs, tablas y gráficos, y devuelve los bytes (en memoria)."""

    # Crear un buffer en memoria para el PDF
    buffer = BytesIO()

    # Crear el documento en memoria
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []

    # Estilos
    styles = getSampleStyleSheet()
    estilo_titulo = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=30,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#2E86C1')
    )
    estilo_subtitulo = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Heading2'],
        fontSize=14,
        spaceAfter=12,
        alignment=TA_LEFT,
        textColor=colors.HexColor('#2E86C1')
    )
    estilo_kpi = ParagraphStyle(
        'KPI',
        parent=styles['Normal'],
        fontSize=12,
        spaceAfter=6,
        alignment=TA_CENTER,
        textColor=colors.black
    )
    estilo_nota = ParagraphStyle(
        'Nota',
        parent=styles['Normal'],
        fontSize=9,
        spaceAfter=6,
        alignment=TA_LEFT,
        textColor=colors.grey
    )

    # Título del informe
    elements.append(Paragraph("INFORME DE KPIs - CDR", estilo_titulo))
    elements.append(Paragraph(f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", estilo_kpi))

    # Nota sobre el filtrado
    if 'total_registros' in kpis and 'llamadas_filtradas' in kpis:
        elements.append(Paragraph(
            f"Nota: Se analizaron {kpis['llamadas_filtradas']} de {kpis['total_registros']} registros (solo llamadas con información completa)",
            estilo_nota
        ))

    elements.append(Spacer(1, 0.5 * inch))

    # 1. KPIs Principales
    elements.append(Paragraph("1. KPIs Principales", estilo_subtitulo))

    # Crear una tabla con los KPIs principales en 2 columnas
    datos_kpis = [
        ["KPI", "Valor", "KPI", "Valor"],
        ["Total de llamadas", str(kpis.get('total_llamadas', 0)),
         "Llamadas contestadas", str(kpis.get('llamadas_contestadas', 0))],
        ["Tasa de respuesta", f"{kpis.get('tasa_respuesta', 0):.1f}%",
         "Duración total", f"{kpis.get('duracion_total_segundos', 0):.0f} s"],
        ["Duración promedio", f"{kpis.get('duracion_promedio_segundos', 0):.1f} s",
         "Minutos facturables", f"{kpis.get('minutos_facturables', 0):.1f}"],
        ["Llamadas internas", str(kpis.get('llamadas_internas', 0)),
         "Llamadas externas", str(kpis.get('llamadas_externas', 0))],
        ["Extensiones únicas", str(kpis.get('extensiones_unicas', 0)),
         "Tasa internas", f"{(kpis.get('llamadas_internas', 0) / kpis.get('total_llamadas', 1) * 100):.1f}%"],
    ]

    tabla_kpis = Table(datos_kpis, colWidths=[2 * inch, 1.5 * inch, 2 * inch, 1.5 * inch])
    tabla_kpis.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2E86C1')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#F8F9F9')),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#D5D8DC')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F2F3F4')]),
    ]))
    elements.append(tabla_kpis)
    elements.append(Spacer(1, 0.5 * inch))

    # 2. GRÁFICOS
    elements.append(Paragraph("2. Gráficos de Análisis", estilo_subtitulo))
    elements.append(Spacer(1, 0.25 * inch))

    # Crear directorio temporal para las imágenes
    temp_dir = tempfile.mkdtemp()
    img_paths = []

    # 2.1 Gráfico de Llamadas por Día
    if 'llamadas_por_dia' in kpis and kpis['llamadas_por_dia']:
        try:
            fig, ax = plt.subplots(figsize=(10, 4))
            fechas = list(kpis['llamadas_por_dia'].keys())[-10:]  # Últimos 10 días
            llamadas = list(kpis['llamadas_por_dia'].values())[-10:]

            bars = ax.bar(fechas, llamadas, color=plt.cm.Blues(np.linspace(0.4, 0.8, len(fechas))))
            ax.set_xlabel('Fecha', fontsize=10)
            ax.set_ylabel('Número de Llamadas', fontsize=10)
            ax.set_title('Llamadas por Día (Últimos 10 días)', fontsize=12, fontweight='bold')
            ax.tick_params(axis='x', rotation=45, labelsize=8)
            ax.tick_params(axis='y', labelsize=8)

            # Añadir valores en las barras
            for bar in bars:
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width() / 2., height + 0.1,
                        f'{int(height)}', ha='center', va='bottom', fontsize=8)

            plt.tight_layout()

            # Guardar imagen temporal
            img_path = os.path.join(temp_dir, 'llamadas_por_dia.png')
            plt.savefig(img_path, dpi=150, bbox_inches='tight')
            plt.close(fig)
            img_paths.append(img_path)

            # Agregar imagen al PDF
            elements.append(Paragraph("Llamadas por Día", estilo_kpi))
            elements.append(Image(img_path, width=6 * inch, height=2.5 * inch))
            elements.append(Spacer(1, 0.25 * inch))

        except Exception as e:
            print(f"Error generando gráfico de llamadas por día: {e}")

    # 2.2 Gráfico de Distribución por Franja Horaria
    if 'llamadas_por_hora_dict' in kpis and kpis['llamadas_por_hora_dict']:
        try:
            fig, ax = plt.subplots(figsize=(10, 4))
            horas = [f"{h}:00" for h in range(24)]
            llamadas = [kpis['llamadas_por_hora_dict'].get(h, 0) for h in range(24)]

            bars = ax.bar(horas, llamadas, color=plt.cm.Greens(np.linspace(0.3, 0.7, 24)))
            ax.set_xlabel('Hora del Día', fontsize=10)
            ax.set_ylabel('Número de Llamadas', fontsize=10)
            ax.set_title('Distribución por Franja Horaria', fontsize=12, fontweight='bold')
            ax.tick_params(axis='x', rotation=45, labelsize=7)
            ax.tick_params(axis='y', labelsize=8)

            # Destacar hora pico
            hora_pico = kpis.get('hora_pico', 0)
            if hora_pico in range(24):
                bars[hora_pico].set_color(plt.cm.Reds(0.7))
                ax.text(hora_pico, llamadas[hora_pico] + 0.5, 'PICO',
                        ha='center', va='bottom', fontsize=8, fontweight='bold', color='red')

            plt.tight_layout()

            img_path = os.path.join(temp_dir, 'distribucion_horaria.png')
            plt.savefig(img_path, dpi=150, bbox_inches='tight')
            plt.close(fig)
            img_paths.append(img_path)

            elements.append(Paragraph(f"Distribución por Franja Horaria (Hora pico: {hora_pico}:00)", estilo_kpi))
            elements.append(Image(img_path, width=6 * inch, height=2.5 * inch))
            elements.append(Spacer(1, 0.25 * inch))

        except Exception as e:
            print(f"Error generando gráfico de distribución horaria: {e}")

    # 2.3 Gráfico de Actividad por Departamento
    if 'actividad_por_depto_dict' in kpis and kpis['actividad_por_depto_dict']:
        try:
            fig, ax = plt.subplots(figsize=(10, 4))

            # Filtrar solo departamentos internos y ordenar por actividad
            dept_internos = ['Administración', 'Comercial', 'Soporte Técnico']
            dept_data = [(dept, llamadas) for dept, llamadas in kpis['actividad_por_depto_dict'].items()
                         if dept in dept_internos]
            dept_data.sort(key=lambda x: x[1], reverse=True)

            if dept_data:
                departamentos = [d[0] for d in dept_data]
                llamadas = [d[1] for d in dept_data]

                colors_dept = [plt.cm.Set2(i / len(departamentos)) for i in range(len(departamentos))]
                bars = ax.bar(departamentos, llamadas, color=colors_dept)

                ax.set_xlabel('Departamento', fontsize=10)
                ax.set_ylabel('Número de Llamadas', fontsize=10)
                ax.set_title('Actividad por Departamento (Internos)', fontsize=12, fontweight='bold')
                ax.tick_params(axis='x', rotation=0, labelsize=9)
                ax.tick_params(axis='y', labelsize=8)

                # Añadir valores en las barras
                for bar in bars:
                    height = bar.get_height()
                    ax.text(bar.get_x() + bar.get_width() / 2., height + 0.1,
                            f'{int(height)}', ha='center', va='bottom', fontsize=8)

                plt.tight_layout()

                img_path = os.path.join(temp_dir, 'actividad_depto.png')
                plt.savefig(img_path, dpi=150, bbox_inches='tight')
                plt.close(fig)
                img_paths.append(img_path)

                elements.append(Paragraph("Actividad por Departamento", estilo_kpi))
                elements.append(Image(img_path, width=6 * inch, height=2.5 * inch))
                elements.append(Spacer(1, 0.25 * inch))

        except Exception as e:
            print(f"Error generando gráfico de actividad por departamento: {e}")

    # 2.4 Gráfico de Top Extensiones y Destinos
    if 'top_origen_dict' in kpis and 'top_destino_dict' in kpis:
        try:
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))

            # Top 5 Extensiones de Origen
            top_origen = list(kpis['top_origen_dict'].items())[:5]
            if top_origen:
                extensiones = [str(ext) for ext, _ in top_origen]
                llamadas_origen = [llamadas for _, llamadas in top_origen]

                colors_origen = plt.cm.Blues(np.linspace(0.5, 0.9, len(extensiones)))
                ax1.bar(extensiones, llamadas_origen, color=colors_origen)
                ax1.set_xlabel('Extensión', fontsize=10)
                ax1.set_ylabel('Llamadas', fontsize=10)
                ax1.set_title('Top 5 Extensiones de Origen', fontsize=12, fontweight='bold')
                ax1.tick_params(axis='x', rotation=45, labelsize=8)
                ax1.tick_params(axis='y', labelsize=8)

                # Añadir valores
                for i, v in enumerate(llamadas_origen):
                    ax1.text(i, v + 0.1, str(v), ha='center', va='bottom', fontsize=8)

            # Top 5 Destinos
            top_destino = list(kpis['top_destino_dict'].items())[:5]
            if top_destino:
                destinos = [str(dst) if len(str(dst)) < 15 else str(dst)[:12] + '...'
                            for dst, _ in top_destino]
                llamadas_destino = [llamadas for _, llamadas in top_destino]

                colors_destino = plt.cm.Greens(np.linspace(0.5, 0.9, len(destinos)))
                ax2.bar(destinos, llamadas_destino, color=colors_destino)
                ax2.set_xlabel('Destino', fontsize=10)
                ax2.set_ylabel('Llamadas', fontsize=10)
                ax2.set_title('Top 5 Destinos', fontsize=12, fontweight='bold')
                ax2.tick_params(axis='x', rotation=45, labelsize=8)
                ax2.tick_params(axis='y', labelsize=8)

                # Añadir valores
                for i, v in enumerate(llamadas_destino):
                    ax2.text(i, v + 0.1, str(v), ha='center', va='bottom', fontsize=8)

            plt.tight_layout()

            img_path = os.path.join(temp_dir, 'top_ext_dest.png')
            plt.savefig(img_path, dpi=150, bbox_inches='tight')
            plt.close(fig)
            img_paths.append(img_path)

            elements.append(Paragraph("Top Extensiones y Destinos", estilo_kpi))
            elements.append(Image(img_path, width=6 * inch, height=2.5 * inch))
            elements.append(Spacer(1, 0.25 * inch))

        except Exception as e:
            print(f"Error generando gráfico de top extensiones/destinos: {e}")

    # 3. TABLAS DETALLADAS
    elements.append(PageBreak())
    elements.append(Paragraph("3. Tablas Detalladas", estilo_subtitulo))
    elements.append(Spacer(1, 0.25 * inch))

    # 3.1 Actividad por Departamento (tabla detallada)
    if 'actividad_por_depto_dict' in kpis:
        elements.append(Paragraph("3.1 Actividad por Departamento", estilo_kpi))

        datos_dept = [["Departamento", "Llamadas", "% del Total"]]
        total_llamadas = kpis.get('total_llamadas', 1)

        for dept, llamadas in sorted(kpis['actividad_por_depto_dict'].items(),
                                     key=lambda x: x[1], reverse=True):
            if llamadas > 0:
                porcentaje = (llamadas / total_llamadas * 100)
                datos_dept.append([dept, str(llamadas), f"{porcentaje:.1f}%"])

        if len(datos_dept) > 1:
            tabla_dept = Table(datos_dept, colWidths=[3 * inch, 1.5 * inch, 1.5 * inch])
            tabla_dept.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2E86C1')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#F8F9F9')),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#D5D8DC')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F2F3F4')]),
            ]))
            elements.append(tabla_dept)
            elements.append(Spacer(1, 0.25 * inch))

    # 3.2 Distribución por Estado de Llamadas - CORREGIDO
    if 'df_resumen_disposition' in kpis and kpis['df_resumen_disposition'] is not None:
        elements.append(Paragraph("3.2 Estado de las Llamadas", estilo_kpi))

        df_disposition = kpis['df_resumen_disposition']

        # Verificar las columnas disponibles
        columnas_disponibles = df_disposition.columns.tolist()

        # Buscar nombres alternativos para las columnas
        col_estado = None
        col_cantidad = None
        col_porcentaje = None

        for col in columnas_disponibles:
            col_lower = col.lower()
            if 'disposition' in col_lower or 'estado' in col_lower or 'status' in col_lower:
                col_estado = col
            elif 'count' in col_lower or 'cantidad' in col_lower or 'llamadas' in col_lower:
                col_cantidad = col
            elif 'percentage' in col_lower or 'porcentaje' in col_lower or '%' in col_lower:
                col_porcentaje = col

        # Si no encontramos columnas con nombres esperados, usar las primeras 3 columnas
        if not col_estado and len(columnas_disponibles) > 0:
            col_estado = columnas_disponibles[0]
        if not col_cantidad and len(columnas_disponibles) > 1:
            col_cantidad = columnas_disponibles[1]
        if not col_porcentaje and len(columnas_disponibles) > 2:
            col_porcentaje = columnas_disponibles[2]

        datos_disposition = [["Estado", "Cantidad", "%"]]

        for _, row in df_disposition.iterrows():
            estado = str(row[col_estado]) if col_estado else "N/A"
            cantidad = str(row[col_cantidad]) if col_cantidad else "N/A"

            # Manejar el porcentaje
            if col_porcentaje:
                porcentaje_val = row[col_porcentaje]
                if isinstance(porcentaje_val, (int, float)):
                    porcentaje = f"{porcentaje_val:.1f}%"
                else:
                    porcentaje = str(porcentaje_val)
            else:
                porcentaje = "N/A"

            datos_disposition.append([estado, cantidad, porcentaje])

        tabla_disposition = Table(datos_disposition, colWidths=[2.5 * inch, 1.5 * inch, 2 * inch])
        tabla_disposition.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#27AE60')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#F8F9F9')),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#D5D8DC')),
        ]))
        elements.append(tabla_disposition)
        elements.append(Spacer(1, 0.25 * inch))

    # 4. MUESTRA DE DATOS
    if df is not None and not df.empty:
        elements.append(Paragraph("4. Muestra de Datos (primeras 10 llamadas con información)", estilo_kpi))

        # Verificar qué columnas existen en el DataFrame
        columnas_interes = ['calldate', 'clid', 'src', 'dst', 'duration', 'disposition', 'billsec', 'lastapp']
        columnas_disponibles = [col for col in columnas_interes if col in df.columns]

        # Si no hay columnas de las esperadas, tomar las primeras 5 columnas disponibles
        if not columnas_disponibles and len(df.columns) > 0:
            columnas_disponibles = df.columns.tolist()[:5]

        if columnas_disponibles:
            df_muestra = df[columnas_disponibles].head(10)

            datos_muestra = [columnas_disponibles]
            for _, fila in df_muestra.iterrows():
                datos_muestra.append([str(fila[col])[:30] if len(str(fila[col])) > 30 else str(fila[col])
                                      for col in columnas_disponibles])

            num_cols = len(columnas_disponibles)
            ancho_col = 6 * inch / num_cols if num_cols > 0 else 1 * inch

            tabla_muestra = Table(datos_muestra, colWidths=[ancho_col] * num_cols)
            tabla_muestra.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#7D3C98')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#F8F9F9')),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#D5D8DC')),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
            ]))
            elements.append(tabla_muestra)

            # Nota sobre el muestreo
            if 'total_registros' in kpis:
                elements.append(Spacer(1, 0.1 * inch))
                elements.append(Paragraph(
                    f"Nota: Muestra de 10 llamadas de un total de {kpis.get('llamadas_filtradas', 0)} llamadas analizadas "
                    f"(de {kpis.get('total_registros', 0)} registros totales en el CDR)",
                    estilo_nota
                ))

    # Pie de página con información de resumen
    elements.append(Spacer(1, 0.5 * inch))
    elements.append(Paragraph(
        f"Resumen: {kpis.get('total_llamadas', 0)} llamadas analizadas | "
        f"Duración total: {kpis.get('duracion_total_segundos', 0) / 60:.1f} minutos | "
        f"Generado el {datetime.now().strftime('%d/%m/%Y a las %H:%M')}",
        ParagraphStyle('Footer', parent=styles['Normal'], fontSize=9,
                       alignment=TA_CENTER, textColor=colors.grey)))

    # Construir el PDF en memoria
    doc.build(elements)

    # Limpiar archivos temporales
    for img_path in img_paths:
        try:
            os.remove(img_path)
        except:
            pass
    try:
        os.rmdir(temp_dir)
    except:
        pass

    # Obtener los bytes del PDF
    pdf_bytes = buffer.getvalue()
    buffer.close()

    return pdf_bytes