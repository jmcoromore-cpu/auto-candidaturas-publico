"""Extracción de ofertas recientes desde el buscador público de LinkedIn (sin login).

Usa el endpoint 'jobs-guest' que alimenta el listado público de empleos de LinkedIn.
No requiere API key, pero LinkedIn limita el ritmo de peticiones y bloquea con
frecuencia las IPs compartidas de GitHub Actions.

Por eso este módulo incluye un CORTACIRCUITOS: si varias peticiones seguidas
fallan (HTTP 429/403/999...), se deja de intentar durante el resto de la
ejecución. El pipeline continúa con Google Jobs y termina en pocos minutos en
lugar de agotar el tiempo del workflow; al día siguiente se reintenta.

Nota: el scraping de LinkedIn va contra sus condiciones de uso aunque los datos
sean públicos. Úsalo con moderación y bajo tu responsabilidad (ver README).
"""

from __future__ import annotations

import random
import re
import time

import requests
from bs4 import BeautifulSoup

from .utils import limpiar_texto

URL_BUSQUEDA = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
URL_DETALLE = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{id_numerico}"

CABECERAS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-ES,es;q=0.9",
}

# ── Cortacircuitos ──────────────────────────────────────────────────────────
LIMITE_FALLOS_SEGUIDOS = 3   # peticiones fallidas seguidas antes de desistir
_fallos_seguidos = 0
_aviso_mostrado = False


def _esta_bloqueado() -> bool:
    """True si LinkedIn ha bloqueado tantas peticiones seguidas que ya no compensa insistir."""
    global _aviso_mostrado
    if _fallos_seguidos >= LIMITE_FALLOS_SEGUIDOS:
        if not _aviso_mostrado:
            print(
                "    [LinkedIn] Demasiados bloqueos seguidos: se omite LinkedIn durante "
                "el resto de la ejecución (se reintentará en la próxima)."
            )
            _aviso_mostrado = True
        return True
    return False


def _registrar_resultado(exito: bool) -> None:
    """Actualiza el contador del cortacircuitos tras cada petición."""
    global _fallos_seguidos
    _fallos_seguidos = 0 if exito else _fallos_seguidos + 1


def _peticion_con_reintentos(url: str, params: dict | None = None, intentos: int = 2):
    """GET con reintentos cortos. Devuelve None si LinkedIn bloquea o falla la red.

    Los reintentos son deliberadamente pocos y con esperas breves: en GitHub
    Actions es mejor desistir rápido (cortacircuitos) que agotar el timeout.
    """
    for intento in range(intentos):
        try:
            respuesta = requests.get(url, params=params, headers=CABECERAS, timeout=15)
        except requests.RequestException as error:
            print(f"    [LinkedIn] Error de red: {error}")
            time.sleep(4)
            continue
        if respuesta.status_code == 200:
            return respuesta
        if respuesta.status_code in (429, 500, 502, 503) and intento < intentos - 1:
            espera = 8 + random.uniform(0, 4)
            print(f"    [LinkedIn] HTTP {respuesta.status_code}; reintento en {espera:.0f}s...")
            time.sleep(espera)
            continue
        print(f"    [LinkedIn] HTTP {respuesta.status_code}; se desiste de esta petición.")
        return None
    return None


def _parsear_tarjeta(tarjeta) -> dict | None:
    """Convierte una tarjeta HTML del listado en un diccionario de oferta."""
    enlace = tarjeta.find("a", class_="base-card__full-link") or tarjeta.find("a", href=True)
    titulo = tarjeta.find("h3", class_="base-search-card__title") or tarjeta.find("h3")
    empresa = tarjeta.find("h4", class_="base-search-card__subtitle") or tarjeta.find("h4")
    lugar = tarjeta.find("span", class_="job-search-card__location")
    fecha = tarjeta.find("time")
    if not (enlace and titulo):
        return None

    url = enlace["href"].split("?")[0]
    urn = tarjeta.get("data-entity-urn", "") or ""
    coincidencia = re.search(r"(\d{8,})", urn) or re.search(r"-(\d{8,})/?$", url)
    if not coincidencia:
        return None

    return {
        "id": f"linkedin-{coincidencia.group(1)}",
        "titulo": limpiar_texto(titulo.get_text()),
        "empresa": limpiar_texto(empresa.get_text()) if empresa else "Desconocida",
        "ubicacion": limpiar_texto(lugar.get_text()) if lugar else "",
        "url": url,
        "descripcion": "",  # se obtiene después, solo para las ofertas que interesan
        "fuente": "LinkedIn",
        "portal": "LinkedIn",
        "publicado": limpiar_texto(fecha.get_text()) if fecha else "",
    }


def buscar_ofertas(termino: str, ubicacion: str, max_paginas: int = 1,
                   antiguedad_segundos: int = 86400) -> list[dict]:
    """Busca ofertas públicas en LinkedIn para un término y una ubicación.

    `antiguedad_segundos` filtra por fecha de publicación (86400 = últimas 24 h).
    Cada página devuelve hasta 25 resultados. Si el cortacircuitos está abierto,
    devuelve [] al instante.
    """
    if _esta_bloqueado():
        return []

    ofertas: list[dict] = []
    for pagina in range(max_paginas):
        params = {
            "keywords": termino,
            "location": ubicacion,
            "f_TPR": f"r{antiguedad_segundos}",
            "start": pagina * 25,
        }
        respuesta = _peticion_con_reintentos(URL_BUSQUEDA, params)
        _registrar_resultado(respuesta is not None)
        if respuesta is None or not respuesta.text.strip():
            break

        sopa = BeautifulSoup(respuesta.text, "html.parser")
        tarjetas = sopa.find_all("div", class_="base-card") or sopa.find_all("li")
        if not tarjetas:
            break

        for tarjeta in tarjetas:
            oferta = _parsear_tarjeta(tarjeta)
            if oferta:
                ofertas.append(oferta)

        time.sleep(random.uniform(2, 4))  # pausa cortés entre páginas
    return ofertas


def obtener_descripcion(id_oferta: str) -> str:
    """Descarga la descripción completa de una oferta a partir de su id ('linkedin-123...').

    Si el cortacircuitos está abierto devuelve "" al instante; la oferta se
    analiza igualmente con su título, empresa y ubicación.
    """
    if _esta_bloqueado():
        return ""

    id_numerico = id_oferta.replace("linkedin-", "")
    respuesta = _peticion_con_reintentos(URL_DETALLE.format(id_numerico=id_numerico))
    _registrar_resultado(respuesta is not None)
    if respuesta is None:
        return ""
    sopa = BeautifulSoup(respuesta.text, "html.parser")
    nodo = sopa.find("div", class_="show-more-less-html__markup")
    texto = nodo.get_text(separator="\n") if nodo else ""
    time.sleep(random.uniform(2, 4))  # pausa cortés entre descargas de detalle
    return limpiar_texto(texto, maximo=6000)
