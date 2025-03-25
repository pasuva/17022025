import sqlitecloud

# Establecer la conexión
conn = sqlitecloud.connect("sqlitecloud://ceafu04onz.g6.sqlite.cloud:8860/usuarios.db?apikey=Qo9m18B9ONpfEGYngUKm99QB5bgzUTGtK7iAcThmwvY")

# Ejecutar la consulta
cursor = conn.execute('SELECT * FROM datos_uis;')

# Obtener todos los registros
resultados = cursor.fetchall()

# Mostrar todos los registros
for resultado in resultados:
    print(resultado)

# Cerrar la conexión
conn.close()