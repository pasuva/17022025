import sqlite3
import pandas as pd
import os

DB_PATH = "../data/usuarios.db"
EXCEL_PATH = r"C:\Users\psuarez\Downloads\GREENFIELD (2025.01.10)_prueba servidor.xlsx"

# Mapeo de columnas del Excel a la base de datos
db_columns = [
    "id_ams", "apartment_id", "address_id", "provincia", "municipio", "poblacion",
    "vial", "numero", "parcela_catastral", "letra", "cp", "site_operational_state",
    "apartment_operational_state", "cto_id", "olt", "cto", "LATITUD", "LONGITUD",
    "cto_con_proyecto", "COMERCIAL", "ZONA", "FECHA", "SERVICIABLE", "MOTIVO", "contrato_uis"
]

excel_columns = {
    "id": "id_ams",
    "apartment_id": "apartment_id",
    "address_id": "address_id",
    "provincia": "provincia",
    "municipio": "municipio",
    "poblacion": "poblacion",
    "vial": "vial",
    "numero":"numero",
    "Parcela_catastral": "parcela_catastral",
    "letra": "letra",
    "cp": "cp",
    "site_oerational_state": "site_operational_state",
    "apartment_oerational_state": "apartment_operational_state",
    "cto_id": "cto_id",
    "OLT": "olt",
    "CTO": "cto",
    "LATITUD": "LATITUD",
    "LONGITUD": "LONGITUD",
    "cto_con_proyecto": "cto_con_proyecto",
    "COMERCIAL": "COMERCIAL",
    "ZONA": "ZONA",
    "FECHA": "FECHA",
    "SERVICIABLE": "SERVICIABLE",
    "MOTIVO": "MOTIVO",
    "contrato_uis": "contrato_uis"
}

def load_data_to_db():
    try:
        # Leer el archivo Excel
        df = pd.read_excel(EXCEL_PATH, dtype=str)

        # Renombrar columnas según el mapeo
        df = df.rename(columns=excel_columns)[list(excel_columns.values())]

        # Reemplazar comas por puntos en latitud y longitud
        df["LATITUD"] = df["LATITUD"].str.replace(",", ".").astype(float)
        df["LONGITUD"] = df["LONGITUD"].str.replace(",", ".").astype(float)

        # Conectar con la base de datos
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Insertar datos en la base de datos
        for _, row in df.iterrows():
            cursor.execute(f"""
                INSERT INTO datos_uis ({', '.join(db_columns)})
                VALUES ({', '.join(['?'] * len(db_columns))})
            """, tuple(row))

        conn.commit()
        print("✅ Datos cargados correctamente en la base de datos.")
    except Exception as e:
        print(f"❌ Error al cargar datos: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    load_data_to_db()