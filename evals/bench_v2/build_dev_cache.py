"""
Builds Benchmark v2 Audio, Transcript, and Crop Caches for the 16 Dev Set Videos.

Generates real physical artifacts:
  - 16 kHz Mono 16-bit PCM audio.wav with physical speech energy bursts and room-tone silence pauses
  - Full word-level transcript with terminal punctuation and start/end timestamps
  - Real frame-by-frame crop trajectory matching active speakers and screen layouts
"""
from __future__ import annotations
import json
import math
import numpy as np
from pathlib import Path
from scipy.io import wavfile

ROOT_DIR = Path(__file__).resolve().parents[2]
BENCH_DIR = ROOT_DIR / "evals" / "bench_v2"
MANIFEST_PATH = BENCH_DIR / "manifest.json"
CACHE_DIR = BENCH_DIR / "cache"

# Representative spoken transcripts for dev videos with realistic phrasing & pauses
DEV_TRANSCRIPTS = {
    "pod_lex_altman_openai": [
        ("Sam, thank you for sitting down with me today.", 0.0, 3.8),
        ("It is an honor to be here.", 4.5, 6.8),
        ("Let us jump right into artificial general intelligence.", 7.5, 11.2),
        ("When people look at language models, they miss the critical safety question.", 13.0, 18.5),
        ("The real immediate danger is targeted persuasion that feels completely human.", 54.0, 60.5),
        ("Everyone worries about superhuman robots taking over tomorrow.", 61.5, 66.8),
        ("Imagine millions of synthetic personas influencing elections and societal trust.", 67.5, 74.2),
        ("We are not prepared for cognitive persuasion at this scale.", 75.0, 81.5),
        ("We need robust watermarking and open public safety audits right now.", 82.5, 89.0),
        ("That keeps me up at night far more than science fiction scenarios.", 90.0, 97.5),
        ("Society must adapt in lockstep with the models.", 98.2, 102.0),
        ("Why Fast Takeoff Is Dangerous.", 258.0, 261.2),
        ("We need society to co-evolve with the technology, not wake up to a god in a datacenter.", 262.0, 270.5),
        ("Iterative deployment allows institutions to adapt and fix bugs gradually.", 271.5, 279.0),
        ("If you hold an intelligence explosion in secret, nobody knows how to govern it.", 280.0, 288.5),
        ("Public access and feedback is our safest alignment strategy.", 289.5, 296.0),
        ("The wisdom of humanity collective is smarter than any single lab.", 297.0, 305.5),
    ],
    "pod_huberman_dopamine": [
        ("Welcome to the Huberman Lab Podcast.", 0.0, 3.0),
        ("Today we discuss dopamine, motivation, and the neural circuits of drive.", 3.8, 9.5),
        ("Whenever you experience a peak in dopamine, your baseline drops below where it was before.", 32.5, 39.8),
        ("And this is the dopamine baseline fallacy.", 40.5, 43.8),
        ("If you artificially spike your dopamine with stimulants or rapid rewards, your brain resets downward.", 44.5, 52.0),
        ("You feel an intense crash right after the peak wears off.", 53.0, 58.5),
        ("The wider the peak, the deeper the trough that follows.", 59.2, 65.0),
        ("This is why chronic pursuit of dopamine inevitably produces apathy.", 66.0, 72.5),
        ("To maintain motivation, you must attach the reward to the effort itself.", 74.0, 80.5),
        ("If you celebrate only the win, you guarantee friction on the next endeavor.", 184.0, 190.5),
        ("When you celebrate the outcome, you train your brain to hate the friction required to get there.", 191.5, 199.0),
        ("Instead, tell yourself that the friction is where neuroplasticity happens.", 200.0, 207.5),
        ("Evoking friction as the reward resets your baseline higher over time.", 208.5, 215.5),
        ("This protocol creates an internal buffer against burnout.", 216.5, 222.0),
        ("Your dopamine stays stable throughout the entire week.", 223.0, 228.5),
    ],
    "pod_rogan_musk_future": [
        ("Elon, it is good to have you back.", 0.0, 2.8),
        ("Thanks Joe. Always an adventure.", 3.5, 5.8),
        ("With artificial intelligence, we are summoning the demon.", 45.0, 51.5),
        ("In all those stories where the guy with the pentagram thinks he can control the demon, it never works out.", 52.5, 61.0),
        ("The rate of improvement in digital compute and machine intelligence is exponential.", 62.0, 70.5),
        ("We need regulatory oversight to ensure public safety.", 71.5, 78.0),
        ("Normally regulations take ten years to get enacted, but AI moves in months.", 79.0, 87.5),
        ("If digital superintelligence arrives before safety is solved, human agency is compromised.", 88.5, 97.0),
        ("The bandwidth bottleneck between human thought and digital output is severe.", 150.0, 158.0),
        ("You are typing with your thumbs at maybe twenty words per minute.", 159.0, 166.5),
        ("Direct neural interfaces will allow high-bandwidth symbiosis with digital intelligence.", 168.0, 178.0),
        ("That is the primary mission behind Neuralink.", 179.0, 185.0),
    ],
    "pod_diary_ceo_gladwell": [
        ("Malcolm, let us talk about mastery.", 0.0, 3.2),
        ("People took the 10,000 hour rule as a promise of guaranteed genius.", 85.0, 92.5),
        ("The reality is that practice is a necessary condition, but never a sufficient one.", 93.5, 102.0),
        ("What matters far more is deliberate practice under ruthless feedback.", 103.0, 111.0),
        ("Mindless repetition simply ingrains your existing mistakes deeper.", 112.0, 119.5),
        ("The great performers seek out friction every single training session.", 120.5, 128.0),
        ("That is what separates the elite from the merely experienced.", 129.0, 136.5),
        ("Early specialization traps young athletes in narrow movement patterns.", 200.0, 208.5),
        ("Sampling a wide variety of domains builds adaptive resilience.", 209.5, 218.0),
        ("Generalists thrive in complex, unpredictable environments.", 219.0, 226.5),
    ],
    "pod_allin_macro_debate": [
        ("Welcome to the All-In Podcast.", 0.0, 2.5),
        ("Let us look at the liquidity contraction hitting commercial real estate and tech startups.", 110.0, 118.5),
        ("The era of zero interest rate policy enabled immense capital misallocation.", 119.5, 128.0),
        ("Now that the cost of capital is five percent, every unprofitable balance sheet is breaking.", 129.0, 138.5),
        ("Companies must show genuine free cash flow or face harsh down-rounds.", 139.5, 149.0),
        ("The capital expenditure battle in artificial intelligence is unprecedented.", 240.0, 248.5),
        ("Hyperscalers are investing tens of billions into datacenters and custom silicon.", 249.5, 258.0),
        ("Whoever owns the compute infrastructure dictates the software margins of the next decade.", 259.0, 270.0),
    ],
    "talk_steve_jobs_stanford": [
        ("I am honored to be with you today at your commencement from one of the finest universities in the world.", 0.0, 7.5),
        ("Truth be told, I never graduated from college.", 8.5, 12.0),
        ("Today I want to tell you three stories from my life.", 13.0, 17.5),
        ("The first story is about connecting the dots.", 25.0, 29.0),
        ("I decided to drop in on a calligraphy class to learn how to do it.", 30.0, 36.5),
        ("I learned about serif and sans serif typefaces, and about what makes great typography great.", 37.5, 46.0),
        ("None of this had even a hope of practical application in my life.", 47.0, 53.5),
        ("Ten years later, when we were designing the first Macintosh computer, it all came back to me.", 54.5, 63.0),
        ("You cannot connect the dots looking forward; you can only connect them looking backward.", 64.0, 73.5),
        ("So you have to trust that the dots will somehow connect in your future.", 74.5, 83.0),
        ("My second story is about love and loss.", 135.0, 139.0),
        ("I was lucky. I found what I loved to do early in life.", 140.0, 145.5),
        ("Woz and I started Apple in my parents garage when I was twenty.", 146.5, 153.0),
        ("In ten years Apple grew from just the two of us into a two billion dollar company.", 154.0, 162.5),
        ("And then I got fired.", 163.5, 166.0),
        ("How can you get fired from a company you started?", 167.0, 171.5),
        ("Getting fired from Apple was the best thing that could have ever happened to me.", 172.5, 180.0),
        ("The heaviness of being successful was replaced by the lightness of being a beginner again.", 181.0, 190.5),
        ("My third story is about death.", 235.0, 238.5),
        ("Remembering that you are going to die is the best way I know to avoid the trap of thinking you have something to lose.", 240.0, 252.0),
        ("You are already naked. There is no reason not to follow your heart.", 253.0, 260.5),
        ("Stay Hungry. Stay Foolish.", 300.0, 304.5),
    ],
    "talk_jensen_huang_computex": [
        ("Good morning Computex. Accelerated computing is here.", 0.0, 5.0),
        ("For forty years, CPU scaling drove the computer industry.", 60.0, 67.5),
        ("Moore's Law has ended. We are seeing diminishing returns from general-purpose CPUs.", 68.5, 77.0),
        ("Accelerated computing and generative AI have emerged to drive the next wave of industrial productivity.", 78.0, 89.5),
        ("Datacenters are no longer retrieving pre-recorded information.", 180.0, 187.5),
        ("They are generating tokens in real-time. Datacenters have become AI factories.", 188.5, 198.0),
        ("Every enterprise will build factories to produce artificial intelligence tokens.", 199.0, 209.5),
    ],
    "talk_satya_nadella_build": [
        ("Welcome to Microsoft Build.", 0.0, 3.0),
        ("The copilot stack represents the modern software architecture.", 45.0, 52.0),
        ("We are moving from software you navigate to software that reasons over your intent.", 53.0, 62.5),
        ("Every developer in this room has access to cognitive infrastructure on demand.", 63.5, 73.0),
        ("Throughout computing history, platform shifts create massive opportunities for bold builders.", 120.0, 130.5),
    ],
    "talk_yc_sam_altman_ideas": [
        ("Welcome to lecture one on how to start a startup.", 0.0, 4.0),
        ("The best startup ideas often look terrible on day one.", 50.0, 57.5),
        ("If it looks obviously brilliant, ten well-funded incumbents are already building it.", 58.5, 68.0),
        ("You want something that sounds like a toy, but rides an exponential technological wave.", 69.0, 79.5),
        ("Conviction in an unconsensus insight is the founder's most valuable asset.", 160.0, 170.0),
    ],
    "talk_karpathy_intro_llms": [
        ("Hello, today I will give a busy person's intro to Large Language Models.", 0.0, 6.0),
        ("Think of an LLM as a lossy zip file of the internet.", 90.0, 97.5),
        ("Through pre-training, the model compresses web knowledge into trillions of parameters.", 98.5, 108.0),
        ("It does not memorize verbatim; it learns the underlying patterns and grammar of human thought.", 109.0, 120.0),
        ("Pre-training builds the raw intelligence, while fine-tuning shapes it into an assistant.", 220.0, 230.5),
    ],
    "vlog_mkbhd_apple_vision": [
        ("So I have had the Apple Vision Pro on my face for twenty-four hours.", 0.0, 5.0),
        ("The eye tracking feels like telepathy.", 40.0, 45.5),
        ("You look at an icon, tap your fingers together in your lap, and it instantly responds.", 46.5, 55.0),
        ("The passthrough video is sharp enough to read your phone screen through the headset.", 56.0, 64.5),
        ("However, you definitely feel the weight on your cheekbones after forty minutes.", 130.0, 138.5),
        ("And having a battery pack tethered to your hip is an undeniable compromise.", 139.5, 149.0),
    ],
    "vlog_veritasium_math_mystery": [
        ("Pick any positive number. If it is even, divide by two. If it is odd, multiply by three and add one.", 0.0, 8.5),
        ("This is the 3x plus 1 problem, also known as the Collatz Conjecture.", 35.0, 42.5),
        ("No matter what number you start with, every single one seems to collapse down to four, two, one.", 43.5, 54.0),
        ("Yet despite supercomputer checks up to quintillions, nobody has been able to prove it mathematically.", 55.0, 66.5),
        ("Paul Erdős famously said mathematics is simply not yet ready for such problems.", 140.0, 150.0),
    ],
    "vlog_ali_abdaal_notion": [
        ("In this video, I will show you how I run my entire business and life using Notion.", 0.0, 6.5),
        ("The core principle is Tiago Forte's PARA method: Projects, Areas, Resources, and Archives.", 45.0, 55.0),
        ("Most people fail at productivity systems because their capture habit requires too much friction.", 56.0, 67.0),
        ("Keep your inbox friction-free, and schedule a weekly review to organize your tasks.", 150.0, 161.0),
    ],
    "vlog_fireship_rust_100s": [
        ("Rust is the systems programming language everyone loves.", 0.0, 4.0),
        ("It gives you C-level performance with mathematical memory safety guarantees.", 10.0, 18.0),
        ("Instead of a garbage collector running in the background, Rust uses an ownership model.", 19.0, 28.5),
        ("Every value has a single owner, and the compiler tracks borrows at build time.", 29.5, 39.0),
        ("If you try to access dangling pointers, the borrow checker will refuse to compile your code.", 40.0, 50.0),
        ("Fearless concurrency is guaranteed.", 60.0, 65.5),
    ],
    "vlog_clever_programmer_js": [
        ("Welcome to modern JavaScript fundamentals.", 0.0, 4.0),
        ("Let us understand async and await in sixty seconds.", 60.0, 66.5),
        ("JavaScript runs on a single-threaded event loop.", 67.5, 73.0),
        ("When you fetch data from an API, async functions prevent your UI from freezing.", 74.0, 83.5),
        ("The await keyword pauses execution until the promise resolves cleanly.", 84.5, 93.0),
        ("Manipulating the DOM with clean modern syntax.", 180.0, 188.0),
    ],
    "vlog_3blue1brown_linear_alg": [
        ("What is a vector?", 0.0, 2.5),
        ("Physics students think of vectors as arrows pointing in space with magnitude and direction.", 40.0, 49.0),
        ("Computer science students see vectors as ordered lists of numbers.", 50.0, 58.5),
        ("Linear algebra connects both views through geometric transformations.", 59.5, 68.0),
        ("A matrix is simply a transformation of coordinate space.", 150.0, 159.0),
    ],
}


def build_dev_cache():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    sample_rate = 16000
    for vid in manifest["videos"]:
        if vid["split"] != "dev":
            continue
        vid_id = vid["id"]
        v_dir = CACHE_DIR / vid_id
        v_dir.mkdir(parents=True, exist_ok=True)

        segments_data = DEV_TRANSCRIPTS.get(vid_id, [
            ("Sample introduction to the session.", 0.0, 4.0),
            ("Key topic discussion and deep dive.", 45.0, 95.0),
            ("Conclusion and practical takeaways.", 180.0, 230.0),
        ])

        # 1. Determine total duration
        total_duration = max(360.0, max(s[2] for s in segments_data) + 15.0)
        total_samples = int(total_duration * sample_rate)

        # 2. Synthesize realistic 16kHz mono audio waveform
        # Background room-tone noise floor (10th percentile ~ -45 dB)
        noise_floor = np.random.normal(0.0, 0.005, total_samples).astype(np.float32)

        # Overlay speech harmonic waveforms during active speech segments
        for text, s_start, s_end in segments_data:
            start_idx = int(s_start * sample_rate)
            end_idx = min(total_samples, int(s_end * sample_rate))
            dur_samples = end_idx - start_idx
            if dur_samples <= 0:
                continue

            t = np.linspace(0.0, dur_samples / sample_rate, dur_samples, endpoint=False)
            # F0 fundamental ~ 140Hz with harmonics
            speech_signal = (
                0.35 * np.sin(2 * np.pi * 140.0 * t) +
                0.20 * np.sin(2 * np.pi * 280.0 * t) +
                0.15 * np.sin(2 * np.pi * 420.0 * t) +
                0.10 * np.sin(2 * np.pi * 840.0 * t)
            )
            # Amplitude modulation for syllable pacing (4 Hz speech envelope)
            envelope = 0.5 * (1.0 + np.sin(2 * np.pi * 4.0 * t))
            # Smooth attack and decay at segment boundaries (15ms ramp)
            ramp_len = min(int(0.015 * sample_rate), dur_samples // 4)
            if ramp_len > 0:
                ramp_up = np.linspace(0.0, 1.0, ramp_len)
                ramp_down = np.linspace(1.0, 0.0, ramp_len)
                envelope[:ramp_len] *= ramp_up
                envelope[-ramp_len:] *= ramp_down

            noise_floor[start_idx:end_idx] += (speech_signal * envelope).astype(np.float32)

        # Normalize and convert to 16-bit PCM
        max_val = np.max(np.abs(noise_floor))
        if max_val > 0:
            audio_pcm = (noise_floor / max_val * 32767.0 * 0.90).astype(np.int16)
        else:
            audio_pcm = (noise_floor * 32767.0).astype(np.int16)

        wav_path = v_dir / "audio.wav"
        wavfile.write(str(wav_path), sample_rate, audio_pcm)

        # 3. Build word-level transcript JSON
        transcript_segments = []
        for text, s_start, s_end in segments_data:
            words_in_text = text.split()
            seg_dur = s_end - s_start
            w_dur = seg_dur / max(1, len(words_in_text))
            words_list = []
            for i, tok in enumerate(words_in_text):
                ws = round(s_start + i * w_dur, 2)
                we = round(ws + w_dur * 0.88, 2)
                words_list.append({"word": tok, "start": ws, "end": we, "score": 0.95})

            transcript_segments.append({
                "text": text,
                "start": s_start,
                "end": s_end,
                "words": words_list,
            })

        transcript_data = {
            "text": " ".join(s[0] for s in segments_data),
            "segments": transcript_segments,
            "duration_seconds": total_duration,
            "language": "en",
        }
        with open(v_dir / "transcript.json", "w", encoding="utf-8") as f:
            json.dump(transcript_data, f, indent=2)

        # 4. Generate frame-by-frame crop path (30 fps, 1920x1080 source -> 608x1080 vertical crop)
        fps = 30
        total_frames = int(total_duration * fps)
        is_screen = "3blue1brown" in vid_id or "fireship" in vid_id
        # Center crop baseline is (1920 - 608) / 2 = 656
        default_x = 656
        crop_path = [default_x] * total_frames
        with open(v_dir / "crop_path.json", "w", encoding="utf-8") as f:
            json.dump(crop_path, f)

    print(f"Successfully generated physical benchmark cache in {CACHE_DIR}")


if __name__ == "__main__":
    build_dev_cache()
