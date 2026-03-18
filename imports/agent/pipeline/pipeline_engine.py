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

class PipelineEngine:
    def __init__(self, providers_manager: ProvidersManager, model: Model, config: dict, image_manager=None, mcp_connector=None):
        self.providers_manager = providers_manager
        self.model = model
        self.config = config
        self.image_manager = image_manager
        self.mcp_connector = mcp_connector

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
        with open("role_payload.json", "a") as f:
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

    def run_pipeline(self, initial_payload: dict, history_manager, send_status: Optional[Callable[[str], None]] = None) -> dict:
        """
        Executes the main role-based execution pipeline with strict role isolation.
        
        Each role receives ONLY the data it needs — no shared mutable payload.
        
        Returns:
            dict: {"text": str, "images": list[str]}
        """
        # Extract core inputs
        user_input = initial_payload.get("input_message", {}).get("text", "")
        input_images = initial_payload.get("input_message", {}).get("image_hashes", [])
        
        # ── 1. Retriever (MemoryRetrieval) ──────────────────────────────
        # Receives: only input
        if send_status:
            send_status("Retrieving memories...")
        
        retriever_payload = {"input": user_input}
        mem_out = self.memory_retrieval.run(retriever_payload)
        self.log_step("MemoryRetrieval", retriever_payload, mem_out)
        memories = mem_out.get("result", {}).get("memories", [])
        
        # Log memory payload size
        memories_text = json.dumps(memories, ensure_ascii=False)
        print(f"[DEBUG] memory_payload_size: {len(memories_text)} characters")
        
        # Gather shared resources
        history_records = history_manager.get_dialog_records() #count=5)
        identity = self.mcp_connector.get_identity_prompt() if self.mcp_connector else ""
        language = self.mcp_connector.get_language() if hasattr(self.mcp_connector, "get_language") else "English"
        
        # ── 2. Router ───────────────────────────────────────────────────
        # Receives: input, history, identity, memory, input_images
        if send_status:
            send_status("Routing request...")
        
        router_payload = {
            "input": user_input,
            "history": history_records,
            "identity": identity,
            "memory": memories,
            "input_images": input_images,
        }
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
            formatter_payload = {
                "raw_answer": raw_answer,
                "task_summary": task_summary,
                "history": history_records,
                "memory": memories,
                "identity": identity,
                "language": language,
                "input_images": input_images,
                "media": [],
            }
            formatter_out = self.formatter.run(formatter_payload)
            self.log_step("Formatter", formatter_payload, formatter_out)
            
            final_text = formatter_out.get("result", {}).get("final_user_message", "Processing error.")
            return {"text": final_text, "images": []}
        
        # ── TASK PATH ───────────────────────────────────────────────────
        
        MAX_ITERATIONS = 30
        abilities = self.mcp_connector.get_all_abilities() if self.mcp_connector else []
        tools = self.mcp_connector.get_available_tools() if self.mcp_connector else []
        tasks_history = []
        collected_images = []
        step_counter = 0
        
        # ── Iterative execution loop ────────────────────────────────────
        for iteration in range(MAX_ITERATIONS):
            
            # Check for mid-loop summary
            if len(history_manager.get_dialog_records()) >= 20:
                if send_status:
                    send_status("Summarizing long conversation...")
                summary_payload = {"history": history_manager.get_dialog_records()}
                sum_out = self.summary.run(summary_payload, history_manager=history_manager)
                self.log_step("Summary", summary_payload, sum_out)
            
            # ── 3. Deconstructor (next step) ────────────────────────────
            if send_status:
                send_status("Planning next step...")
            
            deconstructor_payload = {
                "task_summary": task_summary,
                "abilities": abilities,
                "tasks_history": tasks_history,
                "media": collected_images,
            }
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
            max_retries = 3
            verification_feedback = ""
            step_resolution = "failure"  # default until verified
            step_result_data = {}
            step_images = []
            
            while retry_count < max_retries:
                if send_status:
                    send_status(f"Executing step {step_counter}: {current_task.get('description', 'Unknown')}")
                
                worker_payload = {
                    "current_task": current_task,
                    "tasks_history": tasks_history,
                    "tools": tools,
                    "abilities": abilities,
                    "verification_feedback": verification_feedback,
                }
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
                    return {"text": worker_ans.get("message", "I need more information to proceed."), "images": []}
                    
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
                
                # ── 5. Verifier ─────────────────────────────────────────
                if send_status:
                    send_status("Verifying step result...")
                
                verifier_payload = {
                    "task": current_task,
                    "worker_output": worker_ans,
                    "answer": step_result_data,
                    "images": step_images,
                }
                verifier_out = self.verifier.run(verifier_payload)
                self.log_step("Verifier", verifier_payload, verifier_out)
                
                resolution = verifier_out.get("result", {}).get("resolution", "failure")
                
                if resolution == "success":
                    step_resolution = "success"
                    break
                elif resolution == "interrupt":
                    step_resolution = "interrupt"
                    break
                else:
                    # failure — retry
                    retry_count += 1
                    verification_feedback = verifier_out.get("notes", "Verification failed.")
                    if send_status:
                        send_status(f"Step failed verification (attempt {retry_count}/{max_retries}). Retrying...")
            
            # ── Append to tasks_history ─────────────────────────────────
            history_entry = {
                "id": step_counter,
                "description": current_task.get("description", ""),
                "resolution": step_resolution,
                "result": step_result_data,
                # Only keep images from successful steps
                "media": step_images if step_resolution == "success" else [],
            }
            tasks_history.append(history_entry)
            
            # Collect images only from successful steps
            if step_resolution == "success" and step_images:
                collected_images.extend(step_images)
        
        else:
            # Loop exhausted MAX_ITERATIONS
            tasks_history.append({
                "id": step_counter + 1,
                "description": "Step limit reached",
                "resolution": "interrupt",
                "result": f"Pipeline interrupted: maximum iteration limit ({MAX_ITERATIONS}) reached.",
                "media": [],
            })
            if send_status:
                send_status(f"Step limit ({MAX_ITERATIONS}) reached. Aggregating results...")
                    
        # ── 6. Aggregator ───────────────────────────────────────────────
        if send_status:
            send_status("Aggregating results...")
        
        aggregator_payload = {
            "task_summary": task_summary,
            "tasks_history": tasks_history,
            "input_images": input_images,
            "media": collected_images,
        }
        aggregator_out = self.aggregator.run(aggregator_payload)
        self.log_step("Aggregator", aggregator_payload, aggregator_out)
        
        raw_answer = aggregator_out.get("result", {}).get("answer", "Task completed.")
        aggregator_media = aggregator_out.get("result", {}).get("images", [])
        all_images = list(dict.fromkeys(collected_images + aggregator_media))
        
        # ── 7. Formatter ────────────────────────────────────────────────
        if send_status:
            send_status("Formatting response...")
        
        formatter_payload = {
            "raw_answer": raw_answer,
            "task_summary": task_summary,
            "history": history_records,
            "memory": memories,
            "identity": identity,
            "language": language,
            "input_images": input_images,
            "media": all_images,
        }
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
