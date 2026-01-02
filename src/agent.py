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
from livekit import rtc
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
                "Be concise, natural, and conversational. "
                "Wait for the user to finish speaking before replying."
            )
        )


# --------------------------------------------------
# Prewarm (VAD)
# --------------------------------------------------
def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load(
        min_speech_duration=0.1,
        min_silence_duration=0.25,
        prefix_padding_duration=0.2,
        activation_threshold=0.15,
    )
    logger.info("VAD prewarmed")


# --------------------------------------------------
# Debug audio wrapper
# --------------------------------------------------
class DebugAudioInput:
    def __init__(self, inner):
        self.inner = inner
        self.frames = 0

    async def recv(self):
        frame = await self.inner.recv()
        if frame:
            self.frames += 1
            if self.frames % 50 == 0:
                logger.info(f"AUDIO FRAMES RECEIVED: {self.frames}")
        return frame


# --------------------------------------------------
# Entrypoint
# --------------------------------------------------
async def entrypoint(ctx: JobContext):
    logger.info("Connecting to room...")
    await ctx.connect()

    # 🔍 Track subscription debug
    @ctx.room.on("track_subscribed")
    def on_track_subscribed(track, publication, participant):
        logger.info(
            f"Audio track subscribed from participant={participant.identity}, kind={track.kind}"
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
        allow_interruptions=True,
        min_interruption_duration=0.2,
        user_away_timeout=8.0,
        preemptive_generation=False,  # 🔑 enable AFTER greeting
    )

    await session.start(agent=Assistant(), room=ctx.room)

    # 🔍 Wrap audio input to confirm RTP
    # session.input.audio = DebugAudioInput(session.input.audio)

    logger.info("Waiting for participant...")
    await ctx.wait_for_participant()

    # --------------------------------------------------
    # Greeting
    # --------------------------------------------------
    await session.say(
        "Hello! This is your virtual assistant. How can I help you today?"
    )

    # 🔑 ENABLE NATURAL CONVERSATION
    session.preemptive_generation = True
    logger.info("Preemptive generation enabled")

    # --------------------------------------------------
    # Debug events
    # --------------------------------------------------
    @session.on("user_input_transcribed")
    def on_user_input(ev):
        logger.info(f"USER SAID: {ev.text}")

    @session.on("agent_state_changed")
    def on_agent_state(ev):
        logger.info(f"AGENT STATE: {ev.state}")

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
