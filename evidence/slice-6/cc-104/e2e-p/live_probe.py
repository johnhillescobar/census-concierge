import asyncio, sys, os
sys.path.insert(0, "api")
from dotenv import load_dotenv
load_dotenv(".env")
from src.ask import ExecutionRecord, run_ask
async def one(q):
    rec = ExecutionRecord(question=q)
    r = await run_ask(q, record=rec)
    i = rec.intent
    print("Q:", q)
    print("  tools:", [t["tool"] for t in rec.timings])
    print("  report: places", i.places, "parents", i.parents, "level", i.level, "unit", i.unit, "parent_level", i.parent_level, "states_named", i.states_named, "answered_places", i.answered_places, "reported", i.reported)
    print("  geo_status:", {k: v for k, v in (rec.geo_status or {}).items() if v not in (False, "", 0)})
    print("  urls:", len(r.urls), "| warnings:", [(w.code, w.detail[:90]) for w in r.warnings])
    print("  answer:", r.answer[:160].replace("\n", " "))
async def main():
    for q in sys.argv[1:]:
        await one(q)
asyncio.run(main())
