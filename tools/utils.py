"""Utilidades compartidas del pipeline: escape de LaTeX, cachés JSON y limpieza de texto."""

from __future__ import annotations

import json
import os
import re
import unicodedata

# Rutas base del proyecto (raíz = carpeta que contiene 'tools/')
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR_DATA = os.path.join(RAIZ, "data")
DIR_SALIDA = os.path.join(RAIZ, "salida")
DIR_PLANTILLAS = os.path.join(RAIZ, "plantillas")

# Caracteres especiales de LaTeX y su versión escapada
_LATEX_ESPECIALES = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def escapar_latex(texto: str) -> str:
    """Escapa los caracteres especiales de LaTeX en un texto plano.

    Conserva los saltos de línea, de modo que los párrafos separados por
    líneas en blanco sigan funcionando como párrafos en LaTeX.
    """
    if not texto:
        return ""
    return "".join(_LATEX_ESPECIALES.get(caracter, caracter) for caracter in texto)


def sanitizar_nombre_archivo(texto: str, maximo: int = 40) -> str:
    """Convierte un texto (p. ej. el nombre de una empresa) en un nombre de archivo seguro."""
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    texto = re.sub(r"[^A-Za-z0-9]+", "_", texto).strip("_")
    return texto[:maximo] or "SinNombre"


def limpiar_texto(texto: str, maximo: int | None = None) -> str:
    """Colapsa espacios y saltos de línea repetidos y recorta a una longitud máxima opcional."""
    texto = re.sub(r"\s+", " ", texto or "").strip()
    if maximo and len(texto) > maximo:
        texto = texto[:maximo].rsplit(" ", 1)[0] + " [...]"
    return texto


def cargar_json(ruta: str, por_defecto):
    """Carga un JSON de disco; devuelve `por_defecto` si el archivo no existe o está corrupto."""
    try:
        with open(ruta, "r", encoding="utf-8") as archivo:
            return json.load(archivo)
    except (FileNotFoundError, json.JSONDecodeError):
        return por_defecto


def guardar_json(ruta: str, datos) -> None:
    """Guarda datos como JSON legible, creando la carpeta contenedora si hace falta."""
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as archivo:
        json.dump(datos, archivo, ensure_ascii=False, indent=2)
