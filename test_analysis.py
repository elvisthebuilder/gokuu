import asyncio
from server.agent import agent

async def test():
    query = "[File Received: /tmp/sample.txt] (System Action: The user just uploaded this file without any instructions. Please analyze it and tell the user what you found in a natural, conversational way. End by asking what they would like to do with it.)"
    print("Sending query...\n")
    
    async for event in agent.run_agent(query, source="telegram"):
        if event["type"] == "message":
            print(f"\nResponse: {event['content']}")
        elif event["type"] == "tool_call":
            print(f"Tool executing: {event['name']}")

asyncio.run(test())
