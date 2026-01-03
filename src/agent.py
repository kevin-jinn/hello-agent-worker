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
    stt,
)
from livekit.plugins import silero, sarvam, openai, elevenlabs

# --------------------------------------------------
# Logging
# --------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent")

load_dotenv(".env.local")

# --------------------------------------------------
# Agent
# --------------------------------------------------
class Assistant(Agent):
    def __init__(self):
        super().__init__(
            instructions=(
                "You are a helpful voice AI assistant speaking to users over a phone call. "
                "Be concise, natural, and conversational."
            )
        )

# --------------------------------------------------
# Prewarm (SIP-safe VAD)
# --------------------------------------------------
def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load(
        min_speech_duration=0.1,
        min_silence_duration=0.15,   # 🔥 critical for SIP
        prefix_padding_duration=0.2,
        activation_threshold=0.10,   # 🔥 critical for noisy lines
        max_buffered_speech=8.0,     # 🔥 REQUIRED
    )
    logger.info("VAD prewarmed")

# --------------------------------------------------
# Entrypoint
# --------------------------------------------------
async def entrypoint(ctx: JobContext):
    logger.info("Connecting to room...")
    await ctx.connect()

    # Log track subscription (confirms RTP)
    @ctx.room.on("track_subscribed")
    def on_track_subscribed(track, publication, participant):
        logger.info(
            f"Audio track subscribed from {participant.identity}"
        )

    # --------------------------------------------------
    # Agent session
    # --------------------------------------------------
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

        # 🔑 SIP conversation stability
        allow_interruptions=True,
        min_interruption_duration=0.15,
        min_consecutive_speech_delay=0.4,
        resume_false_interruption=True,
        user_away_timeout=6.0,

        preemptive_generation=False,  # enable AFTER greeting
    )

    await session.start(agent=Assistant(), room=ctx.room)

    logger.info("Waiting for participant...")
    await ctx.wait_for_participant()

    # --------------------------------------------------
    # Greeting
    # --------------------------------------------------
    await session.say(
        """Hello! This is an automated call from Tata Motors Commercial Vehicles. We hope you are doing well today!

We are contacting you to share exciting information about our new launch — Tata Ace Pro EV, India’s most affordable 4-wheeler electric vehicle, specially designed for smart and sustainable commercial needs.

Let me tell you about its key features:

The Tata Ace Pro EV is highly cost-saving (running cost of less than ₹1 per kilometer), reliable, comes with a 750 kg payload capacity, and offers an on-road range of 100 to 150 kilometers.

Along with this, you also get Tata’s trust and service, as well as attractive finance and exchange offers.

Would you like to receive more information about it, or schedule a demo and test drive with our team?"""
    )

    # 🔑 Enable back-and-forth conversation
    session.preemptive_generation = True
    logger.info("Preemptive generation enabled")

    # --------------------------------------------------
    # Debug hooks (safe)
    # --------------------------------------------------
    @session.on("user_input_transcribed")
    def on_user_input(ev):
        logger.info(f"USER SAID: {ev.text}")

    @session.on("metrics_collected")
    def on_metrics(ev):
        if ev.metrics.type == "eou_metrics":
            logger.info(
                f"EOU detected | delay={ev.metrics.end_of_utterance_delay}"
            )

    @session.on("error")
    def on_error(ev):
        logger.error(f"AGENT ERROR: {ev}")

# --------------------------------------------------
# Main
# --------------------------------------------------
if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            agent_name="outbound-kj",
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
        )
    )
