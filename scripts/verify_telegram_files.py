import asyncio
import os
from unittest.mock import AsyncMock, MagicMock
from server.telegram_bot import handle_message

async def test_file_reception():
    print("--- Testing Telegram File Reception ---")
    
    # Mock Update and context
    update = MagicMock()
    update.effective_chat.id = 12345
    update.message.text = None
    update.message.caption = "Summarize this"
    
    # Mock Document
    doc = MagicMock()
    doc.file_id = "file123"
    doc.file_name = "test_doc.txt"
    update.message.document = doc
    update.message.photo = None
    
    # Mock Context and Bot
    context = MagicMock()
    file_mock = AsyncMock()
    context.bot.get_file = AsyncMock(return_value=file_mock)
    
    # Mock status message
    status_msg = AsyncMock()
    update.message.reply_text = AsyncMock(return_value=status_msg)
    
    # Run handle_message
    # We need to mock agent.run_agent as well to avoid actual LLM calls
    from server.agent import agent
    agent.run_agent = MagicMock()
    async def mock_run_agent(*args, **kwargs):
        yield {"type": "message", "content": "File received and processed."}
    agent.run_agent.return_value = mock_run_agent()
    
    try:
        await handle_message(update, context)
        print("✅ handle_message executed without errors.")
        
        # Verify file download attempt
        context.bot.get_file.assert_called_with("file123")
        file_mock.download_to_drive.assert_called()
        print("✅ Bot attempted to download file.")
        
        # Verify agent notification
        args, kwargs = agent.run_agent.call_args
        assert "[File Received:" in args[0]
        assert "Summarize this" in args[0]
        print("✅ Agent was notified about the file and caption.")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_file_reception())
