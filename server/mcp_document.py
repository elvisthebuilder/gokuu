import os
import uvicorn # type: ignore
from fastapi import FastAPI, HTTPException # type: ignore
from pydantic import BaseModel # type: ignore
from markitdown import MarkItDown # type: ignore
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MCP-Document")

app = FastAPI(title="Goku Document Analysis MCP", version="1.0.0")
md = MarkItDown()

class ToolCall(BaseModel):
    name: str
    arguments: dict

@app.get("/tools")
async def get_tools():
    """Returns the tool definitions for this MCP server."""
    return [
        {
            "name": "parse_document",
            "description": "Convert a document file (PDF, DOCX, XLSX, PPTX, etc.) to Markdown for analysis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The absolute path to the document file to parse."
                    }
                },
                "required": ["file_path"]
            }
        }
    ]

@app.post("/call")
async def call_tool(tool_call: ToolCall):
    """Executes a tool call."""
    if tool_call.name == "parse_document":
        file_path = tool_call.arguments.get("file_path")
        if not file_path:
            raise HTTPException(status_code=400, detail="file_path is required")
        
        if not os.path.exists(file_path):
            return {"error": f"File not found at path: {file_path}"}
        
        try:
            logger.info(f"Parsing document: {file_path}")
            result = md.convert(file_path)
            return {
                "content": result.text_content,
                "metadata": {
                    "extension": os.path.splitext(file_path)[1],
                    "size": os.path.getsize(file_path)
                }
            }
        except Exception as e:
            logger.error(f"Failed to parse document: {str(e)}")
            return {"error": f"Conversion failed: {str(e)}"}
    
    raise HTTPException(status_code=404, detail=f"Tool {tool_call.name} not found")

if __name__ == "__main__":
    # Get port from env or default to 8082
    port = int(os.getenv("PORT", 8082))
    uvicorn.run(app, host="0.0.0.0", port=port)
