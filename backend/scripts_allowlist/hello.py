"""Ejemplo de script permitido (allow-list): saluda y termina con éxito.

Placeholder para desarrollo: el ejecutor lanza este archivo con el
intérprete del proyecto, sin shell. Edítalo libremente o añade scripts
propios en este directorio y regístralos en CronPanel como administrador.
"""

import sys

print("hola desde el script permitido")
print(f"argv recibido: {sys.argv}", file=sys.stderr)
sys.exit(0)