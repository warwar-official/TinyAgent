import traceback
from imports.messaging.queue_manager import MessageBus
from imports.messaging.message_models import AgentRequest, AgentResponse
from imports.agent.pipeline.pipeline_engine import PipelineEngine
from imports.history_manager import HistoryManager
from imports.execution_trace import ExecutionTraceManager

def backend_worker_loop(bus: MessageBus, pipeline_engine: PipelineEngine, history_manager: HistoryManager, execution_trace_manager: ExecutionTraceManager) -> None:
    """
    Background thread that continually reads from frontend_to_backend queue
    and passes tasks to the single PipelineEngine instance.
    """
    while True:
        try:
            request: AgentRequest = bus.frontend_to_backend.get()
            
            # Helper function to inject into PipelineEngine for intermediate status updates
            def send_status(msg: str) -> None:
                import os
                if os.getenv("DEBUG", "False").lower() == "true":
                    bus.send_to_frontend(AgentResponse(
                        frontend_type=request.frontend_type,
                        chat_id=request.chat_id,
                        type="status_update",
                        text=msg
                    ))

            # Process image if present in the text (sent by telegram plugin)
            if request.text.startswith("[IMAGE_URL_ATTACHED]:"):
                parts = request.text.split("\n", 1)
                image_url = parts[0].replace("[IMAGE_URL_ATTACHED]:", "")
                caption = parts[1] if len(parts) > 1 else ""
                
                try:
                    send_status("Downloading image attachment...")
                    if pipeline_engine.image_manager:
                        image_hash = pipeline_engine.image_manager.save_image_from_url(image_url)
                        request.image_hashes.append(image_hash)
                    request.text = caption
                except Exception as e:
                    send_status(f"Failed to download image: {e}")
                    request.text = caption
            
            if not request.text or not request.text.strip():
                if request.action == "message":
                    bus.send_to_frontend(AgentResponse(
                        frontend_type=request.frontend_type,
                        chat_id=request.chat_id,
                        type="final_response",
                        text="Please provide a message."
                    ))
                    continue

            # Determine if this is a pipeline resumption (ask_user continuation)
            is_resuming = pipeline_engine.is_waiting_for_user

            # Add User message to Conversational History
            if request.action == "message":
                history_manager.add_dialog_record("user", request.text, image_hashes=request.image_hashes)

            # Create initial payload for the pipeline
            initial_payload = {
                "input_message": {
                    "text": request.text,
                    "image_hashes": request.image_hashes,
                },
            }
            
            # Execute based on action
            answer = "Unknown action."
            images = []
            try:
                pipeline_result = None
                if request.action == "message":
                    pipeline_result = pipeline_engine.run_pipeline(
                        initial_payload, 
                        history_manager=history_manager, 
                        execution_trace_manager=execution_trace_manager, 
                        send_status=send_status
                    )
                
                # Extract text and images from pipeline result
                if isinstance(pipeline_result, dict):
                    result_type = pipeline_result.get("type", "")
                    
                    if result_type == "ask_user":
                        # Pipeline is suspended — send the question and wait for user response
                        answer = pipeline_result.get("text", "I need more information.")
                        images = pipeline_result.get("images", [])
                        
                        # Add the ask_user question to history as model's message
                        if request.action == "message":
                            history_manager.add_dialog_record("model", answer, image_hashes=images)
                        
                        # Send as final_response (the user will reply, and pipeline will resume)
                        bus.send_to_frontend(AgentResponse(
                            frontend_type=request.frontend_type,
                            chat_id=request.chat_id,
                            type="final_response",
                            text=answer,
                            image_hashes=images,
                        ))
                        continue  # Skip post-pipeline jobs, wait for user reply
                    else:
                        answer = pipeline_result.get("text", "Processing error.")
                        images = pipeline_result.get("images", [])
                elif pipeline_result is not None:
                    answer = str(pipeline_result)
                
                # Update dialogue history with final answer and generated images
                if request.action == "message":
                    history_manager.add_dialog_record("model", answer, image_hashes=images)
                history_manager.clear_task_history()

            except Exception as e:
                # Log stack trace and send error response
                traceback.print_exc()
                answer = f"Error processing request: {str(e)}"

            # Send the final response with all images
            bus.send_to_frontend(AgentResponse(
                frontend_type=request.frontend_type,
                chat_id=request.chat_id,
                type="final_response",
                text=answer,
                image_hashes=images
            ))
            
            # Post-pipeline background jobs (only for completed pipelines, not ask_user)
            if request.action == "message":
                def post_pipeline_jobs():
                    try:
                        # 1. Summary Check
                        if len(history_manager.get_dialog_records()) >= 20:
                            sum_payload = {"history": history_manager.get_dialog_records()}
                            sum_out = pipeline_engine.summary.run(sum_payload, history_manager=history_manager)
                            pipeline_engine.log_step("Summary", sum_payload, sum_out)
                            
                        # 2. Memory Creation
                        mem_payload = {"history": history_manager.get_dialog_records()}
                        m_out = pipeline_engine.memory_creation.run(mem_payload)
                        if m_out:
                            pipeline_engine.log_step("MemoryCreation", mem_payload, m_out)
                    except Exception as e:
                        traceback.print_exc()
                import threading
                threading.Thread(target=post_pipeline_jobs, daemon=True).start()

        except Exception as queue_err:
            print(f"Critical error in backend worker loop: {queue_err}")
