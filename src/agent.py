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
    stt
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
    proc.userdata["vad"] = silero.VAD.load(
        min_speech_duration=0.2,
        min_silence_duration=0.4,
    )


async def entrypoint(ctx: JobContext):
    await ctx.connect()

    session = AgentSession(
        stt=stt.StreamAdapter(
            stt=sarvam.STT(
                model="saarika-v2",
                language="en-IN",
            ),
            vad=ctx.proc.userdata["vad"],
        ),

        llm=openai.LLM(model="gpt-4.1-mini"),

        tts=elevenlabs.TTS(
            model="eleven_turbo_v2",
            voice_id="kiaJRdXJzloFWi6AtFBf",
        ),

        # 🔑 REQUIRED for live calls
        allow_interruptions=True,
        min_interruption_duration=0.3,
        user_away_timeout=8.0,

        preemptive_generation=False,
    )

    await session.start(agent=Assistant(), room=ctx.room)

    await ctx.wait_for_participant()

    await asyncio.sleep(0.6)

    await session.say(
        "Hello! This is your virtual assistant. How can I help you today?"
    )

    session.preemptive_generation = True


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            agent_name="outbound-kj",
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
        )
    )
