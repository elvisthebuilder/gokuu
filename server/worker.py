import os
from celery import Celery
from dotenv import load_dotenv

load_dotenv()

redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
app = Celery("goku_worker", broker=redis_url, backend=redis_url)

@app.task
def process_background_skill(skill_name: str, args: dict):
    # This would execute long-running skills (e.g. web research)
    import asyncio
    from .main import registry
    
    skill = registry.get_skill(skill_name)
    if not skill:
        return f"Error: Skill {skill_name} not found."
    
    return asyncio.run(skill.execute(args.get("tool"), args))
