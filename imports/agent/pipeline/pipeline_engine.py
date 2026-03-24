import datetime
import json
import traceback
from typing import Callable, Optional
from imports.providers_manager import ProvidersManager, Model
from imports.history_manager import HistoryRecord
from imports.agent.pipeline.role_base import AIRole

# Import Roles
from imports.agent.roles.router_role import RouterRole
from imports.agent.roles.deconstructor_role import TaskDeconstructorRole
from imports.agent.roles.worker_role import WorkerRole
from imports.agent.roles.verifier_role import VerifierRole
from imports.agent.roles.aggregator_role import AggregatorRole
from imports.agent.roles.formatter_role import PersonalityFormatterRole
from imports.agent.roles.memory_retrieval_role import MemoryRetrievalRole
from imports.agent.roles.memory_creation_role import MemoryCreationRole
from imports.agent.roles.summary_role import SummaryRole
from imports.agent.roles.history_compressor_role import HistoryCompressorRole
from imports.agent.roles.skill_builder_role import SkillBuilderRole

class PipelineEngine:
    def __init__(self, providers_manager: ProvidersManager, model: Model, config: dict, image_manager=None, mcp_connector=None):
        self.providers_manager = providers_manager
        self.model = model
        self.config = config
        self.image_manager = image_manager
        self.mcp_connector = mcp_connector

        # Pipeline suspension state for ask_user
        self._suspended_state: dict | None = None

        # Initialize Roles
        self.router = RouterRole(self)
        self.deconstructor = TaskDeconstructorRole(self)
        self.worker = WorkerRole(self)
        self.verifier = VerifierRole(self)
        self.aggregator = AggregatorRole(self)
        self.formatter = PersonalityFormatterRole(self)
        self.memory_retrieval = MemoryRetrievalRole(self)
        self.memory_creation = MemoryCreationRole(self)
        self.summary = SummaryRole(self)
        self.history_compressor = HistoryCompressorRole(self)
        self.skill_builder = SkillBuilderRole(self)

    def _clean_payload(self, data, skip=False):
        """Recursively removes empty strings, lists, and dicts, except in specific nested keys."""
        if skip:
            return data
        if isinstance(data, dict):
            cleaned = {}
            for k, v in data.items():
                if k in ["tools", "abilities", "arguments", "result", "next_task", "current_task"]:
                    # Preserve structure for specific keys that may legitimately be empty
                    val = self._clean_payload(v, skip=True)
                else:
                    val = self._clean_payload(v)
                
                # Filter out exactly empty structures (but keep boolean False or 0)
                if val in ["", [], {}]:
                    continue
                cleaned[k] = val
            return cleaned
        elif isinstance(data, list):
            cleaned_list = []
            for item in data:
                val = self._clean_payload(item)
                if val not in ["", [], {}]:
                    cleaned_list.append(val)
            return cleaned_list
        else:
            return data

    def log_step(self, role_name: str, payload: dict, output: dict):
        """Log inputs and outputs of each role for debugging reasoning."""
        
        class HistoryEncoder(json.JSONEncoder):
            def default(self, o):
                if isinstance(o, HistoryRecord):
                    return o.to_dict()
                return super().default(o)
                
        log_entry = {
            "role": role_name,
            "input_payload": payload,
            "output": output
        }
        with open("logs/role_payload.json", "a") as f:
            json.dump(log_entry, f, ensure_ascii=False, cls=HistoryEncoder)
            f.write("\n")

    def execute_tool(self, tool_name: str, arguments: dict) -> str:
        """Executes a tool and returns the result as string."""
        if not self.mcp_connector:
            return "Error: MCP Connector not initialized."
            
        try:
            result = self.mcp_connector.execute_tool(tool_name, arguments)
            if isinstance(result, (dict, list)):
                return json.dumps(result, ensure_ascii=False)
            return str(result)
        except Exception as e:
            return f"Error executing tool {tool_name}: {str(e)}"

    @property
    def is_waiting_for_user(self) -> bool:
        """Check if pipeline is suspended waiting for user input."""
        return self._suspended_state is not None

    def run_pipeline(self, initial_payload: dict, history_manager, execution_trace_manager=None, send_status: Optional[Callable[[str], None]] = None) -> dict:
        """
        Executes the main role-based execution pipeline with strict role isolation.
        
        Each role receives ONLY the data it needs — no shared mutable payload.
        
        Returns:
            dict: {"text": str, "images": list[str]}
                  or {"type": "ask_user", "text": str, "images": list[str]} if suspended
        """
        # ── Check for pipeline resumption (ask_user continuation) ────
        if self._suspended_state is not None:
            return self._resume_pipeline(initial_payload, history_manager, execution_trace_manager, send_status)

        # Extract core inputs
        user_input = initial_payload.get("input_message", {}).get("text", "")
        input_images = initial_payload.get("input_message", {}).get("image_hashes", [])
        
        # ── 1. Retriever (MemoryRetrieval) ──────────────────────────────
        # Receives: only input
        if send_status:
            send_status("Retrieving memories...")
        
        retriever_payload = self._clean_payload({"input": user_input})
        mem_out = self.memory_retrieval.run(retriever_payload)
        self.log_step("MemoryRetrieval", retriever_payload, mem_out)
        memories = mem_out.get("result", {}).get("memories", [])
        
        # Log memory payload size
        memories_text = json.dumps(memories, ensure_ascii=False)
        print(f"[DEBUG] memory_payload_size: {len(memories_text)} characters")
        
        # ====== ARCHIVED CONTEXT ======
        archived_context = ""
        if self.mcp_connector:
            try:
                res = self.mcp_connector.execute_tool("search_archived_messages", {"query": user_input, "limit": 2})
                if isinstance(res, dict) and "results" in res:
                    archived_pairs = res["results"]
                    if archived_pairs:
                        archived_context = "Recent relevant past interactions:\n"
                        for i, pair in enumerate(archived_pairs, 1):
                            archived_context += f"{i}. user: {pair.get('user', '')}\n   model: {pair.get('model', '')}\n\n"
            except Exception as e:
                print(f"[DEBUG] Error fetching archived context: {e}")

        user_input_with_context = user_input
        if archived_context:
            user_input_with_context += f"\n\n{archived_context}"

        # Gather shared resources
        history_records = history_manager.get_dialog_records() #count=5)
        identity = self.mcp_connector.get_identity_prompt() if self.mcp_connector else ""
        language = self.mcp_connector.get_language() if hasattr(self.mcp_connector, "get_language") else "English"
        
        now = datetime.datetime.now()
        system_time = now.strftime("%H:%M %a %d %B %Y")
        execution_trace = execution_trace_manager.get_markdown_trace() if execution_trace_manager else ""
        
        # ── 2. Router ───────────────────────────────────────────────────
        # Receives: input, history, identity, memory, input_images
        if send_status:
            send_status("Routing request...")
        
        router_payload = self._clean_payload({
            "input": user_input_with_context,
            "history": history_records,
            "identity": identity,
            "memory": memories,
            "input_images": input_images,
            "system_time": system_time,
            "execution_trace": execution_trace,
        })
        router_out = self.router.run(router_payload)
        self.log_step("Router", router_payload, router_out)
        
        req_type = router_out.get("result", {}).get("type", "task")
        task_summary = router_out.get("result", {}).get("task_summary", user_input)
        raw_answer = router_out.get("result", {}).get("answer", "")
        
        # ── CONVERSATION PATH ───────────────────────────────────────────
        if req_type == "conversation":
            if send_status:
                send_status("Generating response...")
            
            # Formatter in conversation mode: input, history, memory, identity, input_images
            formatter_payload = self._clean_payload({
                "input": user_input_with_context,
                "raw_answer": raw_answer,
                "task_summary": task_summary,
                "history": history_records,
                "memory": memories,
                "identity": identity,
                "language": language,
                "input_images": input_images,
                "media": [],
                "system_time": system_time,
                "execution_trace": execution_trace,
            })
            formatter_out = self.formatter.run(formatter_payload)
            self.log_step("Formatter", formatter_payload, formatter_out)
            
            final_text = formatter_out.get("result", {}).get("final_user_message", "Processing error.")
            return {"text": final_text, "images": []}
        
        # ── TASK PATH ───────────────────────────────────────────────────
        
        MAX_ITERATIONS = 90
        abilities = self.mcp_connector.get_all_abilities() if self.mcp_connector else []
        tools = self.mcp_connector.get_available_tools() if self.mcp_connector else []
        tasks_history = []
        collected_images = []
        step_counter = 0
        
        # ── Skill Retrieval ─────────────────────────────────────────────
        relevant_skills = []
        if self.mcp_connector:
            try:
                skill_res = self.mcp_connector.execute_tool("search_skills", {"query": task_summary, "limit": 3})
                if isinstance(skill_res, dict) and "results" in skill_res:
                    relevant_skills = skill_res["results"]
                    if relevant_skills:
                        print(f"[DEBUG] Found {len(relevant_skills)} relevant skill(s) for task")
            except Exception as e:
                print(f"[DEBUG] Error searching skills: {e}")

        # Execute the task loop
        return self._execute_task_loop(
            task_summary=task_summary,
            abilities=abilities,
            tools=tools,
            tasks_history=tasks_history,
            collected_images=collected_images,
            step_counter=step_counter,
            identity=identity,
            language=language,
            memories=memories,
            user_input_with_context=user_input_with_context,
            input_images=input_images,
            history_records=history_records,
            relevant_skills=relevant_skills,
            history_manager=history_manager,
            execution_trace_manager=execution_trace_manager,
            send_status=send_status,
            max_iterations=MAX_ITERATIONS,
        )

    def _resume_pipeline(self, initial_payload: dict, history_manager, execution_trace_manager=None, send_status: Optional[Callable[[str], None]] = None) -> dict:
        """Resume pipeline after ask_user suspension."""
        state = self._suspended_state
        self._suspended_state = None  # Clear suspended state

        user_response = initial_payload.get("input_message", {}).get("text", "")
        
        # Inject the user's response into the current task context
        current_task = state["current_task"]
        current_task["user_response"] = user_response
        
        # Append the ask_user step and the user's response to tasks_history
        state["tasks_history"].append({
            "id": state["step_counter"],
            "description": current_task.get("description", ""),
            "resolution": "success",
            "result": {"action": "ask_user", "result": f"Asked user, received: {user_response}"},
            "feedback": "",
            "media": [],
        })
        
        if send_status:
            send_status("Continuing task with your response...")

        return self._execute_task_loop(
            task_summary=state["task_summary"],
            abilities=state["abilities"],
            tools=state["tools"],
            tasks_history=state["tasks_history"],
            collected_images=state["collected_images"],
            step_counter=state["step_counter"],
            identity=state["identity"],
            language=state["language"],
            memories=state["memories"],
            user_input_with_context=state["user_input_with_context"],
            input_images=state["input_images"],
            history_records=history_manager.get_dialog_records(),
            relevant_skills=state.get("relevant_skills", []),
            history_manager=history_manager,
            execution_trace_manager=execution_trace_manager,
            send_status=send_status,
            max_iterations=90,
        )

    def _execute_task_loop(
        self,
        task_summary: str,
        abilities,
        tools: list,
        tasks_history: list,
        collected_images: list,
        step_counter: int,
        identity: str,
        language: str,
        memories: list,
        user_input_with_context: str,
        input_images: list,
        history_records: list,
        relevant_skills: list,
        history_manager,
        execution_trace_manager=None,
        send_status: Optional[Callable[[str], None]] = None,
        max_iterations: int = 90,
    ) -> dict:
        """Core task execution loop, extracted for reuse by run_pipeline and _resume_pipeline."""
        
        now = datetime.datetime.now()
        system_time = now.strftime("%H:%M %a %d %B %Y")
        execution_trace = execution_trace_manager.get_markdown_trace() if execution_trace_manager else ""
        
        if execution_trace_manager:
            execution_trace_manager.start_task(task_summary)
        
        # ── Iterative execution loop ────────────────────────────────────
        for iteration in range(max_iterations):
            
            # Check for mid-loop summary
            if len(history_manager.get_dialog_records()) >= 20:
                if send_status:
                    send_status("Summarizing long conversation...")
                summary_payload = self._clean_payload({"history": history_manager.get_dialog_records()})
                sum_out = self.summary.run(summary_payload, history_manager=history_manager)
                self.log_step("Summary", summary_payload, sum_out)
            
            # ── 3. Deconstructor (next step) ────────────────────────────
            if send_status:
                send_status("Planning next step...")
            
            deconstructor_payload = self._clean_payload({
                "task_summary": task_summary,
                "abilities": abilities,
                "tasks_history": tasks_history,
                "media": collected_images,
                "relevant_skills": relevant_skills,
            })
            deconstructor_out = self.deconstructor.run(deconstructor_payload)
            self.log_step("Deconstructor", deconstructor_payload, deconstructor_out)
            
            decision = deconstructor_out.get("result", {}).get("decision", "next_task")
            
            # Check for completion or interruption
            if decision == "task_completed":
                if send_status:
                    send_status("Task completed.")
                break
            
            if decision == "task_interrupted":
                reason = deconstructor_out.get("result", {}).get("reason", "Unknown reason")
                tasks_history.append({
                    "id": step_counter + 1,
                    "description": "Task interrupted by planner",
                    "resolution": "interrupt",
                    "result": reason,
                    "media": [],
                })
                if send_status:
                    send_status(f"Task interrupted: {reason}")
                break
            
            # Get the next task
            current_task = deconstructor_out.get("result", {}).get("next_task", {})
            step_counter += 1
            current_task["id"] = step_counter
            
            # ── 4. Worker + Retry loop ──────────────────────────────────
            retry_count = 0
            max_retries = 1
            verification_feedback = ""
            step_resolution = "failure"  # default until verified
            step_result_data = {}
            step_images = []
            
            while retry_count < max_retries:
                if send_status:
                    send_status(f"Executing step {step_counter}: {current_task.get('description', 'Unknown')}")
                
                worker_payload = self._clean_payload({
                    "current_task": current_task,
                    "tasks_history": tasks_history,
                    "tools": tools,
                    "abilities": abilities,
                    "verification_feedback": verification_feedback,
                })
                worker_out = self.worker.run(worker_payload)
                self.log_step("Worker", worker_payload, worker_out)
                
                worker_ans = worker_out.get("result", {})
                action = worker_ans.get("action")
                status = worker_ans.get("status", "success")
                
                step_images = worker_ans.get("media", [])
                if not isinstance(step_images, list):
                    step_images = []
                
                if action == "tool":
                    tool_name = worker_ans.get("tool_name")
                    arguments = worker_ans.get("arguments", {})
                    if send_status:
                        send_status(f"Executing tool {tool_name}...")
                    
                    tool_result = self.execute_tool(tool_name, arguments)
                    
                    step_result_data = {
                        "tool": tool_name,
                        "arguments": arguments,
                        "result": tool_result,
                    }
                    
                    # Detect generated images from tool result
                    try:
                        parsed_result = tool_result if isinstance(tool_result, dict) else json.loads(tool_result) if isinstance(tool_result, str) and tool_result.strip().startswith("{") else {}
                        if parsed_result.get("image_hash"):
                            step_images.append(parsed_result["image_hash"])
                    except (json.JSONDecodeError, TypeError):
                        pass
                    
                elif action == "ask_user":
                    # ── SUSPEND PIPELINE: ask_user ──────────────────────
                    raw_question = worker_ans.get("message", "I need more information to proceed.")
                    
                    # Style the question through Formatter
                    formatter_payload = self._clean_payload({
                        "input": user_input_with_context,
                        "raw_answer": raw_question,
                        "task_summary": task_summary,
                        "history": history_records,
                        "memory": memories,
                        "identity": identity,
                        "language": language,
                        "input_images": input_images,
                        "media": [],
                        "system_time": system_time,
                        "execution_trace": execution_trace,
                    })
                    formatter_out = self.formatter.run(formatter_payload)
                    self.log_step("Formatter_AskUser", formatter_payload, formatter_out)
                    styled_question = formatter_out.get("result", {}).get("final_user_message", raw_question)
                    
                    # Save pipeline state for resumption
                    self._suspended_state = {
                        "task_summary": task_summary,
                        "tasks_history": tasks_history,
                        "collected_images": collected_images,
                        "step_counter": step_counter,
                        "current_task": current_task,
                        "abilities": abilities,
                        "tools": tools,
                        "identity": identity,
                        "language": language,
                        "memories": memories,
                        "user_input_with_context": user_input_with_context,
                        "input_images": input_images,
                        "relevant_skills": relevant_skills,
                    }
                    
                    return {"type": "ask_user", "text": styled_question, "images": []}
                    
                elif action == "text":
                    step_result_data = {
                        "action": "text",
                        "result": worker_ans.get("message", ""),
                    }
                    
                elif action == "interrupt":
                    step_result_data = {
                        "action": "interrupt",
                        "result": worker_ans.get("answer", "task_unexecutable"),
                    }
                    
                elif action == "delete_history_entry":
                    entry_ids = worker_ans.get("entry_ids", [])
                    tasks_history = [t for t in tasks_history if t["id"] not in entry_ids]
                    step_result_data = {
                        "action": "delete_history_entry",
                        "result": f"Deleted entries {entry_ids}"
                    }
                
                # ── 5. Verifier ─────────────────────────────────────────
                if send_status:
                    send_status("Verifying step result...")
                
                verifier_payload = self._clean_payload({
                    "task": current_task,
                    "worker_output": worker_ans,
                    "answer": step_result_data,
                    "images": step_images,
                    "identity": identity,
                })
                verifier_out = self.verifier.run(verifier_payload)
                self.log_step("Verifier", verifier_payload, verifier_out)
                
                resolution = verifier_out.get("result", {}).get("resolution", "failure")
                
                if resolution == "success":
                    step_resolution = "success"
                    verification_feedback = verifier_out.get("notes", "")
                    break
                elif resolution == "interrupt":
                    step_resolution = "interrupt"
                    verification_feedback = verifier_out.get("notes", "")
                    break
                elif resolution == "violation":
                    step_resolution = "violation"
                    step_result_data["result"] = "[REMOVED: identity violation]"
                    verification_feedback = verifier_out.get("notes", "Identity violation.")
                    break
                else:
                    # failure — retry
                    retry_count += 1
                    verification_feedback = verifier_out.get("notes", "Verification failed.")
                    if send_status:
                        send_status(f"Step failed verification (attempt {retry_count}/{max_retries}). Retrying...")
            
            if step_resolution == "failure":
                result_str = str(step_result_data.get("result", ""))
                if len(result_str) > 1000:
                    step_result_data["result"] = result_str[:1000] + "\n... [TRUNCATED to preserve context space]"

            # ── Append to tasks_history ─────────────────────────────────
            history_entry = {
                "id": step_counter,
                "description": current_task.get("description", ""),
                "resolution": step_resolution,
                "result": step_result_data,
                "feedback": verification_feedback,
                # Only keep images from successful steps
                "media": step_images if step_resolution == "success" else [],
            }
            tasks_history.append(history_entry)
            
            # Collect images only from successful steps
            if step_resolution == "success" and step_images:
                collected_images.extend(step_images)
                
            # Add step to execution trace manager
            if execution_trace_manager:
                trace_args = worker_ans.get("arguments", {}) if action == "tool" else {"message": worker_ans.get("message", worker_ans.get("answer", ""))}
                tool_name = worker_ans.get("tool_name") if action == "tool" else None
                execution_trace_manager.add_step(action=action, args=trace_args, status=step_resolution, tool_name=tool_name)
        
        else:
            # Loop exhausted MAX_ITERATIONS
            tasks_history.append({
                "id": step_counter + 1,
                "description": "Step limit reached",
                "resolution": "interrupt",
                "result": f"Pipeline interrupted: maximum iteration limit ({max_iterations}) reached.",
                "media": [],
            })
            if send_status:
                send_status(f"Step limit ({max_iterations}) reached. Aggregating results...")
        
        # ── SkillBuilder (before Aggregator) ────────────────────────────
        try:
            if send_status:
                send_status("Extracting skills...")
            skill_payload = self._clean_payload({
                "task_summary": task_summary,
                "tasks_history": tasks_history,
                "input_images": input_images,
                "media": collected_images,
            })
            skill_out = self.skill_builder.run(skill_payload)
            self.log_step("SkillBuilder", skill_payload, skill_out)
            
            if skill_out.get("result", {}).get("save_skill", False):
                skill_data = skill_out.get("result", {}).get("skill", {})
                if skill_data and self.mcp_connector:
                    self.mcp_connector.execute_tool("save_skill", {"skill_data": skill_data})
                    print(f"[DEBUG] Skill saved: {skill_data.get('task_signature', 'unknown')}")
        except Exception as e:
            print(f"[DEBUG] SkillBuilder error: {e}")
                    
        # ── 6. Aggregator ───────────────────────────────────────────────
        if send_status:
            send_status("Aggregating results...")
        
        aggregator_payload = self._clean_payload({
            "task_summary": task_summary,
            "tasks_history": tasks_history,
            "input_images": input_images,
            "media": collected_images,
        })
        aggregator_out = self.aggregator.run(aggregator_payload)
        self.log_step("Aggregator", aggregator_payload, aggregator_out)
        
        raw_answer = aggregator_out.get("result", {}).get("answer", "Task completed.")
        aggregator_media = aggregator_out.get("result", {}).get("images", [])
        all_images = list(dict.fromkeys(collected_images + aggregator_media))
        
        # ── 7. Formatter ────────────────────────────────────────────────
        if send_status:
            send_status("Formatting response...")
        
        formatter_payload = self._clean_payload({
            "input": user_input_with_context,
            "raw_answer": raw_answer,
            "task_summary": task_summary,
            "history": history_records,
            "memory": memories,
            "identity": identity,
            "language": language,
            "input_images": input_images,
            "media": all_images,
            "system_time": system_time,
            "execution_trace": execution_trace,
        })
        formatter_out = self.formatter.run(formatter_payload)
        self.log_step("Formatter", formatter_payload, formatter_out)
        
        final_text = formatter_out.get("result", {}).get("final_user_message", raw_answer)
        return {"text": final_text, "images": all_images}

    def generate_response(self, role: AIRole, system_prompt: str, user_prompt: str, history_records: list[HistoryRecord] | None = None, encode_images: bool = False, input_images: list[str] | None = None) -> str:
        """Utility for roles to query the LLM.
        
        Args:
            role: The role making the request.
            system_prompt: System-level instructions.
            user_prompt: The user-facing prompt text.
            history_records: Optional conversation/task history records.
            encode_images: Whether to encode image data in the payload.
            input_images: Optional list of image hashes to attach to the user prompt.
        """
        
        # Build the prompt array 
        records = []
        
        # Prepend the existing history from the particular context (task or dialog)
        if history_records:
            records.extend(history_records)

        # Add system prompt
        records.append(HistoryRecord("system", system_prompt))
            
        # Append the current step's user prompt to the end
        records.append(HistoryRecord("user", user_prompt))
        
        image_resolver = self.image_manager.get_image_base64 if self.image_manager else None

        if input_images and len(records) > 1:
            records[-1].image_hashes = input_images
            encode_images = True
        
        try:
            return self.providers_manager.generation_request(
                self.model, 
                records,
                encode_images=encode_images, 
                image_resolver=image_resolver
            )
        except Exception as e:
            traceback.print_exc()
            return f'{{"notes": "Error during generation", "result": {{"error": "{str(e)}"}}}}'
