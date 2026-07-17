"""Fase OSINT: localiza perfiles públicos de Talent Acquisition / RRHH de la empresa.

Hace una búsqueda de Google (vía SerpApi, 1 unidad de cuota por empresa)
restringida a linkedin.com/in. Los resultados se cachean por empresa en
data/osint_cache.json para no volver a gastar cuota en empresas ya investigadas.

Los perfiles devueltos son resultados públicos de Google; el pipeline solo los
lista en el reporte para que TÚ decidas si contactar. No envía nada a nadie.
"""

from __future__ import annotations

import os

import requests

from .utils import DIR_DATA, cargar_json, guardar_json, limpiar_texto

URL_SERPAPI = "https://serpapi.com/search.json"
RUTA_CACHE = os.path.join(DIR_DATA, "osint_cache.json")


def buscar_reclutadores(empresa: str) -> list[dict]:
    """Devuelve hasta 3 perfiles de selección de personal de la empresa (con caché)."""
    cache = cargar_json(RUTA_CACHE, {})
    clave = empresa.strip().lower()
    if clave in cache:
        return cache[clave]

    api_key = os.environ.get("SERPAPI_API_KEY", "")
    if not api_key:
        print("    [OSINT] SERPAPI_API_KEY no configurada; se omite la búsqueda de perfiles.")
        return []

    consulta = (
        f'site:linkedin.com/in ("talent acquisition" OR "recursos humanos" '
        f'OR "recruiter" OR "selección de personal") "{empresa}"'
    )
    params = {
        "engine": "google",
        "q": consulta,
        "hl": "es",
        "gl": "es",
        "num": 10,
        "api_key": api_key,
    }
    try:
        datos = requests.get(URL_SERPAPI, params=params, timeout=30).json()
    except (requests.RequestException, ValueError) as error:
        print(f"    [OSINT] Error consultando SerpApi: {error}")
        return []

    if "error" in datos:
        print(f"    [OSINT] SerpApi devolvió un error: {datos['error']}")
        return []

    perfiles: list[dict] = []
    for resultado in datos.get("organic_results", []):
        enlace = resultado.get("link", "")
        if "linkedin.com/in" not in enlace:
            continue
        titulo = limpiar_texto(resultado.get("title", ""))
        perfiles.append({
            "nombre": titulo.split(" - ")[0].strip() or "Perfil de LinkedIn",
            "titulo": titulo,
            "url": enlace,
        })
        if len(perfiles) == 3:
            break

    cache[clave] = perfiles
    guardar_json(RUTA_CACHE, cache)
    return perfiles
