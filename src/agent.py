import asyncio
import logging
from dotenv import load_dotenv

from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    JobProcess,
    cli,
)

from livekit.plugins import silero, sarvam, openai, elevenlabs

# --------------------------------------------------
# Logging
# --------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent")

# Load environment variables
load_dotenv(".env.local")

# --------------------------------------------------
# Agent definition
# --------------------------------------------------
class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=(
                "You are a helpful voice AI assistant speaking to users over a phone call. "
                "Your responses should be natural, concise, and conversational. "
                "Avoid emojis, markdown, or special formatting. "
                "Be friendly, polite, and efficient."
            )
        )

# --------------------------------------------------
# Agent server
# --------------------------------------------------
server = AgentServer()

# --------------------------------------------------
# Prewarm (VAD only — safe for self-hosted)
# --------------------------------------------------
def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()

server.setup_fnc = prewarm

# --------------------------------------------------
# RTC session handler
# --------------------------------------------------
@server.rtc_session()
async def my_agent(ctx: JobContext):
    await ctx.connect()

    session = AgentSession(
        stt=sarvam.STT(model="saarika-v2", language="en-IN"),
        llm=openai.LLM(model="gpt-4.1-mini"),
        tts=elevenlabs.TTS(
            model="eleven_turbo_v2",
            voice_id="kiaJRdXJzloFWi6AtFBf",
        ),
        vad=ctx.proc.userdata["vad"],
        preemptive_generation=False,  # important initially
    )

    await session.start(agent=Assistant(), room=ctx.room)

    def on_participant_connected(participant):
        if participant.kind.name == "SIP":
            asyncio.create_task(handle_sip_join())

    async def handle_sip_join():
        await asyncio.sleep(0.6)
        await session.say(
            "Hello! This is your virtual assistant. How can I help you today?"
        )
        session.preemptive_generation = True

    ctx.room.on("participant_connected", on_participant_connected)





# --------------------------------------------------
# Entry point
# --------------------------------------------------
if __name__ == "__main__":
    cli.run_app(server)
