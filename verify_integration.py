import asyncio
import json
from server.mcp_manager import mcp_manager

async def verify_integration():
    print("--- Goku-OpenClaw Integration Verification ---")
    
    # 1. Test Ingestion
    print("\n[1] Testing Tool Ingestion...")
    tools = await mcp_manager.get_all_tools()
    claw_tools = [t for t in tools if t["function"]["name"].startswith("openclaw_")]
    native_tools = [t for t in tools if t.get("source") == "native"]
    
    print(f"Total Tools Found: {len(tools)}")
    print(f"OpenClaw Tools: {len(claw_tools)}")
    print(f"Native Tools: {len(native_tools)} (e.g., {', '.join([t['function']['name'] for t in native_tools])})")
    
    if len(claw_tools) > 0:
        print("✅ Ingestion Successful.")
    else:
        print("❌ Ingestion Failed.")
        return

    # 2. Test Tool Routing (OpenClaw)
    print("\n[2] Testing Tool Routing (openclaw_weather)...")
    weather_tool = next((t for t in claw_tools if "weather" in t["function"]["name"]), None)
    if weather_tool:
        tool_name = weather_tool["function"]["name"]
        print(f"Calling {tool_name}...")
        result = await mcp_manager.call_tool(tool_name, {"user_intent": "What is the weather in London?"})
        print(f"Result Status: {result.get('status')}")
        if result.get("status") == "success" and "instructions" in result:
            print("✅ OpenClaw Routing Successful.")
        else:
            print("❌ OpenClaw Routing Failed.")
    else:
        print("⚠️ Weather tool not found, skipping OpenClaw routing test.")

    # 3. Test Tool Routing (Native Bash)
    print("\n[3] Testing Tool Routing (bash)...")
    bash_result = await mcp_manager.call_tool("bash", {"command": "echo 'Goku is superior'"})
    if isinstance(bash_result, dict) and "stdout" in bash_result:
        print(f"Output: {bash_result['stdout'].strip()}")
        if "Goku is superior" in bash_result["stdout"]:
            print("✅ Native Bash Routing Successful.")
        else:
            print("❌ Native Bash Routing Failed (incorrect output).")
    else:
        print(f"❌ Native Bash Routing Failed: {bash_result}")

if __name__ == "__main__":
    asyncio.run(verify_integration())
