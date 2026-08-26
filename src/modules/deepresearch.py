import asyncio
from typing import Dict, Any
from urllib.parse import urlparse
from google.genai import types

from src.config import settings, log
from src.modules import rag_client, perplexity_client, gemini_client
from src.core.prompts import PIDA_SYSTEM_PROMPT

async def ejecutar_investigacion_profunda(
    job_id: str, 
    prompt: str, 
    user_email: str, 
    country_code: str, 
    jobs_db: Dict[str, Any]
):
    try:
        jobs_db[job_id]["status"] = "PROCESANDO"
        jobs_db[job_id]["status_message"] = "Iniciando análisis y recopilación de información..."
        jobs_db[job_id]["steps"] = ["Iniciando investigación profunda..."]
        log.info(f"Iniciando Deep Research job {job_id} para {user_email} en {country_code}")

        # Ejecutar búsquedas en paralelo
        jobs_db[job_id]["status_message"] = "Buscando en la base de datos interna de jurisprudencia (RAG) y en la web..."
        jobs_db[job_id]["steps"].append("Consultando base de datos interna y fuentes web en paralelo...")

        rag_task = rag_client.search_internal_documents(prompt)
        perp_task = perplexity_client.get_perplexity_research(prompt)
        
        rag_res, perp_res = await asyncio.gather(rag_task, perp_task)
        
        rag_context = rag_res["text"]
        web_context = perp_res["text"]
        
        documentos_consultados = rag_res["documents"]
        citaciones_encontradas = perp_res["citations"]
        
        # Extraer nombres de dominio de las citaciones de Perplexity
        sitios_web = list(set(urlparse(url).netloc for url in citaciones_encontradas if url))
        
        # Guardar metadatos en el job para su consumo directo por API / polling
        jobs_db[job_id]["documents_consulted"] = documentos_consultados
        jobs_db[job_id]["websites_consulted"] = sitios_web
        
        # Agregar al historial de pasos detallados
        if documentos_consultados:
            jobs_db[job_id]["steps"].append(f"Documentos consultados en RAG: {', '.join(documentos_consultados)}")
        else:
            jobs_db[job_id]["steps"].append("No se encontraron documentos internos aplicables.")
            
        if sitios_web:
            jobs_db[job_id]["steps"].append(f"Fuentes web encontradas: {', '.join(sitios_web)}")
        else:
            jobs_db[job_id]["steps"].append("No se encontraron fuentes web adicionales.")

        jobs_db[job_id]["status_message"] = "Procesando, correlacionando y redactando el informe con Gemini 2.5 Pro..."
        jobs_db[job_id]["steps"].append("Enviando el contexto completo al modelo de IA para la síntesis jurídica...")

        # Construir prompt final
        final_prompt = f"""Contexto geográfico principal: {country_code or 'General'}

Toma en cuenta las fuentes proporcionadas.

[CONTEXTO INTERNO DE JURISPRUDENCIA (RAG)]
{rag_context}

[INVESTIGACIÓN WEB RECIENTE (Perplexity)]
{web_context}

Pregunta del usuario: {prompt}
"""

        generation_config = types.GenerateContentConfig(
            max_output_tokens=65536,
            system_instruction=PIDA_SYSTEM_PROMPT,
            thinking_config=types.ThinkingConfig(
                thinking_level="high"
            )
        )

        response = await gemini_client.client.aio.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=final_prompt,
            config=generation_config
        )

        jobs_db[job_id]["result"] = response.text
        jobs_db[job_id]["status"] = "COMPLETADO"
        jobs_db[job_id]["status_message"] = "Investigación completada con éxito."
        jobs_db[job_id]["steps"].append("Informe redactado e investigación completada.")
        log.info(f"Deep Research job {job_id} completado con éxito.")

    except Exception as e:
        log.error(f"Error en Deep Research job {job_id}: {e}", exc_info=True)
        jobs_db[job_id]["status"] = "ERROR"
        jobs_db[job_id]["status_message"] = f"Error durante la investigación: {str(e)}"
        jobs_db[job_id]["result"] = str(e)
