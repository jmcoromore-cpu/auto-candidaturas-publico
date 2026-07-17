"""Fase de FILTRADO: análisis de ofertas con la API de Gemini (REST v1beta).

Se llama a la API REST directamente con `requests` (sin SDK) para minimizar
dependencias. Modelo por defecto: `gemini-2.5-flash` (tier gratuito, ~10
peticiones/minuto y cuota diaria limitada), configurable con GEMINI_MODEL.

Incluye un CORTACIRCUITOS: si la cuota se agota o la API cae (HTTP 429/5xx
persistente), se deja de llamar a Gemini durante el resto de la ejecución.
El pipeline envía entonces el reporte con lo analizado hasta ese momento,
en lugar de consumir reintentos hasta morir por timeout.
"""

from __future__ import annotations

import json
import os
import time

import requests

URL_GEMINI = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
PAUSA_ENTRE_LLAMADAS = 7        # segundos entre llamadas correctas (límite RPM)
ESPERAS_REINTENTO = (12, 30)    # esperas ante 429/5xx; pocas y cortas a propósito

# ── Cortacircuitos ──────────────────────────────────────────────────────────
LIMITE_FALLOS_SEGUIDOS = 3
_fallos_seguidos = 0
_aviso_mostrado = False


def esta_agotado() -> bool:
    """True si Gemini acumula demasiados fallos seguidos (cuota agotada o caída)."""
    global _aviso_mostrado
    if _fallos_seguidos >= LIMITE_FALLOS_SEGUIDOS:
        if not _aviso_mostrado:
            print(
                "    [Gemini] Demasiados fallos seguidos (¿cuota diaria agotada?): se "
                "detiene el análisis y el reporte saldrá con lo procesado hasta ahora."
            )
            _aviso_mostrado = True
        return True
    return False


def _registrar(exito: bool) -> None:
    """Actualiza el contador del cortacircuitos."""
    global _fallos_seguidos
    _fallos_seguidos = 0 if exito else _fallos_seguidos + 1


def analizar_oferta(prompt: str) -> dict | None:
    """Envía el prompt de análisis a Gemini y devuelve el JSON parseado, o None si falla."""
    if esta_agotado():
        return None

    api_key = os.environ.get("GEMINI_API_KEY", "")
    modelo = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    if not api_key:
        print("    [Gemini] GEMINI_API_KEY no configurada; no se puede filtrar.")
        return None

    cuerpo = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.4,
        },
    }

    for intento in range(len(ESPERAS_REINTENTO) + 1):
        try:
            respuesta = requests.post(
                URL_GEMINI.format(modelo=modelo),
                headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                json=cuerpo,
                timeout=60,
            )
        except requests.RequestException as error:
            print(f"    [Gemini] Error de red: {error}")
            time.sleep(8)
            continue

        if respuesta.status_code == 200:
            _registrar(True)
            time.sleep(PAUSA_ENTRE_LLAMADAS)  # respeta el límite de peticiones/minuto
            return _extraer_json(respuesta.json())

        if respuesta.status_code in (429, 500, 503) and intento < len(ESPERAS_REINTENTO):
            espera = ESPERAS_REINTENTO[intento]
            print(f"    [Gemini] HTTP {respuesta.status_code}; espera de {espera}s...")
            time.sleep(espera)
            continue

        print(f"    [Gemini] HTTP {respuesta.status_code}: {respuesta.text[:200]}")
        break

    _registrar(False)
    return None


def _extraer_json(datos: dict) -> dict | None:
    """Extrae y parsea el JSON devuelto por el modelo."""
    try:
        texto = datos["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        print(f"    [Gemini] Respuesta sin contenido: {json.dumps(datos)[:300]}")
        return None

    # Por robustez: algunos modelos envuelven el JSON en un bloque de código.
    texto = texto.strip()
    if texto.startswith("```"):
        texto = texto.strip("`")
        texto = texto.removeprefix("json").strip()

    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        print(f"    [Gemini] JSON inválido en la respuesta: {texto[:300]}")
        return None
