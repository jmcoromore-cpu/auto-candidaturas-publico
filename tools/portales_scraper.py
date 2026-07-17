"""Vigilancia directa de los portales de empleo de las empresas prioritarias.

Busca en Google (vía SerpApi, 1 unidad de cuota por ejecución en total)
resultados restringidos a los dominios de empleo configurados en
`batch_search.PORTALES_EMPRESA` (p. ej. jobs.moeveglobal.com, jobs.enel.com),
limitados a lo publicado en la última semana; la memoria de ofertas vistas
garantiza que al correo solo llegue lo nuevo.

Ventaja frente a scrapear cada portal: los portales corporativos (Workday,
SuccessFactors...) cambian y cargan por JavaScript, pero Google los indexa
de forma estable.
"""

from __future__ import annotations

import hashlib
import os

import requests

from .utils import limpiar_texto

URL_SERPAPI = "https://serpapi.com/search.json"

# Palabras que buscar dentro de los portales
TERMINOS_PORTALES = "(ingeniero OR beca OR técnico OR graduado OR prácticas)"

# Fragmentos de URL que corresponden a páginas de listado (no a ofertas concretas)
_FRAGMENTOS_LISTADO = ("jobopenings", "/careers/home", "/search", "/employment")


def _empresa_del_enlace(enlace: str, portales: list[dict]) -> str:
    """Devuelve el nombre de la empresa cuyo dominio aparece en el enlace."""
    for portal in portales:
        if portal["dominio"].lower() in enlace.lower():
            return portal["empresa"]
    return "Desconocida"


def _convertir(resultado: dict, portales: list[dict]) -> dict | None:
    """Convierte un resultado orgánico de Google en una oferta del pipeline."""
    enlace = resultado.get("link", "")
    if not enlace:
        return None
    if any(fragmento in enlace.lower() for fragmento in _FRAGMENTOS_LISTADO):
        return None  # página de listado genérica, no una oferta concreta

    titulo = limpiar_texto(resultado.get("title", ""))
    # Los portales añaden sufijos tipo "... - - 14614 - Enel": nos quedamos con el título real
    titulo = titulo.split(" - ")[0].strip() or titulo
    empresa = _empresa_del_enlace(enlace, portales)

    return {
        "id": "portal-" + hashlib.md5(enlace.encode("utf-8")).hexdigest()[:16],
        "titulo": titulo,
        "empresa": empresa,
        "ubicacion": "",
        "url": enlace,
        "descripcion": limpiar_texto(resultado.get("snippet", ""), maximo=1000),
        "fuente": "Portal de empresa",
        "portal": f"Web de {empresa}",
        "publicado": "",
    }


def buscar_ofertas(portales: list[dict]) -> list[dict]:
    """Busca ofertas nuevas en todos los portales configurados (1 unidad de cuota en total)."""
    if not portales:
        return []

    api_key = os.environ.get("SERPAPI_API_KEY", "")
    if not api_key:
        print("    [Portales] SERPAPI_API_KEY no configurada; se omite esta fuente.")
        return []

    sitios = " OR ".join(f"site:{portal['dominio']}" for portal in portales)
    params = {
        "engine": "google",
        "q": f"({sitios}) {TERMINOS_PORTALES}",
        "hl": "es",
        "gl": "es",
        "num": 20,
        "tbs": "qdr:d",  # publicado en las últimas 24 horas
        "api_key": api_key,
    }
    try:
        datos = requests.get(URL_SERPAPI, params=params, timeout=30).json()
    except (requests.RequestException, ValueError) as error:
        print(f"    [Portales] Error consultando SerpApi: {error}")
        return []

    if "error" in datos:
        # SerpApi devuelve error también cuando simplemente no hay resultados
        print(f"    [Portales] SerpApi: {datos['error']}")
        return []

    ofertas: list[dict] = []
    for resultado in datos.get("organic_results", []):
        oferta = _convertir(resultado, portales)
        if oferta:
            ofertas.append(oferta)
    return ofertas
