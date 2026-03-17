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
        
        # ── 3. Deconstructor ────────────────────────────────────────────
        # Receives: input, history, memory, input_images
        if send_status:
            send_status("Deconstructing task...")
        
        abilities = self.mcp_connector.get_all_abilities() if self.mcp_connector else []
        deconstructor_payload = {
            "task_summary": task_summary,
            "abilities": abilities,
        }
        deconstructor_out = self.deconstructor.run(deconstructor_payload)
        self.log_step("Deconstructor", deconstructor_payload, deconstructor_out)
        
        steps = deconstructor_out.get("result", {}).get("steps", [])
        task_table = steps
        current_step_index = 0
        tool_results = []
        collected_images = []
        
        # ── Task execution loop ─────────────────────────────────────────
        while current_step_index < len(task_table):
            
            # Check for mid-loop summary
            if len(history_manager.get_dialog_records()) >= 20:
                if send_status:
                    send_status("Summarizing long conversation...")
                summary_payload = {"history": history_manager.get_dialog_records()}
                sum_out = self.summary.run(summary_payload, history_manager=history_manager)
                self.log_step("Summary", summary_payload, sum_out)
                
            current_step = task_table[current_step_index]

            # Check Retry Limit
            if current_step.get("retry_count", 0) >= 3:
                if current_step.get("critical", False):
                    raw_answer = f"Task failed because critical step '{current_step.get('description', 'Unknown')}' could not be completed after 3 attempts."
                    if send_status: 
                        send_status(raw_answer)
                    break
                else:
                    task_table[current_step_index]["status"] = "failed"
                    current_step_index += 1
                    if send_status:
                        send_status(f"Step '{current_step.get('description', 'Unknown')}' failed after 3 attempts. Non-critical, skipping.")
                    continue
            
            # ── 4. Worker ───────────────────────────────────────────────
            # Receives: task, tasks, tools, tool_results, verification_feedback
            if send_status:
                send_status(f"Executing step: {current_step.get('description', 'Unknown')}")
            
            tools = self.mcp_connector.get_available_tools() if self.mcp_connector else []
            abilities = self.mcp_connector.get_all_abilities() if self.mcp_connector else []
            verification_feedback = current_step.get("_verification_feedback", "")
            
            worker_payload = {
                "task": current_step,
                "tools": tools,
                "abilities": abilities,
                "tool_results": tool_results,
                "verification_feedback": verification_feedback,
            }
            worker_out = self.worker.run(worker_payload)
            self.log_step("Worker", worker_payload, worker_out)
            
            worker_ans = worker_out.get("result", {})
            action = worker_ans.get("action")
            status = worker_ans.get("status", "success")
            
            # Log worker behavior to task history
            notes = worker_out.get("notes", "")
            if notes:
                history_manager.add_task_record("model", f"[Worker Reasoning]: {notes}")
            history_manager.add_task_record("model", f"[Worker Result]: {json.dumps(worker_ans, ensure_ascii=False)}")
            
            worker_answer = worker_ans
            step_images = worker_answer.get("media", [])
            if not isinstance(step_images, list):
                step_images = []
                
            if step_images:
                collected_images.extend(step_images)
            
            if action == "tool":
                # Execution Stage
                tool_name = worker_answer.get("tool_name")
                arguments = worker_answer.get("arguments", {})
                if send_status:
                    send_status(f"Executing tool {tool_name}...")
                    
                tool_result = self.execute_tool(tool_name, arguments)
                
                result_entry = {
                    "step_id": current_step.get("id"),
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
                
                if step_images:
                    result_entry["images"] = step_images
                    collected_images.extend(step_images)
                
                tool_results.append(result_entry)
                    
            elif action == "ask_user":
                # Interrupt pipeline and ask user
                return {"text": worker_answer.get("message", "I need more information to proceed."), "images": []}
                    
            elif action == "text":
                tool_results.append({
                    "step_id": current_step.get("id"),
                    "action": "text",
                    "result": worker_answer.get("message", ""),
                })
            elif action == "interrupt":
                tool_results.append({
                    "step_id": current_step.get("id"),
                    "action": "interrupt",
                    "status": "interrupt",
                    "result": worker_answer.get("answer", "task_unexecutable"),
                })
                
            # ── 5. Verifier ─────────────────────────────────────────────
            # Receives: task, answer, images (generated in this step)
            if send_status:
                send_status("Verifying step result...")
            
            # Get the latest result for this step
            step_results = [r for r in tool_results if r.get("step_id") == current_step.get("id")]
            latest_answer = step_results[-1] if step_results else {}
            
            verifier_payload = {
                "task": current_step,
                "worker_output": worker_answer,
                "answer": latest_answer,
                "images": step_images,
            }
            verifier_out = self.verifier.run(verifier_payload)
            self.log_step("Verifier", verifier_payload, verifier_out)
            
            approved = verifier_out.get("result", {}).get("approved", False)
            is_critical = verifier_out.get("result", {}).get("is_critical", False)
            
            if status == "interrupt":
                if is_critical or current_step.get("critical", False):
                    raw_answer = f"Pipeline interrupted: critical step failed. Notes: {verifier_out.get('notes', '')}"
                    if send_status:
                        send_status(raw_answer)
                    return {"text": raw_answer, "images": collected_images}
                else:
                    task_table[current_step_index]["status"] = "skipped"
                    if send_status:
                        send_status(f"Step skipped (non-critical interrupt): {verifier_out.get('notes', '')}")
                    current_step_index += 1
                    continue
            
            if approved:
                task_table[current_step_index]["status"] = "completed"
                current_step_index += 1
            else:
                # Loop back to worker (index stays the same)
                task_table[current_step_index]["retry_count"] = task_table[current_step_index].get("retry_count", 0) + 1
                task_table[current_step_index]["_verification_feedback"] = verifier_out.get("notes", "Verification failed.")
                    
        # ── 6. Aggregator ───────────────────────────────────────────────
        # Receives: input, task_results, task_table, input_images
        if send_status:
            send_status("Aggregating results...")
        
        aggregator_payload = {
            "task_summary": task_summary,
            "task_results": tool_results,
            "task_table": task_table,
            "input_images": input_images,
            "media": collected_images,
        }
        aggregator_out = self.aggregator.run(aggregator_payload)
        self.log_step("Aggregator", aggregator_payload, aggregator_out)
        
        raw_answer = aggregator_out.get("result", {}).get("answer", "Task completed.")
        # Aggregator collects media from results
        aggregator_media = aggregator_out.get("result", {}).get("images", [])
        # Merge any images from aggregator with those we collected
        all_images = list(dict.fromkeys(collected_images + aggregator_media))
        
        # ── 7. Formatter ────────────────────────────────────────────────
        # Receives: raw_answer, input, history, memory, identity, media, input_images
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
