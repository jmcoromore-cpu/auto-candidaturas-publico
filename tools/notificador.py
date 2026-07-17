"""Fase de NOTIFICACIÓN: compone y envía el reporte diario por Gmail.

Usa SMTP con SSL y una contraseña de aplicación de Google (App Password).
Variables de entorno necesarias: EMAIL_REMITENTE y EMAIL_APP_PASSWORD
(EMAIL_DESTINATARIO es opcional; por defecto se envía al propio remitente).

El reporte se organiza en dos secciones: primero las ofertas localizadas en
LinkedIn/InfoJobs y después las publicadas en portales y webs de empresas.
Las empresas prioritarias van destacadas y encabezan su sección.
"""

from __future__ import annotations

import html
import os
import smtplib
from email.message import EmailMessage

MAX_ADJUNTOS_MB = 18  # margen por debajo del límite de 25 MB de Gmail

TITULOS_SECCIONES = {
    0: "Ofertas en LinkedIn e InfoJobs",
    1: "Ofertas en portales y webs de empresas",
}


def _bloque_oferta(resultado: dict) -> str:
    """Genera el bloque HTML de una oferta seleccionada."""
    oferta = resultado["oferta"]
    analisis = resultado["analisis"]
    reclutadores = resultado.get("reclutadores", [])
    e = html.escape

    insignia = (
        '<span style="background:#b8860b;color:#fff;border-radius:4px;'
        'padding:2px 8px;font-size:12px;margin-left:6px;">&#9733; Empresa prioritaria</span>'
        if analisis.get("prioritaria") else ""
    )

    publicado = oferta.get("publicado", "")
    meta = " &middot; ".join(
        parte for parte in (
            e(oferta.get("ubicacion", "")),
            e(oferta.get("portal") or oferta.get("fuente", "")),
            e(publicado) if publicado else "",
        ) if parte
    )

    lineas_reclutadores = "".join(
        f'<li><a href="{e(perfil["url"])}">{e(perfil["titulo"])}</a></li>'
        for perfil in reclutadores
    ) or "<li>Sin perfiles localizados (o búsqueda OSINT no ejecutada hoy)</li>"

    mensaje = e(analisis.get("mensaje_linkedin", "") or "—")

    return f"""
    <div style="border:1px solid #d8dee9;border-radius:8px;padding:16px;margin-bottom:16px;">
      <h3 style="margin:0 0 4px;color:#1b3155;">{e(oferta["titulo"])} &middot; {e(oferta["empresa"])}{insignia}</h3>
      <p style="margin:0 0 8px;color:#555;">
        {meta} &middot; Encaje: <b>{analisis.get("puntuacion", "?")}/100</b>
      </p>
      <p style="margin:0 0 8px;">{e(analisis.get("motivo", ""))}</p>
      <p style="margin:0 0 10px;"><a href="{e(oferta["url"])}">Ver la oferta</a></p>
      <p style="margin:0 0 4px;"><b>Perfiles de Talent Acquisition:</b></p>
      <ul style="margin:0 0 10px;">{lineas_reclutadores}</ul>
      <p style="margin:0 0 4px;"><b>Borrador de mensaje para LinkedIn:</b></p>
      <p style="margin:0;background:#f4f6f8;padding:10px;border-radius:6px;white-space:pre-wrap;">{mensaje}</p>
    </div>"""


def componer_reporte(resultados: list[dict], descartadas: int, fecha: str) -> str:
    """Compone el cuerpo HTML del reporte, agrupado por tipo de portal."""
    secciones = ""
    for grupo in (0, 1):
        del_grupo = [r for r in resultados if r.get("grupo", 1) == grupo]
        if not del_grupo:
            continue
        secciones += (
            f'<h3 style="color:#1b3155;border-bottom:2px solid #1b3155;'
            f'padding-bottom:4px;">{TITULOS_SECCIONES[grupo]}</h3>'
        )
        secciones += "".join(_bloque_oferta(r) for r in del_grupo)

    if not secciones:
        secciones = "<p>Hoy no hay ofertas nuevas que encajen con tu perfil.</p>"

    return f"""<html><body style="font-family:Arial,Helvetica,sans-serif;max-width:720px;margin:auto;color:#222;">
      <h2 style="color:#1b3155;">Reporte de candidaturas &middot; {html.escape(fecha)}</h2>
      <p><b>{len(resultados)}</b> ofertas seleccionadas &middot; <b>{descartadas}</b> descartadas por la IA.</p>
      {secciones}
      <p style="color:#888;font-size:12px;">Los CV y cartas personalizados van adjuntos en PDF.
      Generado automáticamente por <i>auto-candidaturas</i>.</p>
    </body></html>"""


def enviar_email(asunto: str, cuerpo_html: str, adjuntos: list[str]) -> bool:
    """Envía el reporte con los PDFs adjuntos. Devuelve True si el envío tuvo éxito."""
    remitente = os.environ.get("EMAIL_REMITENTE", "")
    password = os.environ.get("EMAIL_APP_PASSWORD", "")
    destinatario = os.environ.get("EMAIL_DESTINATARIO", "") or remitente

    if not (remitente and password):
        print("[Email] Falta EMAIL_REMITENTE o EMAIL_APP_PASSWORD; no se envía el reporte.")
        return False

    mensaje = EmailMessage()
    mensaje["From"] = remitente
    mensaje["To"] = destinatario
    mensaje["Subject"] = asunto
    mensaje.set_content("Este reporte requiere un cliente de correo con soporte HTML.")
    mensaje.add_alternative(cuerpo_html, subtype="html")

    total_bytes = 0
    for ruta in adjuntos:
        try:
            with open(ruta, "rb") as archivo:
                datos = archivo.read()
        except OSError:
            continue
        total_bytes += len(datos)
        if total_bytes > MAX_ADJUNTOS_MB * 1024 * 1024:
            print("[Email] Límite de adjuntos alcanzado; el resto queda en salida/ (artefacto del workflow).")
            break
        mensaje.add_attachment(
            datos,
            maintype="application",
            subtype="pdf",
            filename=os.path.basename(ruta),
        )

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=60) as smtp:
            smtp.login(remitente, password)
            smtp.send_message(mensaje)
        return True
    except (smtplib.SMTPException, OSError) as error:
        print(f"[Email] Error enviando el reporte: {error}")
        return False
