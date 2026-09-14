from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path
import edge_tts

DEFAULT_VOICE = "en-US-ChristopherNeural"
FEMALE_VOICE = "en-US-JennyNeural"


async def generate_audio_file(script: str, output_path: str, voice: str = DEFAULT_VOICE, mode: str = "solo") -> str:
    """Generate high-fidelity neural MP3 audio using Edge-TTS."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # Clean markdown formatting or bracket notes from speech script
    clean_text = re.sub(r"\[.*?\]", "", script)
    clean_text = re.sub(r"[*_#`>]", "", clean_text)
    clean_text = re.sub(r"\n\s*\n", "\n", clean_text).strip()

    if not clean_text:
        clean_text = "This research session has concluded with no additional verbal notes."

    if mode == "podcast" and ("Host:" in clean_text or "Researcher:" in clean_text):
        # Multi-speaker podcast mode
        chunks = []
        for line in clean_text.split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith("Host:"):
                chunks.append((FEMALE_VOICE, line.replace("Host:", "").strip()))
            elif line.startswith("Researcher:"):
                chunks.append((DEFAULT_VOICE, line.replace("Researcher:", "").strip()))
            else:
                chunks.append((voice, line))

        # Write each chunk to temp files then concatenate
        tmp_files = []
        try:
            for idx, (v, text) in enumerate(chunks[:20]):
                if not text:
                    continue
                tmp_file = f"{output_path}.tmp_{idx}.mp3"
                comm = edge_tts.Communicate(text, v, rate="+5%")
                await comm.save(tmp_file)
                tmp_files.append(tmp_file)

            with open(output_path, "wb") as outfile:
                for tmp_file in tmp_files:
                    if os.path.exists(tmp_file):
                        with open(tmp_file, "rb") as infile:
                            outfile.write(infile.read())
                        try:
                            os.remove(tmp_file)
                        except Exception:
                            pass
        except Exception:
            # Fallback to single pass
            comm = edge_tts.Communicate(clean_text, voice, rate="+5%")
            await comm.save(output_path)
    else:
        comm = edge_tts.Communicate(clean_text, voice, rate="+5%")
        await comm.save(output_path)

    return output_path
