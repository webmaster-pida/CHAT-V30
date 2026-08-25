import asyncio
from typing import Dict, Any
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
        log.info(f"Iniciando Deep Research job {job_id} para {user_email} en {country_code}")

        # Ejecutar búsquedas en paralelo
        rag_task = rag_client.search_internal_documents(prompt)
        perp_task = perplexity_client.get_perplexity_research(prompt)
        
        rag_context, web_context = await asyncio.gather(rag_task, perp_task)

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
            max_output_tokens=32000,
            system_instruction=PIDA_SYSTEM_PROMPT
        )

        response = await gemini_client.client.aio.models.generate_content(
            model="gemini-2.5-pro",
            contents=final_prompt,
            config=generation_config
        )

        jobs_db[job_id]["result"] = response.text
        jobs_db[job_id]["status"] = "COMPLETADO"
        log.info(f"Deep Research job {job_id} completado con éxito.")

    except Exception as e:
        log.error(f"Error en Deep Research job {job_id}: {e}", exc_info=True)
        jobs_db[job_id]["status"] = "ERROR"
        jobs_db[job_id]["result"] = str(e)
