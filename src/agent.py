import asyncio
import logging
from dotenv import load_dotenv

from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    WorkerOptions,
    cli,
)

from livekit.plugins import silero, sarvam, openai, elevenlabs

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent")

load_dotenv(".env.local")

class Assistant(Agent):
    def __init__(self):
        super().__init__(
            instructions=(
                "You are a helpful voice AI assistant speaking to users over a phone call. "
                "Be concise, natural, and conversational."
            )
        )

def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()

async def entrypoint(ctx: JobContext):
    await ctx.connect()

    session = AgentSession(
        stt=sarvam.STT(model="saarika-v2", language="en-IN"),
        llm=openai.LLM(model="gpt-4.1-mini"),
        tts=elevenlabs.TTS(
            model="eleven_turbo_v2",
            voice_id="kiaJRdXJzloFWi6AtFBf",
        ),
        vad=ctx.proc.userdata["vad"],
        preemptive_generation=False,  # IMPORTANT at start
    )

    await session.start(agent=Assistant(), room=ctx.room)

    # 🔑 WAIT FOR SIP PARTICIPANT
    participant = await ctx.wait_for_participant()

    # small delay to ensure RTP is flowing
    await asyncio.sleep(0.5)

    # 🔊 NOW speak
    await session.say(
        "Hello! This is your virtual assistant. How can I help you today?"
    )

    # enable natural back-and-forth AFTER greeting
    session.preemptive_generation = True


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            agent_name="outbound-kj",
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
        )
    )
