"""Configuración de búsqueda y fase de EXTRACCIÓN del pipeline.

════════════════════════════════════════════════════════════════════
  >>> ESTE ES EL ARCHIVO QUE DEBES EDITAR PARA AJUSTAR TUS BÚSQUEDAS <<<
════════════════════════════════════════════════════════════════════

Combina tres fuentes:
  1. LinkedIn (endpoint público, gratuito): una petición por término y ubicación.
  2. Google Jobs vía SerpApi: agrega InfoJobs, Indeed y muchos portales.
  3. Portales de empleo de las empresas prioritarias (jobs.moeveglobal.com,
     jobs.enel.com...): vigilados vía búsqueda de Google restringida al dominio.

Presupuesto SerpApi (100 búsquedas/mes gratis): 1 consulta Google Jobs +
1 consulta de portales al día ≈ 60/mes, más el OSINT (≤1/día, con caché).
"""

from __future__ import annotations

from . import google_jobs_scraper, linkedin_scraper, portales_scraper

# ── 1) Búsquedas en LinkedIn (solo Huelva) ──────────────────────────────────
TERMINOS_LINKEDIN = [
    "ingeniero de procesos",
    "ingeniero de proyectos",
    "ingeniero eléctrico",
    "ingeniero fotovoltaico",
    "ingeniero de mantenimiento",
    "ingeniero industrial",
    "ingeniero energía",
    "ingeniero eficiencia energética",
    "ingeniero hidrógeno verde",
    "ingeniero junior",
    "técnico energías renovables",
]

UBICACIONES_LINKEDIN = [
    "Huelva, España",
]

# Antigüedad máxima de las ofertas en segundos (86400 = últimas 24 h).
ANTIGUEDAD_SEGUNDOS = 86400

# 1 página = hasta 25 resultados por término y ubicación.
MAX_PAGINAS_LINKEDIN = 1

# ── 2) Empresas prioritarias ────────────────────────────────────────────────
# Ofertas de estas empresas reciben un bonus de puntuación, nunca se descartan
# por el filtro rápido y van destacadas en el reporte. En minúsculas;
# se compara por subcadena del nombre de la empresa.
EMPRESAS_PRIORITARIAS = [
    "moeve",
    "cepsa",       # antiguo nombre de Moeve; algunas ofertas siguen publicándose así
    "endesa",
    "enel",        # matriz de Endesa
]

# Portales de empleo propios que se vigilan directamente (añade aquí más webs:
# basta con el nombre de la empresa y el dominio de su portal de empleo).
PORTALES_EMPRESA = [
    {"empresa": "Moeve", "dominio": "jobs.moeveglobal.com"},
    {"empresa": "Endesa / Enel", "dominio": "jobs.enel.com"},
]

# Búsquedas dirigidas en LinkedIn para no perder sus becas y programas
# (en toda España: las becas a veces se publican sin provincia, y el filtro
#  de Gemini ya descarta lo que no encaje).
TERMINOS_EMPRESAS = [
    "Moeve ingeniero",
    "Moeve beca",
    "Endesa ingeniero Huelva",
    "Endesa beca ingeniero",
]

# ── 3) Consultas en Google Jobs (SerpApi) ───────────────────────────────────
# Cada línea gasta 1 búsqueda de cuota AL DÍA. Consulta corta y enfocada:
# encadenar muchos OR hace que Google devuelva resultados irrelevantes
# (camareros, reponedores...) y de otras provincias, desperdiciando la cuota
# de Gemini. Los filtros rápidos de abajo rematan la limpieza.
CONSULTAS_GOOGLE_JOBS = [
    "ingeniero Huelva",
]

# ── 4) Filtros rápidos (no gastan llamadas a Gemini) ────────────────────────
# Descarte por título:
PALABRAS_EXCLUIR = [
    "senior",
    "sr.",
    "manager",
    "director",
    "jefe de",
    "comercial",
    "ventas",
    "teleoperador",
]

# El título debe contener al menos una de estas raíces para pasar a la IA
# (salvo empresas prioritarias). Evita analizar camareros, reponedores, etc.
PALABRAS_CLAVE_TITULO = [
    "ingenier", "engineer", "técnic", "tecnic", "beca", "prácticas", "practicas",
    "energ", "fotovolta", "solar", "eléctric", "electric", "mantenimiento",
    "proceso", "proyect", "industrial", "hidrógeno", "hidrogeno", "renovab",
    "graduado", "junior",
]

# Ubicaciones genéricas aceptadas tal cual (además de todo lo que contenga
# "huelva" o "remoto"). Lo demás (Sevilla, Madrid...) se descarta.
UBICACIONES_GENERICAS = ("", "españa", "spain", "andalucía", "andalucia")


def es_empresa_prioritaria(nombre_empresa: str) -> bool:
    """True si la empresa está en la lista de prioritarias (comparación por subcadena)."""
    nombre = (nombre_empresa or "").lower()
    return any(clave in nombre for clave in EMPRESAS_PRIORITARIAS)


def recolectar_ofertas() -> list[dict]:
    """Ejecuta todas las búsquedas configuradas y devuelve una lista de ofertas únicas."""
    ofertas: dict[str, dict] = {}

    print("[Extracción] LinkedIn (Huelva)...")
    for ubicacion in UBICACIONES_LINKEDIN:
        for termino in TERMINOS_LINKEDIN:
            encontradas = linkedin_scraper.buscar_ofertas(
                termino, ubicacion, MAX_PAGINAS_LINKEDIN, ANTIGUEDAD_SEGUNDOS
            )
            print(f"  · '{termino}' en {ubicacion}: {len(encontradas)} ofertas")
            for oferta in encontradas:
                ofertas.setdefault(oferta["id"], oferta)

    print("[Extracción] LinkedIn (empresas prioritarias)...")
    for termino in TERMINOS_EMPRESAS:
        encontradas = linkedin_scraper.buscar_ofertas(
            termino, "España", MAX_PAGINAS_LINKEDIN, ANTIGUEDAD_SEGUNDOS
        )
        print(f"  · '{termino}': {len(encontradas)} ofertas")
        for oferta in encontradas:
            ofertas.setdefault(oferta["id"], oferta)

    print("[Extracción] Google Jobs (SerpApi)...")
    for consulta in CONSULTAS_GOOGLE_JOBS:
        encontradas = google_jobs_scraper.buscar_ofertas(consulta)
        print(f"  · '{consulta}': {len(encontradas)} ofertas")
        for oferta in encontradas:
            ofertas.setdefault(oferta["id"], oferta)

    print("[Extracción] Portales de empresas prioritarias (SerpApi)...")
    encontradas = portales_scraper.buscar_ofertas(PORTALES_EMPRESA)
    print(f"  · {len(PORTALES_EMPRESA)} portales vigilados: {len(encontradas)} ofertas")
    for oferta in encontradas:
        ofertas.setdefault(oferta["id"], oferta)

    return list(ofertas.values())


def pasa_filtro_rapido(oferta: dict) -> bool:
    """Descarta ofertas claramente fuera de perfil antes de llamar a la IA.

    Comprueba título (exclusiones y palabras clave) y ubicación (solo Huelva,
    remoto o genéricas). Las empresas prioritarias nunca se descartan aquí.
    """
    if es_empresa_prioritaria(oferta.get("empresa", "")):
        return True

    titulo = oferta["titulo"].lower()
    if any(palabra in titulo for palabra in PALABRAS_EXCLUIR):
        return False
    if not any(clave in titulo for clave in PALABRAS_CLAVE_TITULO):
        return False

    ubicacion = (oferta.get("ubicacion") or "").lower().strip()
    if "huelva" in ubicacion or "remot" in ubicacion:
        return True
    return ubicacion in UBICACIONES_GENERICAS
