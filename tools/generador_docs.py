"""Fase de GENERACIÓN DE DOCUMENTOS: compila el CV y la carta en PDF con pdflatex.

Sustituye los marcadores de las plantillas .tex y compila dos pasadas de
pdflatex en un directorio temporal. Marcadores reconocidos:

  Comunes:      [COMPANY_NAME], [JOB_TITLE]
  Solo CV:      [HEADLINE], [PROFILE_SUMMARY], [INERCO_BULLETS]
  Solo carta:   [LETTER_BODY], [FECHA]

Si añades tus propias plantillas, mantén intactos [COMPANY_NAME] y [JOB_TITLE].
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

from .utils import DIR_PLANTILLAS, DIR_SALIDA, escapar_latex, sanitizar_nombre_archivo

PLANTILLA_CV = os.path.join(DIR_PLANTILLAS, "cv", "plantilla_cv.tex")
PLANTILLA_CARTA = os.path.join(DIR_PLANTILLAS, "carta", "plantilla_carta.tex")
DIR_ASSETS = os.path.join(DIR_PLANTILLAS, "assets")

BULLETS_INERCO_POR_DEFECTO = [
    "Optimización de plantas de recuperación de azufre (SRE) con Symmetry.",
    "Identificación de compuestos químicos en gases mediante cromatografía.",
    "Automatización de los informes del departamento con una aplicación en Python "
    "(de 20 horas a 1 hora por informe).",
]


def hay_pdflatex() -> bool:
    """Comprueba si pdflatex está disponible en el sistema."""
    return shutil.which("pdflatex") is not None


def _renderizar(ruta_plantilla: str, variables: dict[str, str]) -> str:
    """Lee una plantilla .tex y sustituye todos los marcadores por sus valores."""
    with open(ruta_plantilla, "r", encoding="utf-8") as archivo:
        contenido = archivo.read()
    for marcador, valor in variables.items():
        contenido = contenido.replace(marcador, valor)
    return contenido


def _compilar(codigo_tex: str, nombre_pdf: str) -> str | None:
    """Compila un documento LaTeX y devuelve la ruta del PDF en `salida/`, o None si falla."""
    os.makedirs(DIR_SALIDA, exist_ok=True)

    with tempfile.TemporaryDirectory() as temporal:
        # Los assets (foto, logos...) deben estar junto al .tex al compilar.
        archivos_assets = os.listdir(DIR_ASSETS) if os.path.isdir(DIR_ASSETS) else []
        for archivo in archivos_assets:
            shutil.copy(os.path.join(DIR_ASSETS, archivo), temporal)

        ruta_tex = os.path.join(temporal, "documento.tex")
        with open(ruta_tex, "w", encoding="utf-8") as archivo:
            archivo.write(codigo_tex)

        proceso = None
        for _ in range(2):  # dos pasadas para que la maquetación quede estable
            proceso = subprocess.run(
                ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "documento.tex"],
                cwd=temporal,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if proceso.returncode != 0:
                break

        ruta_pdf = os.path.join(temporal, "documento.pdf")
        if proceso is None or proceso.returncode != 0 or not os.path.exists(ruta_pdf):
            print(f"    [LaTeX] Fallo al compilar {nombre_pdf}. Últimas líneas del log:")
            if proceso is not None:
                for linea in proceso.stdout.splitlines()[-12:]:
                    print(f"      {linea}")
            return None

        destino = os.path.join(DIR_SALIDA, nombre_pdf)
        shutil.copy(ruta_pdf, destino)
        return destino


def generar_documentos(oferta: dict, analisis: dict, fecha: str) -> dict[str, str]:
    """Genera el CV y la carta personalizados para una oferta.

    Devuelve un diccionario {'cv': ruta, 'carta': ruta} solo con los PDFs
    que se hayan compilado correctamente.
    """
    if not hay_pdflatex():
        print("    [LaTeX] pdflatex no está instalado; se omite la generación de PDFs.")
        return {}

    empresa = escapar_latex(oferta["empresa"])
    puesto = escapar_latex(oferta["titulo"])

    bullets = analisis.get("bullets_inerco") or BULLETS_INERCO_POR_DEFECTO
    variables_cv = {
        "[COMPANY_NAME]": empresa,
        "[JOB_TITLE]": puesto,
        "[HEADLINE]": escapar_latex(analisis.get("titular_cv") or "INGENIERO DE ENERGÍA"),
        "[PROFILE_SUMMARY]": escapar_latex(analisis.get("perfil_cv", "")),
        "[INERCO_BULLETS]": "\n".join(f"\\item {escapar_latex(b)}" for b in bullets),
    }
    variables_carta = {
        "[COMPANY_NAME]": empresa,
        "[JOB_TITLE]": puesto,
        "[LETTER_BODY]": escapar_latex(analisis.get("cuerpo_carta", "")),
        "[FECHA]": escapar_latex(fecha),
    }

    sufijo = sanitizar_nombre_archivo(oferta["empresa"])
    rutas: dict[str, str] = {}

    pdf_cv = _compilar(_renderizar(PLANTILLA_CV, variables_cv), f"CV_JoseCoronel_{sufijo}.pdf")
    if pdf_cv:
        rutas["cv"] = pdf_cv

    pdf_carta = _compilar(
        _renderizar(PLANTILLA_CARTA, variables_carta), f"Carta_JoseCoronel_{sufijo}.pdf"
    )
    if pdf_carta:
        rutas["carta"] = pdf_carta

    return rutas
