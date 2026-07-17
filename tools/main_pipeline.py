"""Orquestador principal del pipeline automático de candidaturas.

Fases: EXTRACCIÓN → FILTRADO (Gemini) → DOCUMENTOS (LaTeX) → OSINT → NOTIFICACIÓN.

════════════════════════════════════════════════════════════════════
  >>> EDITA `PERFIL_CANDIDATO` PARA AJUSTAR TU EXPERIENCIA <<<
      (los términos de búsqueda se editan en tools/batch_search.py)
════════════════════════════════════════════════════════════════════

Ejecución:
    python -m tools.main_pipeline                 → pipeline completo
    MODO_PRUEBA=1 python -m tools.main_pipeline   → prueba local sin APIs ni email
                                                    (usa ofertas simuladas y guarda
                                                    el reporte en salida/)

Variables de entorno opcionales de ajuste:
    MAX_ANALISIS_DIARIO   nº máx. de ofertas analizadas con Gemini por día (def. 20)
    UMBRAL_PUNTUACION     puntuación mínima (0-100) para aceptar una oferta (def. 60)
    MAX_OSINT_DIARIO      nº máx. de búsquedas OSINT nuevas por día (def. 1)
    ENVIAR_REPORTE_VACIO  "1" para enviar email aunque no haya resultados (def. no)
    LIMITE_MINUTOS        presupuesto de tiempo del pipeline (def. 18): al agotarse
                          se salta directamente al envío del email con lo que haya
"""

from __future__ import annotations

import datetime
import os
import time

from . import batch_search, filtro_ia, generador_docs, linkedin_scraper, notificador, osint
from .utils import DIR_DATA, DIR_SALIDA, cargar_json, guardar_json

# Bonus de puntuación para ofertas de empresas prioritarias (Moeve, Endesa...)
BONUS_PRIORITARIA = 15

# ══════════════════════════════════════════════════════════════════════════
#  PERFIL PROFESIONAL DEL CANDIDATO (contexto que recibe Gemini)
# ══════════════════════════════════════════════════════════════════════════
PERFIL_CANDIDATO = """
Nombre: JUAN GARCÍA LÓPEZ (22 años, residente en Huelva, España).
Titulación: Grado en Ingeniería Industrial, Universidad de Sevilla (2022-2026).
Nota media 8,0; Trabajo de Fin de Grado: 10.
Especialización: química, con base sólida en el sector Oil&GAs.

Experiencia:
- Becario de ingeniería en MOEVE (febrero 2026 - agosto 2026), sector Oil&Gas:
  optimización de plantas de recuperación de azufre (SRE) con el simulador Symmetry;
  identificación de compuestos químicos en gases mediante cromatografía; automatizó
  todos los informes del departamento desarrollando una aplicación en Python que
  redujo el tiempo de elaboración de 20 horas a 1 hora.
- Profesor de química y profesor particular
  de Física, Matemáticas e Inglés (2023): comunicación y didáctica.

Proyectos académicos:
- Instalación fotovoltaica de autoconsumo: dimensionamiento según consumo real y
  radiación, estudio de retorno económico con y sin baterías, selección de panel,
  inversor y batería, y simulación completa en PVsyst.
- Central termosolar cilindroparabólica diseñada en SAM: viabilidad del HTF con
  aceite y con sales fundidas, optimización de horas de almacenamiento y múltiplo solar.
- Estudio de viabilidad técnica de un parque eólico offshore en el estrecho de
  Gibraltar: emplazamiento, turbina, cimentación y punto de conexión a tierra.

Herramientas: Excel, Python, MATLAB, PVsyst, SAM, AutoCAD, Symmetry.
Idiomas: español nativo, inglés B2 (Cambridge).
Otros: carnet de conducir, disponibilidad horaria total, curso de producción,
transporte y almacenaje de hidrógeno verde, curso de análisis y prevención de
riesgos laborales.

QUÉ BUSCA: puestos junior, de recién graduado o becas EN LA PROVINCIA DE HUELVA
(única zona aceptada, salvo trabajo 100 % remoto): ingeniero de procesos, de
proyectos, eléctrico, fotovoltaico, de mantenimiento, industrial, de eficiencia
energética, de hidrógeno verde o técnico relacionado con la energía.
Tienen interés especial las becas y programas de recién titulados de empresas
como Moeve (antigua Cepsa, refinería La Rábida en Palos de la Frontera) y
Endesa/Enel, aunque se publiquen en sus propios portales.
NO ENCAJA EN: puestos que exijan más de 3 años de experiencia, perfiles puramente
comerciales o de ventas, ni ofertas fuera de la provincia de Huelva (salvo remoto).
"""

# Prompt de análisis que se envía a Gemini para cada oferta.
PROMPT_ANALISIS = """Eres un experto en selección de personal técnico en España.

PERFIL DEL CANDIDATO:
{perfil}

OFERTA DE EMPLEO:
Puesto: {titulo}
Empresa: {empresa}
Ubicación: {ubicacion}
Descripción: {descripcion}

TAREA: analiza si el candidato encaja TÉCNICAMENTE en la oferta (requisitos,
experiencia exigida, ubicación). Sé exigente: descarta ofertas senior, comerciales
o de otro sector. Si encaja, redacta además el contenido personalizado solicitado,
sin inventar experiencia que el candidato no tenga.

Responde SOLO con un JSON válido con esta estructura exacta:
{{
  "encaja": true o false,
  "puntuacion": entero de 0 a 100 (encaje técnico global),
  "motivo": "1-2 frases explicando la decisión",
  "titular_cv": "titular corto en MAYÚSCULAS adaptado al puesto, p. ej. INGENIERO DE PROCESOS",
  "perfil_cv": "párrafo 'Mi perfil' del CV reescrito para esta oferta (55-75 palabras, primera persona, profesional y natural)",
  "bullets_inerco": ["exactamente 3 viñetas de la experiencia en INERCO reorientadas a lo que pide la oferta"],
  "cuerpo_carta": "cuerpo de la carta de presentación: 3 párrafos separados por líneas en blanco, 150-200 palabras en total, sin saludo ni despedida, mencionando la empresa y el puesto",
  "mensaje_linkedin": "mensaje de menos de 300 caracteres para enviar a una persona de selección de la empresa presentando la candidatura"
}}
Si "encaja" es false: deja los campos de texto como cadenas vacías y bullets_inerco como [].
"""

# ══════════════════════════════════════════════════════════════════════════
#  Datos simulados para MODO_PRUEBA=1 (prueba local sin gastar APIs)
# ══════════════════════════════════════════════════════════════════════════
OFERTAS_DE_EJEMPLO = [
    {
        "id": "prueba-001",
        "titulo": "Ingeniero/a Fotovoltaico Junior",
        "empresa": "Soluciones Solares & Andalucía S.L.",
        "ubicacion": "Huelva, Andalucía",
        "url": "https://ejemplo.invalid/oferta-fotovoltaica",
        "descripcion": "Buscamos ingeniero/a junior para diseño y simulación de plantas "
                       "fotovoltaicas de autoconsumo industrial. Imprescindible manejo de "
                       "PVsyst y AutoCAD. Se valora Python y curso de PRL. Contrato indefinido.",
        "fuente": "LinkedIn",
        "portal": "LinkedIn",
        "publicado": "hace 5 horas",
    },
    {
        "id": "prueba-002",
        "titulo": "Beca Ingeniero/a de Procesos - Programa Becas Moeve",
        "empresa": "Moeve",
        "ubicacion": "Palos de la Frontera, Huelva",
        "url": "https://ejemplo.invalid/beca-moeve",
        "descripcion": "Programa de becas para recién titulados en ingeniería. Rotación por "
                       "unidades de proceso de la refinería La Rábida. Se valora conocimiento "
                       "de simuladores de procesos y Python.",
        "fuente": "Google Jobs",
        "portal": "Web de Moeve",
        "publicado": "hace 3 horas",
    },
    {
        "id": "prueba-004",
        "titulo": "Camarero de Sala",
        "empresa": "Paradores",
        "ubicacion": "Gerena, Sevilla",
        "url": "https://ejemplo.invalid/oferta-camarero",
        "descripcion": "Servicio de sala en restaurante.",
        "fuente": "Google Jobs",
        "portal": "InfoJobs",
        "publicado": "hace 1 hora",
    },
    {
        "id": "prueba-003",
        "titulo": "Director Comercial Senior - Ventas Industriales",
        "empresa": "Ventas Industriales del Sur",
        "ubicacion": "Sevilla, Andalucía",
        "url": "https://ejemplo.invalid/oferta-comercial",
        "descripcion": "Más de 10 años de experiencia liderando equipos comerciales.",
        "fuente": "Google Jobs",
        "portal": "InfoJobs",
        "publicado": "hace 2 horas",
    },
]

ANALISIS_DE_EJEMPLO = {
    "encaja": True,
    "puntuacion": 88,
    "motivo": "Encaje alto: la oferta pide un perfil junior con PVsyst y AutoCAD, "
              "herramientas que el candidato domina por proyectos académicos y formación.",
    "titular_cv": "INGENIERO FOTOVOLTAICO",
    "perfil_cv": "Graduado en Ingeniería de la Energía por la Universidad de Sevilla, "
                 "especializado en energías renovables y eficiencia energética. He diseñado y "
                 "simulado en PVsyst una instalación fotovoltaica de autoconsumo completa, desde "
                 "el dimensionamiento hasta el análisis de retorno económico, y domino AutoCAD y "
                 "Python. Busco aportar rigor técnico y ganas de aprender al diseño de plantas "
                 "solares en Huelva.",
    "bullets_inerco": [
        "Optimicé plantas de recuperación de azufre (SRE) con el simulador Symmetry, "
        "aplicando criterios de eficiencia de procesos trasladables al diseño fotovoltaico.",
        "Automaticé los informes técnicos del departamento con una aplicación en Python, "
        "reduciendo su elaboración de 20 horas a 1 hora.",
        "Analicé compuestos químicos en gases mediante cromatografía, con rigor de "
        "laboratorio y documentación técnica.",
    ],
    "cuerpo_carta": "Me dirijo a ustedes para presentar mi candidatura al puesto de "
                    "Ingeniero/a Fotovoltaico Junior en Soluciones Solares & Andalucía S.L. Soy "
                    "graduado en Ingeniería de la Energía por la Universidad de Sevilla, "
                    "especializado en energías renovables, y resido en Huelva con disponibilidad "
                    "total.\n\nHe diseñado una instalación fotovoltaica de autoconsumo completa "
                    "simulada en PVsyst, estudiando su retorno económico con y sin baterías, y "
                    "manejo AutoCAD y Python con soltura. Durante mis prácticas en INERCO "
                    "automaticé los informes del departamento reduciendo su tiempo de elaboración "
                    "de 20 horas a 1 hora.\n\nMe motiva especialmente la oportunidad de "
                    "desarrollar plantas de autoconsumo industrial en mi provincia. Estaré "
                    "encantado de ampliar cualquier detalle en una entrevista.",
    "mensaje_linkedin": "Hola, soy José Manuel, ingeniero de la energía por la US. He visto la "
                        "oferta de Ingeniero Fotovoltaico Junior y encaja mucho con mi perfil "
                        "(PVsyst, AutoCAD, Python). Acabo de enviar mi candidatura; quedo a su "
                        "disposición. ¡Gracias!",
}

RECLUTADORES_DE_EJEMPLO = [
    {
        "nombre": "Ana García",
        "titulo": "Ana García - Talent Acquisition - Soluciones Solares",
        "url": "https://www.linkedin.com/in/ejemplo-ana-garcia",
    }
]


def _grupo_portal(oferta: dict) -> int:
    """Grupo de ordenación del reporte: 0 = LinkedIn/InfoJobs, 1 = resto (webs de empresas...)."""
    portal = (oferta.get("portal") or oferta.get("fuente", "")).lower()
    if oferta.get("fuente") == "LinkedIn" or "linkedin" in portal or "infojobs" in portal:
        return 0
    return 1


def ejecutar() -> None:
    """Ejecuta el pipeline completo de principio a fin."""
    fecha = datetime.date.today().strftime("%d/%m/%Y")
    modo_prueba = os.environ.get("MODO_PRUEBA") == "1"
    inicio = time.monotonic()
    limite_segundos = int(os.environ.get("LIMITE_MINUTOS", "18")) * 60

    def queda_tiempo() -> bool:
        return (time.monotonic() - inicio) < limite_segundos
    if modo_prueba:
        print("[Pipeline] MODO_PRUEBA activo: sin llamadas a APIs ni envío de email.\n")

    ruta_vistas = os.path.join(DIR_DATA, "ofertas_vistas.json")
    vistas: set[str] = set(cargar_json(ruta_vistas, []))
    procesadas: set[str] = set()

    # ── 1) EXTRACCIÓN ──────────────────────────────────────────────────────
    ofertas = OFERTAS_DE_EJEMPLO if modo_prueba else batch_search.recolectar_ofertas()
    print(f"\n[Pipeline] {len(ofertas)} ofertas recopiladas en total.")

    nuevas = [oferta for oferta in ofertas if oferta["id"] not in vistas]
    candidatas = []
    for oferta in nuevas:
        if batch_search.pasa_filtro_rapido(oferta):
            candidatas.append(oferta)
        else:
            procesadas.add(oferta["id"])  # descartada por título: no volver a mirarla
    print(f"[Pipeline] {len(nuevas)} nuevas; {len(candidatas)} pasan el filtro rápido por título.")

    maximo_analisis = int(os.environ.get("MAX_ANALISIS_DIARIO", "20"))
    candidatas = candidatas[:maximo_analisis]

    # Completar descripciones de LinkedIn (Google Jobs ya la incluye).
    if not modo_prueba:
        for oferta in candidatas:
            if oferta["fuente"] == "LinkedIn" and not oferta["descripcion"]:
                oferta["descripcion"] = linkedin_scraper.obtener_descripcion(oferta["id"])

    # ── 2) FILTRADO CON GEMINI ─────────────────────────────────────────────
    umbral = int(os.environ.get("UMBRAL_PUNTUACION", "60"))
    resultados: list[dict] = []
    descartadas = 0

    for oferta in candidatas:
        if not queda_tiempo():
            print("[Pipeline] Presupuesto de tiempo agotado: se pasa al envío del reporte.")
            break
        if not modo_prueba and filtro_ia.esta_agotado():
            break
        print(f"[Filtrado] {oferta['titulo']} · {oferta['empresa']}")
        if modo_prueba:
            analisis = dict(ANALISIS_DE_EJEMPLO)
        else:
            prompt = PROMPT_ANALISIS.format(
                perfil=PERFIL_CANDIDATO,
                titulo=oferta["titulo"],
                empresa=oferta["empresa"],
                ubicacion=oferta["ubicacion"],
                descripcion=oferta["descripcion"] or "(sin descripción disponible)",
            )
            analisis = filtro_ia.analizar_oferta(prompt)

        if analisis is None:
            # Fallo temporal de la API: la oferta NO se marca como vista
            # para reintentarla en la próxima ejecución si sigue publicada.
            continue

        procesadas.add(oferta["id"])
        try:
            puntuacion = int(analisis.get("puntuacion", 0))
        except (TypeError, ValueError):
            puntuacion = 0

        # Bonus para empresas prioritarias (Moeve, Endesa...)
        prioritaria = batch_search.es_empresa_prioritaria(oferta.get("empresa", ""))
        if prioritaria:
            puntuacion = min(100, puntuacion + BONUS_PRIORITARIA)
        analisis["puntuacion"] = puntuacion
        analisis["prioritaria"] = prioritaria

        if not analisis.get("encaja") or puntuacion < umbral:
            descartadas += 1
            continue
        resultados.append({
            "oferta": oferta,
            "analisis": analisis,
            "grupo": _grupo_portal(oferta),
        })

    print(f"[Pipeline] {len(resultados)} ofertas encajan; {descartadas} descartadas por la IA.")

    # Orden global: prioritarias primero, luego LinkedIn/InfoJobs, luego puntuación.
    # (El OSINT y los documentos se generan en este orden, de más a menos relevante.)
    resultados.sort(key=lambda r: (
        0 if r["analisis"].get("prioritaria") else 1,
        r["grupo"],
        -r["analisis"].get("puntuacion", 0),
    ))

    # ── 3) DOCUMENTOS (LaTeX)  +  4) OSINT ─────────────────────────────────
    adjuntos: list[str] = []
    max_osint = int(os.environ.get("MAX_OSINT_DIARIO", "1"))
    osint_realizadas = 0

    for resultado in resultados:
        oferta = resultado["oferta"]
        analisis = resultado["analisis"]

        if queda_tiempo():
            print(f"[Documentos] Generando CV y carta para {oferta['empresa']}...")
            rutas = generador_docs.generar_documentos(oferta, analisis, fecha)
            adjuntos.extend(rutas.values())
        else:
            print(f"[Documentos] Sin tiempo para los PDFs de {oferta['empresa']}; la oferta va igualmente en el reporte.")

        if modo_prueba:
            resultado["reclutadores"] = RECLUTADORES_DE_EJEMPLO
        elif osint_realizadas < max_osint:
            print(f"[OSINT] Buscando perfiles de selección en {oferta['empresa']}...")
            resultado["reclutadores"] = osint.buscar_reclutadores(oferta["empresa"])
            osint_realizadas += 1
        else:
            resultado["reclutadores"] = []

    # ── 5) NOTIFICACIÓN ────────────────────────────────────────────────────
    reporte_html = notificador.componer_reporte(resultados, descartadas, fecha)
    asunto = f"[Candidaturas] {len(resultados)} ofertas seleccionadas · {fecha}"

    if modo_prueba:
        os.makedirs(DIR_SALIDA, exist_ok=True)
        ruta_html = os.path.join(DIR_SALIDA, "reporte_prueba.html")
        with open(ruta_html, "w", encoding="utf-8") as archivo:
            archivo.write(reporte_html)
        print(f"[Email] MODO_PRUEBA: reporte guardado en {ruta_html} (no se envía).")
    elif resultados or os.environ.get("ENVIAR_REPORTE_VACIO") == "1":
        if notificador.enviar_email(asunto, reporte_html, adjuntos):
            print("[Email] Reporte enviado correctamente.")
    else:
        print("[Email] Sin resultados hoy; no se envía email (ENVIAR_REPORTE_VACIO=1 para forzarlo).")

    # ── Memoria de ofertas ya procesadas ───────────────────────────────────
    if not modo_prueba:
        vistas.update(procesadas)
        guardar_json(ruta_vistas, sorted(vistas))
    print("[Pipeline] Terminado.")


if __name__ == "__main__":
    ejecutar()
