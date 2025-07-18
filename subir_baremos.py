import pandas as pd
import sqlitecloud

# 📁 Nombre del archivo Excel en el mismo directorio
EXCEL_FILE = "baremo.xlsx"

# 📡 URL de conexión a SQLite Cloud
DB_URL = "sqlitecloud://ceafu04onz.g6.sqlite.cloud:8860/usuarios.db?apikey=Qo9m18B9ONpfEGYngUKm99QB5bgzUTGtK7iAcThmwvY"

def cargar_excel_y_subir():
    try:
        # Leer el Excel
        df = pd.read_excel(EXCEL_FILE)

        # Mostrar columnas originales para depuración
        print("📄 Columnas originales del Excel:", df.columns.tolist())

        # Normalizar nombres de columnas
        df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")

        # Renombrar variaciones comunes
        df = df.rename(columns={
            "código": "codigo",
            "codigo": "codigo",
            "descripción": "descripcion",
            "descripcion": "descripcion",
            "baremo": "precio",
            "precio": "precio"
        })

        # Validar que las columnas esenciales existen
        columnas_requeridas = ["codigo", "descripcion", "precio"]
        for col in columnas_requeridas:
            if col not in df.columns:
                raise ValueError(f"Falta la columna requerida: '{col}'")

        # Rellenar valores vacíos con cadena vacía
        df = df.fillna("")

        # Conectar con SQLite Cloud
        conn = sqlitecloud.connect(DB_URL)
        cursor = conn.cursor()

        insertados = 0
        for _, row in df.iterrows():
            try:
                cursor.execute("""
                    INSERT INTO baremos_viabilidades (codigo, descripcion, unidades, precio, tipo)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    str(row["codigo"]).strip(),
                    str(row["descripcion"]).strip(),
                    str(row.get("unidades", "")).strip(),
                    str(row["precio"]).strip(),
                    str(row.get("tipo", "")).strip()
                ))
                insertados += 1
            except Exception as e:
                print(f"⚠️ Error en '{row.get('codigo', '???')}': {e}")
                continue

        conn.commit()
        conn.close()
        print(f"✅ Se insertaron {insertados} registros correctamente.")

    except Exception as e:
        print(f"❌ Error general: {e}")

if __name__ == "__main__":
    cargar_excel_y_subir()
