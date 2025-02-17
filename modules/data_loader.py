import pandas as pd

EXCEL_PATH = "data/datos.xlsx"  # Ruta del Excel

def cargar_datos(comercial=None):
    """Carga los datos del Excel y los filtra según el comercial logueado."""
    try:
        df = pd.read_excel(EXCEL_PATH)

        # Renombramos las columnas de latitud y longitud para evitar conflictos
        df.rename(columns={"LATITUD": "lat_corregida", "LONGITUD": "long_corregida", "COMERCIAL": "comercial"}, inplace=True)

        if comercial:
            df = df[df["comercial"] == comercial]  # Filtra por comercial logueado

        # Reemplazar comas por puntos y convertir a numérico
        df['lat_corregida'] = df['lat_corregida'].astype(str).str.replace(",", ".").astype(float)
        df['long_corregida'] = df['long_corregida'].astype(str).str.replace(",", ".").astype(float)

        # Eliminar filas con valores faltantes en 'lat_corregida' o 'long_corregida'
        df = df.dropna(subset=['lat_corregida', 'long_corregida'])

        return df
    except Exception as e:
        return f"Error al cargar los datos: {e}"
