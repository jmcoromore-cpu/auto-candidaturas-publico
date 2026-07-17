# auto-candidaturas

Pipeline automático de búsqueda de empleo que se ejecuta **solo, cada día a las 15:00 (España)** en GitHub Actions, sin servidor propio. Busca ofertas de ingeniería publicadas en las **últimas 24 horas en la provincia de Huelva**, las filtra con IA según tu perfil, genera CV y carta de presentación personalizados en PDF, localiza perfiles de Talent Acquisition de cada empresa y envía un reporte por email con todo listo para aplicar.

## Cómo funciona

| Fase | Qué hace | Módulo |
|---|---|---|
| 1. Extracción | Recopila ofertas de las últimas 24 h de LinkedIn (endpoint público) y Google Jobs (SerpApi), que agrega InfoJobs y los portales web de las propias empresas | `tools/batch_search.py` + scrapers |
| 2. Filtrado | Filtros rápidos de título y ubicación (solo Huelva/remoto) y análisis con Gemini, que puntúa el encaje técnico (0-100). Las **empresas prioritarias** (Moeve, Endesa...) reciben +15 puntos y nunca se descartan sin análisis. Si la cuota de Gemini se agota, el reporte sale igualmente con lo analizado | `tools/filtro_ia.py` |
| 3. Documentos | Compila CV y carta en PDF con LaTeX, adaptando titular, perfil y experiencia a cada oferta | `tools/generador_docs.py` |
| 4. OSINT | Busca en Google (SerpApi) perfiles de Talent Acquisition / RRHH de la empresa | `tools/osint.py` |
| 5. Notificación | Envía el reporte diario por Gmail (llega **aunque no haya ofertas nuevas**), con los PDFs adjuntos y borradores de mensaje | `tools/notificador.py` |

El reporte muestra **primero las ofertas de LinkedIn e InfoJobs** y después las publicadas en portales y webs de empresas; dentro de cada sección, las empresas prioritarias van arriba con la insignia ⭐.

El pipeline **no envía candidaturas ni mensajes a nadie**: te entrega el material preparado y tú decides a qué aplicar.

## Estructura del repositorio

```
auto-candidaturas/
├── .github/workflows/pipeline_diario.yml   # ejecución diaria automática (15:00)
├── boton_ejecucion.html   # página con botón para lanzar el pipeline a mano
├── tools/
│   ├── batch_search.py        # ⚙️ EDITA: términos, ubicación y empresas prioritarias
│   ├── main_pipeline.py       # ⚙️ EDITA: tu perfil profesional (PERFIL_CANDIDATO)
│   ├── linkedin_scraper.py    # extracción LinkedIn (guest, sin API key)
│   ├── google_jobs_scraper.py # extracción Google Jobs (SerpApi) + filtro 24 h
│   ├── portales_scraper.py    # vigilancia de portales de empresa (Moeve, Enel...)
│   ├── filtro_ia.py           # análisis con Gemini (REST, sin SDK)
│   ├── generador_docs.py      # render de plantillas + pdflatex
│   ├── osint.py               # búsqueda de reclutadores (SerpApi)
│   ├── notificador.py         # reporte por email (SMTP Gmail)
│   └── utils.py               # utilidades comunes
├── plantillas/
│   ├── cv/plantilla_cv.tex        # ⚙️ EDITA si quieres otro diseño
│   ├── carta/plantilla_carta.tex
│   └── assets/foto.jpg            # foto que incrusta el CV
├── data/                      # memoria de ofertas ya vistas y caché OSINT
└── salida/                    # PDFs y reportes generados (no se versiona)
```

## Ejecución automática y manual

- **Automática**: el `cron` del workflow corre cada día sin que toques nada. Está en `"0 13 * * *"` (UTC), que son las **15:00 en España peninsular en verano** (14:00 en invierno; para mantener las 15:00 en invierno cámbialo a `"0 14 * * *"`). GitHub puede retrasar el arranque unos minutos.
- **Manual (opción 1)**: pestaña **Actions** → "Pipeline diario de candidaturas" → **Run workflow**.
- **Manual (opción 2, botón web)**: abre `boton_ejecucion.html` en tu navegador (doble clic). Necesita un token fine-grained de GitHub con permiso *Actions: Read and write* sobre este repo (las instrucciones están en la propia página). No compartas el archivo con el token guardado.
- GitHub desactiva los workflows programados tras 60 días sin actividad en el repo; el commit automático diario de `data/` lo mantiene siempre activo.

## Puesta en marcha (15 minutos)

### 1. Sube el proyecto a un repositorio privado

Con GitHub Desktop: *File → Add local repository → Create repository → Publish* (marca **Keep this code private**). O por terminal:

```bash
cd auto-candidaturas
git init && git add -A && git commit -m "feat: pipeline inicial"
gh repo create auto-candidaturas --private --source=. --push
```

### 2. Consigue las tres credenciales gratuitas

- **Gemini**: entra en [Google AI Studio](https://aistudio.google.com/apikey) y crea una API key. El tier gratuito basta de sobra.
- **SerpApi**: regístrate en [serpapi.com](https://serpapi.com/) y copia tu API key (100 búsquedas/mes gratis).
- **Gmail App Password**: activa la verificación en 2 pasos en tu cuenta de Google y crea una [contraseña de aplicación](https://myaccount.google.com/apppasswords) de 16 letras. **No uses tu contraseña normal.**

### 3. Configura los Secrets en GitHub

En el repositorio: `Settings → Secrets and variables → Actions → New repository secret`. Crea:

| Secret | Valor |
|---|---|
| `GEMINI_API_KEY` | tu clave de AI Studio |
| `SERPAPI_API_KEY` | tu clave de SerpApi |
| `EMAIL_REMITENTE` | tu dirección de Gmail |
| `EMAIL_APP_PASSWORD` | la contraseña de aplicación de 16 letras |
| `EMAIL_DESTINATARIO` | (opcional) otra dirección; si no, se envía al remitente |

### 4. Activa y prueba el workflow

En la pestaña **Actions** del repo, habilita los workflows y lanza "Pipeline diario de candidaturas" con **Run workflow**. A partir de ahí se ejecutará solo cada día.

## Personalización

1. **Búsquedas** — `tools/batch_search.py`: `TERMINOS_LINKEDIN` (puestos), `UBICACIONES_LINKEDIN` (solo Huelva por defecto), `EMPRESAS_PRIORITARIAS`, `TERMINOS_EMPRESAS` y `PORTALES_EMPRESA` (Moeve/Cepsa, Endesa/Enel y sus webs de empleo; añade más con empresa + dominio), `CONSULTAS_GOOGLE_JOBS` y `PALABRAS_EXCLUIR`.
2. **Tu perfil** — `tools/main_pipeline.py`: la constante `PERFIL_CANDIDATO` es el contexto que Gemini usa para decidir si una oferta encaja y para redactar el contenido personalizado. `BONUS_PRIORITARIA` ajusta el empujón de las empresas prioritarias.
3. **Plantillas** — `plantillas/cv/plantilla_cv.tex` y `plantillas/carta/plantilla_carta.tex`. Si cambias el diseño, **mantén intactos los marcadores** `[COMPANY_NAME]`, `[JOB_TITLE]`, `[HEADLINE]`, `[PROFILE_SUMMARY]`, `[INERCO_BULLETS]`, `[LETTER_BODY]` y `[FECHA]`.

Ajustes finos por variables de entorno (opcionales): `MAX_ANALISIS_DIARIO` (20), `UMBRAL_PUNTUACION` (60), `MAX_OSINT_DIARIO` (1), `LIMITE_MINUTOS` (18, presupuesto de tiempo: al agotarse se envía el email con lo que haya), `GEMINI_MODEL` (`gemini-2.5-flash`), `ENVIAR_REPORTE_VACIO` (activado en el workflow).

## Ejecución en local

```bash
pip install -r requirements.txt
sudo apt-get install texlive-latex-base texlive-latex-recommended \
     texlive-latex-extra texlive-fonts-recommended texlive-pictures lmodern

# Prueba sin gastar APIs ni enviar email (usa ofertas simuladas):
MODO_PRUEBA=1 python -m tools.main_pipeline
# → genera salida/reporte_prueba.html y los PDFs de ejemplo en salida/

# Ejecución real (configura antes las variables de .env.example):
python -m tools.main_pipeline
```

## Cuotas y límites (planes gratuitos)

| Servicio | Límite gratuito | Consumo con la config. por defecto |
|---|---|---|
| Gemini (`gemini-2.5-flash`) | ~10 pet./min y ~500/día | ≤ 20 análisis/día (pausa de 7 s entre llamadas) |
| SerpApi | 100 búsquedas/mes | 1 Google Jobs + 1 portales de empresas + ≤ 1 OSINT al día ≈ 90/mes |
| LinkedIn guest | sin cuota oficial; limita por IP | 15 búsquedas/día + descripciones, con pausas y reintentos |
| Gmail | 25 MB por email | adjuntos limitados a 18 MB (el resto queda como artefacto) |

La memoria de ofertas ya procesadas (`data/ofertas_vistas.json`) y la caché OSINT se guardan con un commit automático al final de cada ejecución, así el pipeline no repite trabajo ni gasta cuota dos veces. Ese mismo mecanismo, junto al filtro de 24 h en ambas fuentes, garantiza que el correo solo contenga ofertas nuevas.

## Uso responsable

- El scraping del listado público de LinkedIn va contra sus condiciones de uso, aunque sean datos públicos y el volumen aquí sea mínimo. Úsalo con moderación, bajo tu responsabilidad; si LinkedIn devuelve 429 de forma persistente, baja la frecuencia o apóyate solo en Google Jobs.
- Los perfiles de reclutadores que lista el reporte son resultados públicos de Google. Úsalos para contacto profesional individual y respetuoso (RGPD: interés legítimo de búsqueda de empleo), nunca para envíos masivos.
- Revisa siempre los PDF generados antes de enviarlos: la IA redacta bien, pero la responsabilidad del contenido es tuya.

## Licencia

MIT. Si te resulta útil, adáptalo y compártelo.
