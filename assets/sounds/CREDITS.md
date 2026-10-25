# Sound credits

| Files | Source | License |
|---|---|---|
| `music/*.wav` | Synthesized placeholders (feel_sound kit, `make_placeholder_assets.py`) | Team-made |
| `objects/{birds,cicadas,wind,crickets,leaves,footsteps}.wav` | ElevenLabs Sound Effects, prompts in `tools/make_sfx_elevenlabs.py` (cicadas: gentle low-pass above 4 kHz) | ElevenLabs free plan: credit "Sound effects by ElevenLabs" |
| `objects/water.wav` | Synthesized placeholder (used by the Great Wave's water) | Team-made |
| `ui/chime.wav` | ElevenLabs Sound Effects (same tool) | ElevenLabs free plan |
| `voice/*.wav` | ElevenLabs, voice "George", model `eleven_v4`, via `tools/make_voices_elevenlabs.py` | ElevenLabs free plan: credit "Voice by ElevenLabs" in the submission |
| `content/library/{great_wave,mondrian}/voice/*.wav` | ElevenLabs, voice "George", model `eleven_v4`, via `tools/make_voices_elevenlabs.py --content` | ElevenLabs free plan: credit "Voice by ElevenLabs" in the submission |
| `content/library/starry_night/voice/*.wav` | macOS built-in voice "Samantha" via `tools/make_voices_say.py` (stand-in; ElevenLabs credits ran out) | Generated on the demo Mac |

When a placeholder is replaced with a real recording, update its row here with the
source URL, author, and license (e.g. freesound.org CC0 / CC-BY).
