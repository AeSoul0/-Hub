import asyncio
from typing import Dict, Any
from langchain_core.messages import HumanMessage
from app.workers.scheduler import proactive_scheduler
from app.runtime.aurora import get_aurora_app
from app.core.event_bus import event_bus

class WorkflowEngine:
    """
    Phase 13: Autonomous Workflows.
    Allows A.U.R.O.R.A. to run long-term independent goals.
    """
    
    @staticmethod
    async def morning_briefing_routine():
        """
        An autonomous task that runs without user input.
        It generates a briefing and pushes it to the UI via SSE.
        """
        print("[Workflow] Starting Autonomous Morning Briefing...")
        
        app_instance = await get_aurora_app()
        # Session ID dedicated to background tasks
        session_id = "background_workflow_daemon"
        
        initial_state = {
            "messages": [HumanMessage(content="Fai una rapida ricerca sulle notizie tech più importanti di oggi e genera un report riassuntivo con i 3 punti chiave. Non aspettare input dell'utente.")],
            "session_id": session_id,
            "current_intent": "workflow_briefing"
        }
        
        try:
            # Let AURORA run the workflow autonomously
            final_state = await app_instance.ainvoke(
                initial_state,
                config={"configurable": {"thread_id": session_id}}
            )
            
            result = final_state["messages"][-1].content
            
            # Push proactively to the UI using the event bus
            await event_bus.publish("global_alerts", "notification", {
                "title": "Morning Briefing Ready",
                "content": result
            })
            print("[Workflow] Morning Briefing completed and pushed to UI.")
            
        except Exception as e:
            print(f"[Workflow] Error during autonomous task: {e}")

def register_workflows():
    """Registers all autonomous jobs into the Proactive Scheduler."""
    # Runs every 24 hours (86400 seconds) - for demo purposes, set to 60 seconds or triggered via API.
    # proactive_scheduler.schedule_interval(86400, WorkflowEngine.morning_briefing_routine)
    pass
