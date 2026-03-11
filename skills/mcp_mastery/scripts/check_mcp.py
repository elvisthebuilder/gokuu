import httpx
import asyncio
import os
import sys

# Standard MCP ports in Goku
SERVERS = {
    "git": "http://localhost:8080",
    "search": "http://localhost:8081",
    "document": "http://localhost:8082",
    "voice": "http://localhost:8083"
}

async def check_server(name, url):
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{url}/tools")
            if resp.status_code == 200:
                print(f"✅ {name}: Online ({len(resp.json())} tools)")
                # For voice, check if API keys are ready
                if name == "voice":
                    call_resp = await client.post(f"{url}/call", json={"name": "list_voices", "arguments": {}})
                    if "error" in call_resp.json():
                        print(f"   ⚠️ Warning: {call_resp.json()['error']}")
                    else:
                        print(f"   ✨ ElevenLabs API Key: Verified")
            else:
                print(f"❌ {name}: HTTP {resp.status_code}")
    except Exception as e:
        print(f"❌ {name}: Offline ({str(e)})")

async def main():
    print("🔍 Goku MCP Diagnostic Tool\n" + "="*30)
    tasks = [check_server(name, url) for name, url in SERVERS.items()]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
