import sqlite3

# Conexión a la base de datos
conn = sqlite3.connect("../data/usuarios.db")
cursor = conn.cursor()

# Función para limpiar las tablas
def limpiar_tabla(tabla):
    cursor.execute(f"DELETE FROM {tabla}")
    print(f"Datos de la tabla {tabla} eliminados correctamente.")

# Limpiar las tablas ofertas_comercia, trazabilidad y viabilidades
tablas_a_limpiar = ["ofertas_comercial", "trazabilidad", "viabilidades","comercial_rafa"]

for tabla in tablas_a_limpiar:
    limpiar_tabla(tabla)

# Guardar los cambios y cerrar la conexión
conn.commit()
conn.close()

print("Datos de las tablas limpiados correctamente.")