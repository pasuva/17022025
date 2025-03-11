import pandas as pd
import sqlite3

# Ruta del archivo CSV
csv_file = "tu_archivo.csv"

# Leer CSV con el delimitador correcto
df = pd.read_csv(csv_file, delimiter=";", dtype=str)

# Limpiar los nombres de las columnas (eliminar espacios innecesarios)
df.columns = df.columns.str.strip()

# Eliminar la columna 'site_operational_state' si existe en el CSV
if 'site_operational_state' in df.columns:
    df.drop(columns=['site_operational_state'], inplace=True)

# Convertir latitud y longitud: reemplazar ',' por '.' y convertir a float
df['latitud'] = df['latitud'].str.replace(',', '.').astype(float)
df['longitud'] = df['longitud'].str.replace(',', '.').astype(float)

# Conectar a la base de datos SQLite
conn = sqlite3.connect("../data/usuarios.db")
cursor = conn.cursor()

# 🔥 Borrar todos los datos de la tabla y resetear el autoincremento
cursor.execute("DELETE FROM ofertas_comercial")
cursor.execute("DELETE FROM sqlite_sequence WHERE name='ofertas_comercial'")

# Guardar en la base de datos SIN la columna 'site_operational_state'
df.to_sql("ofertas_comercial", conn, if_exists="append", index=False)

# Confirmar cambios y cerrar conexión
conn.commit()
conn.close()

print("✅ Datos cargados correctamente en ofertas_comercial sin la columna 'site_operational_state'.")
