from app.core.celery_app import celery_app
from app.core import database
from litellm import acompletion
import asyncio
import os

@celery_app.task(name="memory.summarize_and_forget")
def summarize_old_chats(session_id: str):
    """
    Implements the Forgetting and Auto-Summarization mechanism (Phase 4).
    Checks if chat history is too long. If so, summarizes the oldest messages,
    saves the semantic summary to RAG/memory table, and deletes the raw messages.
    """
    asyncio.run(_async_summarize(session_id))

async def _async_summarize(session_id: str):
    # Fetch all chats
    with database.get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, user_text, ai_text FROM chats WHERE session_id = %s ORDER BY timestamp ASC", (session_id,))
            rows = cursor.fetchall()
            
    if len(rows) <= 10:
        return # Not enough history to summarize
        
    # Summarize the oldest 5 messages
    old_messages = rows[:5]
    old_ids = [row[0] for row in old_messages]
    
    transcript = ""
    for r in old_messages:
        transcript += f"User: {r[1]}\nAI: {r[2]}\n\n"
        
    # Summarize via LLM
    try:
        response = await acompletion(
            model="groq/llama3-70b-8192",
            api_key=os.getenv("GROQ_API_KEY"),
            messages=[
                {"role": "system", "content": "Summarize the following chat history into a concise semantic memory. Focus on user facts, preferences, and long-term context."},
                {"role": "user", "content": transcript}
            ]
        )
        summary = response.choices[0].message.content
        
        # Save to semantic memory
        with database.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO memory_semantic (session_id, fact) VALUES (%s, %s)",
                    (session_id, summary)
                )
                
                # Forget (delete) the summarized raw messages
                cursor.execute(
                    "DELETE FROM chats WHERE id = ANY(%s)",
                    (old_ids,)
                )
            conn.commit()
    except Exception as e:
        print(f"Error summarizing: {e}")
