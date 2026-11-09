# VIDEO · 24 Voice Agent Pipeline

hook: Interrupt this AI mid-sentence, and it stops in 40 ms.

demo_cmd: python demo.py

demo_output:
```text
    2.940s  stt     | final "hi can you tell me your opening hours please"  (endpoint +300 ms, stt +120 ms)
    3.190s  llm     | first token  (+250 ms after transcript)
    3.320s  speaker | "Sure!" (300 ms)  <- voice-to-voice 800 ms
    6.040s  barge-in| user talked over the agent -> stopped after 40 ms; user heard: "Sure! We're open from nine to six, Monday to"
   13.830s  speaker | filler "One moment." (600 ms)  <- voice-to-voice 870 ms
   1  hi can you tell me your opening...   800 ms        300   120   250   130  PASS
   3  and what will the weather be to...   870 ms        300   120   950   210  PASS via filler (llm 950 ms > 300 ms)
same call in batch mode -> first turn heard after 2160 ms (vs 800 ms in streaming mode)
```

diagram:
1. Mic frames -> VAD + speech-to-text
2. Streaming LLM tokens
3. Phrase chunker -> text-to-speech
4. Speaker (cancel on barge-in)
5. Latency budget per stage

real_world: A restaurant's phone line takes bookings with a voice agent that answers in under a second and stops
talking the moment the caller interrupts.

try_it: Change end_silence_ms from 300 to 600 in EnergyVAD and see which turns now fail the budget.

flow_steps:
1. `cli.py` loads settings from `config.py` and the scripted caller from `examples/conversation.json`, then runs the call on the virtual clock in `clock.py`.
2. `audio.py` sends 20 ms microphone frames; `ears.py` detects when the caller starts and stops talking and emits the final transcript 120 ms later.
3. `pipeline.py` starts a response: `brain.py` streams tokens, `mouth.py` cuts them into phrases, synthesises each one and plays the first phrase while the model is still writing.
4. When the caller talks over the agent, `pipeline.py` cancels the whole response in 40 ms and remembers only the words the caller actually heard; for the slow weather question it says "One moment." instead of going silent.
5. `budget.py` splits every turn's latency into endpoint, STT, LLM and TTS and checks it against the one-second budget, and the CLI shows the same call in batch mode for comparison.
