"""
@file backend/app/agent_engine/runtime.py
@description Execution Runtime and Multi-Agent Orchestrator.

Manages the core orchestration loop (Phase 7.5): Worker -> Checker -> Retry.
Handles durable state checkpointing, error recovery, pausing for human approval (Phase 4), 
and securely spawning scoped subagents (Phase 7). Integrates deeply with the Guardrail layer (Phase 8).
"""

class SubagentWrapper:
    def __init__(self, compiled_graph, capabilities):
        self.compiled_graph = compiled_graph
        self.capabilities = capabilities
        
    async def generate(self, context: Dict[str, Any]) -> Dict[str, Any]:
        from app.core.security import Principal
        from langchain_core.messages import HumanMessage
        
        task = context.get("task", {}).get("description", str(context.get("task", "")))
        feedback = context.get("feedback")
        if feedback:
            task += "\n\nChecker Feedback from previous attempt: " + feedback
            
        initial_state = {
            "messages": [HumanMessage(content=task)],
            "task": task,
            "principal": Principal(id="subagent", role="subagent", workspace_id="default"),
            "session_id": "default",
            "capabilities": self.capabilities
        }
        
        final_state = await self.compiled_graph.ainvoke(initial_state)
        output = final_state["messages"][-1].content
        
        return {"output": output, "tool_proposals": []}


class AgentRuntime:
    """
    Phase 5: Agent Execution Kernel with Fully Durable Runs.
    """

    def __init__(self, db_session=None, tool_gateway=None):
        self.db = db_session
        self.tool_gateway = tool_gateway

    async def execute_task(
        self,
        task: Dict[str, Any],
        orchestrator: Any,
        worker: Any,
        checker: Any,
        max_attempts: int = 3,
        max_turns: int = 10,
        max_tool_calls: int = 5,
        timeout: Optional[float] = None,
        cancellation_token: Optional[Any] = None,
        run_id: Optional[str] = None,
        session_id: str = "default_session",
        workspace_id: str = "default_workspace"
    ) -> Any:
        
        run_id = run_id or str(uuid.uuid4())
        
        # 1. Load durable run state if resuming
        agent_run = AgentStateManager.load_agent_run(run_id)
        if agent_run:
            start_time = agent_run.created_at
            current_attempt = agent_run.task_attempts
            turn = agent_run.current_state.get("turn", 0)
            worker_context = agent_run.current_state.get("worker_context")
            last_feedback = agent_run.current_state.get("last_feedback")
            
            if agent_run.status == AgentRunStatus.WAITING_APPROVAL:
                agent_run.status = AgentRunStatus.RUNNING
        else:
            start_time = datetime.utcnow()
            current_attempt = 1
            turn = 0
            try:
                task["description"] = InputGuardrail.validate(task.get("description", str(task)))
            except Exception as e:
                agent_run.status = AgentRunStatus.FAILED
                agent_run.errors.append(str(e))
                AgentStateManager.save_agent_run(agent_run)
                raise
            
            dispatcher = EventDispatcher()
            dispatcher.dispatch("run.started", run_id=run_id, session_id=session_id, workspace_id=workspace_id)

            worker_context = {"task": task, "feedback": None, "observations": [], "resuming": False}
            last_feedback = None
            
            agent_run = AgentRun(
                run_id=run_id,
                session_id=session_id,
                workspace_id=workspace_id,
                status=AgentRunStatus.RUNNING,
                task_attempts=current_attempt,
                current_state={
                    "turn": turn,
                    "worker_context": worker_context,
                    "last_feedback": last_feedback
                },
                created_at=start_time
            )
            AgentStateManager.save_agent_run(agent_run)

        while current_attempt <= max_attempts:
            if cancellation_token and cancellation_token.is_cancelled:
                agent_run.status = AgentRunStatus.CANCELLED
                self._save(agent_run, current_attempt, turn, worker_context, last_feedback)
                return None
            
            if timeout and (datetime.utcnow() - start_time).total_seconds() > timeout:
                agent_run.status = AgentRunStatus.FAILED
                self._save(agent_run, current_attempt, turn, worker_context, last_feedback)
                raise TaskTimeoutError("Task execution exceeded timeout")

            agent_run.task_attempts = current_attempt
            worker_completed = False
            worker_result = None

            while turn < max_turns:
                turn += 1
                
                try:
                    if timeout:
                        time_left = timeout - (datetime.utcnow() - start_time).total_seconds()
                        step_result = await asyncio.wait_for(worker.generate(worker_context), timeout=time_left)
                    else:
                        step_result = await worker.generate(worker_context)
                except asyncio.TimeoutError:
                    agent_run.status = AgentRunStatus.FAILED
                    agent_run.errors.append("TaskTimeoutError")
                    self._save(agent_run, current_attempt, turn, worker_context, last_feedback)
                    raise TaskTimeoutError("Task execution exceeded timeout")
                except Exception as e:
                    agent_run.status = AgentRunStatus.FAILED
                    agent_run.errors.append(f"Worker failed: {str(e)}")
                    self._save(agent_run, current_attempt, turn, worker_context, last_feedback)
                    break
                    
                worker_context["resuming"] = False
                self._save(agent_run, current_attempt, turn, worker_context, last_feedback)

                if "tool_proposals" in step_result and step_result["tool_proposals"]:
                    proposals = step_result["tool_proposals"]
                    if len(proposals) > max_tool_calls:
                         agent_run.status = AgentRunStatus.FAILED
                         agent_run.errors.append("Exceeded max tool calls per turn")
                         break

                    for proposal in proposals:
                        try:
                            if self.tool_gateway:
                                dispatcher = EventDispatcher()
                                dispatcher.dispatch("tool.proposed", run_id=run_id, session_id=session_id, workspace_id=workspace_id, tool=proposal.tool_name)
                                tool_res = await self.tool_gateway.execute(proposal)
                                worker_context["observations"].append(Observation(tool_call_id=proposal.tool_call_id, content=tool_res.output))
                            else:
                                worker_context["observations"].append(Observation(tool_call_id=proposal.tool_call_id, content="No gateway initialized."))
                        except ApprovalRequiredError as e:
                            # DURABLE WAIT: process can safely die here
                            agent_run.status = AgentRunStatus.WAITING_APPROVAL
                            EventDispatcher().dispatch("tool.approval_required", run_id=run_id, session_id=session_id, workspace_id=workspace_id, tool=proposal.tool_name)
                            worker_context["observations"].append(Observation(tool_call_id=proposal.tool_call_id, content="Waiting for approval..."))
                            self._save(agent_run, current_attempt, turn, worker_context, last_feedback)
                            return {"status": "WAITING_APPROVAL", "run_id": run_id}
                        except Exception as e:
                            worker_context["observations"].append(Observation(tool_call_id=proposal.tool_call_id, content=f"Tool error: {str(e)}"))
                            
                        self._save(agent_run, current_attempt, turn, worker_context, last_feedback)
                else:
                    worker_result = step_result.get("output")
                    worker_completed = True
                    break

            if not worker_completed and agent_run.status not in [AgentRunStatus.FAILED, AgentRunStatus.WAITING_APPROVAL]:
                agent_run.status = AgentRunStatus.FAILED
                agent_run.errors.append("Max turns reached")
                self._save(agent_run, current_attempt, turn, worker_context, last_feedback)
                raise MaxTurnsReachedError(f"Task {run_id} failed: max turns reached")

            if agent_run.status in [AgentRunStatus.FAILED, AgentRunStatus.WAITING_APPROVAL]:
                break

            try:
                checker_decision = await checker.evaluate(task=task, result=worker_result)
            except Exception as e:
                agent_run.status = AgentRunStatus.FAILED
                agent_run.errors.append(f"Checker failed: {str(e)}")
                self._save(agent_run, current_attempt, turn, worker_context, last_feedback)
                break
                
            if checker_decision.status == CheckerDecisionEnum.ACCEPT:
                agent_run.status = AgentRunStatus.COMPLETED
                EventDispatcher().dispatch("checker.accepted", run_id=run_id, session_id=session_id, workspace_id=workspace_id)
                EventDispatcher().dispatch("run.completed", run_id=run_id, session_id=session_id, workspace_id=workspace_id)
                self._save(agent_run, current_attempt, turn, worker_context, last_feedback)
                return OutputGuardrail.validate(str(worker_result))
            else:
                last_feedback = checker_decision.retry_instruction or "Failed criteria."
                EventDispatcher().dispatch("checker.rejected", run_id=run_id, session_id=session_id, workspace_id=workspace_id)
                EventDispatcher().dispatch("retry.requested", run_id=run_id, session_id=session_id, workspace_id=workspace_id, attempt=current_attempt+1)
                current_attempt += 1
                turn = 0
                worker_context = {"task": task, "feedback": last_feedback, "observations": [], "resuming": False}
                self._save(agent_run, current_attempt, turn, worker_context, last_feedback)

        if agent_run.status not in [AgentRunStatus.COMPLETED, AgentRunStatus.CANCELLED, AgentRunStatus.WAITING_APPROVAL]:
            agent_run.status = AgentRunStatus.FAILED
            self._save(agent_run, current_attempt, turn, worker_context, last_feedback)
            raise MaxTurnsReachedError(f"Task {run_id} failed after {max_attempts} attempts.")
            
        return None

    def _save(self, agent_run, current_attempt, turn, worker_context, last_feedback):
        worker_context_serializable = {
            "task": worker_context.get("task"),
            "feedback": worker_context.get("feedback"),
            "resuming": worker_context.get("resuming"),
            "observations": [{"tool_call_id": o.tool_call_id, "content": o.content} if hasattr(o, 'tool_call_id') else o for o in worker_context.get("observations", [])]
        }
        agent_run.current_state = {
            "turn": turn,
            "worker_context": worker_context_serializable,
            "last_feedback": last_feedback
        }
        agent_run.task_attempts = current_attempt
        agent_run.updated_at = datetime.utcnow()
        AgentStateManager.save_agent_run(agent_run)

    async def spawn_agent(
        self,
        parent_run_id: Optional[str],
        child_run_id: str,
        task: Dict[str, Any],
        role: str,
        budget: float,
        permissions: List[str],
        deadline: Optional[datetime],
        result_schema: Dict[str, Any],
        provider: str = "default",
        model: str = "default",
        session_id: str = "default_session",
        workspace_id: str = "default_workspace"
    ) -> Any:
        """
        Phase 7: Multi-Agent Primitive.
        Phase 12: LangGraph successfully removed. Uses NativeWorker exclusively.
        """
        from app.agents.subagents.base import SubagentFactory, SubagentCapabilitySet
        from app.agent_engine.checker import AgentChecker
        from app.agent_engine.adapters.openai_adapter import OpenAIAdapter
        
        # [Phase 7] Ensure strict capabilities
        capability_set = SubagentCapabilitySet(
            allowed_tools=[],
            max_budget=budget,
            require_approval=True
        )
        
        # [Phase 11 & 12] Inject Adapter and create native worker
        worker_adapter = OpenAIAdapter(model_name=model)
        worker = SubagentFactory.create_subagent(
            role_name=role, 
            system_prompt=f"You are a specialized subagent for {role}", 
            tools=[],
            adapter=worker_adapter,
            capabilities=capability_set
        )
        
        # [Phase 11] Independent Checker Adapter
        checker_adapter = OpenAIAdapter(model_name=model)
        checker = AgentChecker(model_provider=checker_adapter)
        
        timeout = max(0.0, (deadline - datetime.utcnow()).total_seconds()) if deadline else None
            
        # [Phase 7.5] Delegate to standard Orchestration Loop
        return await self.execute_task(
            task=task,
            orchestrator=None,
            worker=worker,
            checker=checker,
            timeout=timeout,
            run_id=child_run_id,
            session_id=session_id,
            workspace_id=workspace_id
        )