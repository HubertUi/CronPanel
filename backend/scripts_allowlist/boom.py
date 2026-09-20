"""Ejemplo de fallo: termina con código de salida distinto de cero."""

import sys

print("este es un error de ejemplo", file=sys.stderr)
sys.exit(1)