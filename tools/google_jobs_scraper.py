"""Extracción de ofertas desde Google Jobs a través de SerpApi.

Cada consulta consume 1 búsqueda de la cuota de SerpApi (100/mes en el plan
gratuito). Google Jobs agrega ofertas de InfoJobs, Indeed, LinkedIn y de los
portales de empleo de las propias empresas (Workday, SuccessFactors...).

De cada oferta se captura:
  - `portal` (campo "via" de Google): InfoJobs, LinkedIn, web de la empresa...
  - `publicado` (posted_at): se usa para quedarse solo con las últimas 24 h.
"""

from __future__ import annotations

import hashlib
import os
import re

import requests

from .utils import limpiar_texto

URL_SERPAPI = "https://serpapi.com/search.json"

# Unidades de tiempo que implican más de 24 horas
_UNIDADES_ANTIGUAS = ("semana", "week", "mes", "month", "año", "ano", "year")


def _es_reciente(publicado: str) -> bool:
    """True si el texto de antigüedad ('hace 3 horas', '2 days ago'...) es ≤ 24 h.

    Si no hay dato, se considera reciente (la memoria de ofertas vistas ya
    evita procesar dos veces la misma oferta).
    """
    texto = (publicado or "").lower()
    if not texto.strip():
        return True
    if any(unidad in texto for unidad in _UNIDADES_ANTIGUAS):
        return False
    coincidencia = re.search(r"(\d+)", texto)
    numero = int(coincidencia.group(1)) if coincidencia else 0
    if "día" in texto or "dia" in texto or "day" in texto:
        return numero <= 1
    # horas, minutos, "recién publicada", etc.
    return True


def buscar_ofertas(consulta: str) -> list[dict]:
    """Lanza una consulta a Google Jobs (1 unidad de cuota) y devuelve las ofertas ≤ 24 h."""
    api_key = os.environ.get("SERPAPI_API_KEY", "")
    if not api_key:
        print("    [Google Jobs] SERPAPI_API_KEY no configurada; se omite esta fuente.")
        return []

    params = {
        "engine": "google_jobs",
        "q": consulta,
        "hl": "es",
        "gl": "es",
        "api_key": api_key,
    }
    try:
        respuesta = requests.get(URL_SERPAPI, params=params, timeout=30)
        datos = respuesta.json()
    except (requests.RequestException, ValueError) as error:
        print(f"    [Google Jobs] Error consultando SerpApi: {error}")
        return []

    if "error" in datos:
        print(f"    [Google Jobs] SerpApi devolvió un error: {datos['error']}")
        return []

    ofertas: list[dict] = []
    for resultado in datos.get("jobs_results", []):
        id_bruto = resultado.get("job_id", "")
        if not id_bruto:
            continue

        extensiones = resultado.get("detected_extensions") or {}
        publicado = limpiar_texto(extensiones.get("posted_at", ""))
        if not _es_reciente(publicado):
            continue  # solo ofertas de las últimas 24 horas

        # El job_id de Google es un token largo: se acorta con un hash estable.
        id_oferta = "googlejobs-" + hashlib.md5(id_bruto.encode("utf-8")).hexdigest()[:16]

        opciones = resultado.get("apply_options", [])
        url = opciones[0].get("link", "") if opciones else resultado.get("share_link", "")

        ofertas.append({
            "id": id_oferta,
            "titulo": limpiar_texto(resultado.get("title", "")),
            "empresa": limpiar_texto(resultado.get("company_name", "Desconocida")),
            "ubicacion": limpiar_texto(resultado.get("location", "")),
            "url": url,
            "descripcion": limpiar_texto(resultado.get("description", ""), maximo=6000),
            "fuente": "Google Jobs",
            "portal": limpiar_texto(resultado.get("via", "")) or "Google Jobs",
            "publicado": publicado,
        })
    return ofertas
