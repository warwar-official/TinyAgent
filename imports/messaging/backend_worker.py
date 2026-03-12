import traceback
from imports.messaging.queue_manager import MessageBus
from imports.messaging.message_models import AgentRequest, AgentResponse
from imports.loop_manager import LoopManager, AgentMessage

def backend_worker_loop(bus: MessageBus, loop_manager: LoopManager) -> None:
    """
    Background thread that continually reads from frontend_to_backend queue
    and passes tasks to the single LoopManager instance.
    """
    while True:
        try:
            request: AgentRequest = bus.frontend_to_backend.get()
            
            # Helper function to inject into LoopManager for intermediate status updates
            def send_status(msg: str) -> None:
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
                    if send_status:
                        send_status("Downloading image attachment...")
                    # Note: Need access to ImageManager here instance. Let's pass image_manager into backend_worker_loop
                    request.image_hash = loop_manager.image_manager.save_image_from_url(image_url)
                    request.text = caption
                except Exception as e:
                    if send_status:
                        send_status(f"Failed to download image: {e}")
                    request.text = caption
            
            # Execute based on action
            answer = "Unknown action."
            try:
                if request.action == "message":
                    agent_message = AgentMessage(
                        text=request.text,
                        image_hash=request.image_hash
                    )
                    answer = loop_manager.router(agent_message, send_status=send_status)
                elif request.action == "init":
                    answer = loop_manager.init_agent(send_status=send_status)
                elif request.action == "own_task":
                    answer = loop_manager.own_task(send_status=send_status)
                elif request.action == "identity_rethink":
                    answer = loop_manager.identity_rethink(send_status=send_status)
            except Exception as e:
                # Log stack trace and send error response
                traceback.print_exc()
                answer = f"Error processing request: {str(e)}"

            # Send the final response
            bus.send_to_frontend(AgentResponse(
                frontend_type=request.frontend_type,
                chat_id=request.chat_id,
                type="final_response",
                text=answer
            ))

        except Exception as queue_err:
            print(f"Critical error in backend worker loop: {queue_err}")
