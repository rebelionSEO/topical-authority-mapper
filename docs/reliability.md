# Primera entrega: fiabilidad del análisis

## Cambios

- Caché de embeddings con huella del texto ordenado y modelo; escritura atómica en NPZ.
  Los pickles antiguos se ignoran. Se invalida la ejecución completa: todavía no hay
  caché incremental por chunk ni fijación de revisión de modelos de Hugging Face.
- Retrieval lee el nuevo formato y comprueba el número de filas.
- Perfiles de marca usan el directorio de caché activo. Un PDF explícito se reprocesa.
  El parser ya no comparte listas mutables entre perfiles.
- Sitios pequeños ajustan UMAP; menos de tres chunks se consideran sin clasificar.
- El pipeline ejecuta similitud, sugerencias entre clusters y voz de marca.
- Los resultados vacíos esenciales conservan encabezados y reemplazan datos anteriores.
- Ruido (-1) y URLs duplicadas no cuentan como solapamiento.
- El CSV y el dashboard no eligen automáticamente una URL ganadora a partir de tipos
  de página. Los consejos del LLM siguen siendo opiniones que requieren revisión.
- El solapamiento sin confirmar no penaliza el score de salud.
- QA crítico interrumpe el pipeline antes de renderizar los informes.
- CI y pruebas de regresión sin APIs pagas; prueba integral con ingestión y encoder
  controlados, generación real de CSV, dashboard y retrieval.

## Límites de esta entrega

El nombre legado `cannibalization.csv` y algunos rótulos de informes se conservan por
compatibilidad. No representan competencia confirmada en buscadores. El PDF y otras
vistas todavía necesitan una revisión editorial completa de sus heurísticas.

La prueba integral sustituye las solicitudes de red, el encoder, el renderizador PDF
y el mapa vectorial. No valida crawling real, calidad del modelo ni la apariencia del PDF.
La segunda entrega añade aislamiento automático por dominio y ejecución y un
manifiesto con estado por etapa. No se fijaron versiones de dependencias:
el lockfile debe validarse contra las plataformas y la versión de Python objetivo.

## Próximas entregas

1. Embeddings por página, soporte multilingüe y evaluación con ejemplos etiquetados.
2. Importación GSC y comparación por consultas para diagnosticar canibalización.
3. Oportunidades competitivas sustentadas en datos y priorización de acciones.

La fórmula de canibalización propuesta en el análisis inicial era ilustrativa;
sus pesos no están calibrados y no se implementan como probabilidades.

## Segunda entrega: ejecuciones y crawler

- Carpetas únicas por ejecución; no se sobrescriben auditorías ni snapshots anteriores.
- Manifiesto JSON y página de estado con configuración, fechas, cobertura, errores
  e inventario de archivos. Los informes distinguen ejecuciones completas y parciales.
- Cachés reutilizables separados por dominio; los índices y chunks pertenecen a cada
  ejecución. El puntero del directorio raíz permite localizar la auditoría actual.
- Sitemaps recursivos y gzip con límites, eliminación de ciclos y lastmod compartido
  con frescura. Las fechas inválidas/futuras se consideran desconocidas.
- Reintentos HTTP, límites de respuesta/redirects, robots.txt, normalización conservadora,
  evidencia de canonical/noindex y un registro por URL. Las páginas noindex se excluyen
  del mapa; canonicalizados se conservan como candidatos con su señal explícita.
- Etiquetas TF-IDF sin tokens numéricos puros: una prueba real descubrió un cluster
  denominado `13 21 34`, que ahora se evita sin desactivar el control de calidad.

El aislamiento soporta ejecuciones en procesos separados. La configuración global del
proyecto todavía impide ejecutar auditorías simultáneas en hilos de un mismo proceso.
Los fallos fatales salen con código no cero; fallos de análisis opcionales se registran
como ejecución parcial. La ejecución secuencial evita ráfagas concurrentes, pero aún
no implementa un planificador completo de crawl-delay ni navegación con JavaScript.
