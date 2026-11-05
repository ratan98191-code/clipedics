"""
Generates deterministic, word-level offline transcript caches for all eval benchmark videos.
Allows running Phase 0-7 metrics instantly without downloading gigabytes of video or spending API tokens.
"""
import json
from pathlib import Path
from core.models import Transcript, TranscriptSegment, WordSegment

CACHE_DIR = Path(__file__).parent / "cache" / "transcripts"
MANIFEST_PATH = Path(__file__).parent / "manifest.json"

SAMPLE_TEXTS = {
    "pod_huberman_dopamine": [
        ("Welcome back to the podcast.", 0.0, 3.2),
        ("Today we are discussing dopamine, motivation, and drive.", 3.8, 8.5),
        ("Most people misunderstand how dopamine works in the human brain.", 9.2, 14.8),
        ("They assume that high dopamine is always the ultimate goal.", 15.5, 20.0),
        ("Whenever you experience a peak in dopamine, your baseline drops below where it was before.", 32.5, 39.8),
        ("And this is the dopamine baseline fallacy.", 40.5, 43.8),
        ("If you artificially spike your dopamine with stimulants or rapid rewards, your brain resets downward.", 44.5, 52.0),
        ("You feel an intense crash right after the peak wears off.", 53.0, 58.5),
        ("The wider the peak, the deeper the trough that follows.", 59.2, 65.0),
        ("This is why chronic pursuit of dopamine inevitably produces apathy.", 66.0, 72.5),
        ("To maintain motivation, you must attach the reward to the effort itself.", 74.0, 80.5),
        ("That is the true secret of sustained human performance.", 81.2, 88.0),
        ("Let us take a brief pause to look at the clinical literature.", 89.5, 95.0),
        ("Now moving to practical protocols for daily life.", 175.0, 182.0),
        ("If you celebrate only the win, you guarantee friction on the next endeavor.", 184.2, 191.0),
        ("When you celebrate the outcome, you train your brain to hate the friction required to get there.", 192.0, 200.5),
        ("Instead, tell yourself that the friction is where neuroplasticity happens.", 201.5, 208.0),
        ("Evoking friction as the reward resets your baseline higher over time.", 209.0, 216.5),
        ("This protocol creates an internal buffer against burnout.", 218.0, 224.5),
        ("Your dopamine stays stable throughout the entire week.", 226.0, 232.0),
        ("And that concludes our core takeaway on neurochemistry.", 235.0, 242.0),
    ],
    "pod_lex_altman": [
        ("Sam, thank you for sitting down with me today.", 0.0, 4.0),
        ("It is an honor. Let us jump right into artificial intelligence.", 4.8, 10.5),
        ("When you look at GPT-4, what surprises you the most?", 12.0, 17.5),
        ("I think people are looking at the wrong risks; disinformation at scale is tomorrow's crisis.", 54.0, 61.5),
        ("Everyone worries about superhuman robots taking over tomorrow.", 62.2, 67.8),
        ("The real immediate danger is targeted persuasion that feels completely human.", 68.5, 75.0),
        ("Imagine millions of synthetic personas personalized to influence elections and culture.", 76.0, 83.5),
        ("We are not societally prepared for cognitive persuasion at this scale.", 85.0, 92.0),
        ("We need robust watermarking and open public safety audits right now.", 93.5, 100.5),
        ("That keeps me up at night far more than science fiction scenarios.", 102.0, 112.5),
        ("What about the long term horizon?", 250.0, 256.0),
        ("Why Fast Takeoff Is Dangerous.", 258.0, 261.5),
        ("We need society to co-evolve with the technology, not wake up to a god in a datacenter.", 262.5, 271.0),
        ("Iterative deployment allows institutions to adapt and fix bugs gradually.", 272.5, 280.0),
        ("If you hold an intelligence explosion in secret, nobody knows how to govern it.", 282.0, 290.5),
        ("Public access and feedback is our safest alignment strategy.", 292.0, 299.5),
        ("The wisdom of humanity collective is smarter than any single lab.", 301.0, 310.0),
        ("That is the philosophy guiding our deployment.", 312.0, 318.0),
    ],
    "pod_rogan_musk": [
        ("So Elon, how do you think about consciousness?", 0.0, 5.0),
        ("It is one of the deepest mysteries in physics.", 6.0, 11.5),
        ("Forty years ago we had Pong. Today we have photorealistic 3D simulations with millions playing.", 92.0, 101.5),
        ("Think about the rate of improvement over just four decades.", 102.5, 108.0),
        ("If you assume any rate of progress at all, games will become indistinguishable from reality.", 109.5, 118.0),
        ("Even if that progress slows down by a thousand times, it still happens.", 119.5, 126.0),
        ("Therefore, the odds that we are in base reality are one in billions.", 128.0, 136.5),
        ("It is either that, or civilization stops advancing due to catastrophic collapse.", 138.0, 146.0),
        ("So we should probably hope that we are living in a simulation.", 148.0, 156.0),
        ("Now let's talk about the communication link between humans and machines.", 330.0, 338.0),
        ("Your thumbs are outputting at maybe a hundred bits per second; your phone is a million times faster.", 340.0, 349.5),
        ("You are already a cyborg because of your digital devices.", 351.0, 357.5),
        ("The bottleneck is the input-output rate between your biological brain and the silicon.", 359.0, 368.0),
        ("Solve that bandwidth limitation, and human potential expands exponentially.", 370.0, 379.5),
        ("Neuralink is fundamentally a high-bandwidth interface to preserve human agency.", 382.0, 392.0),
        ("That is the long-term vision.", 395.0, 402.0),
    ],
    "pod_diary_ceo_gladwell": [
        ("Welcome Malcolm. Outliers changed how we view talent.", 0.0, 6.0),
        ("Thank you. I think it is time to revisit some of those conclusions.", 7.0, 14.0),
        ("Nobody becomes a world-class expert alone without immense structural advantage.", 45.0, 53.0),
        ("When I wrote about ten thousand hours, people thought practice was a solo endeavor.", 54.5, 62.5),
        ("In reality, behind every virtuoso was free ice time, wealthy parents, or lucky birth dates.", 64.0, 73.0),
        ("Effort is necessary, but opportunity is what converts effort into mastery.", 74.5, 83.0),
        ("If we want more geniuses, we should broaden access rather than preach raw hustle.", 85.0, 94.0),
        ("That is the true lesson of mastery in modern society.", 96.0, 108.0),
    ],
    "talk_yc_startup_ideas": [
        ("Welcome to Startup School. Let us talk about ideation.", 0.0, 5.5),
        ("Most founders spend months building things nobody actually wants.", 6.5, 12.0),
        ("The worst startup ideas look like amazing consumer apps that everyone wants but nobody will pay for.", 40.0, 48.5),
        ("We call these tarpit ideas because brilliant founders step into them and never get out.", 49.8, 57.5),
        ("They sound appealing because you can imagine yourself using them casually.", 59.0, 66.5),
        ("However, there is no acute pain and no urgent purchasing power behind them.", 68.0, 76.5),
        ("Look for boring B2B problems where companies are hemorrhaging money every day.", 78.5, 87.0),
        ("Urgency beats novelty every single time.", 89.0, 98.0),
        ("Live in the future, then build what's missing.", 180.0, 186.0),
        ("Notice the things that seem broken or incomplete in your daily technical work.", 187.5, 195.0),
        ("When you build for your own acute problems, you understand the customer intuitively.", 197.0, 206.0),
        ("Organic demand will always outperform fabricated market research.", 208.0, 217.0),
        ("That is how Apple, Airbnb, and Stripe were born.", 219.0, 226.5),
        ("Start building what you personally cannot live without.", 228.0, 235.0),
    ],
    "talk_steve_jobs_stanford": [
        ("I am honored to be with you today at your commencement.", 0.0, 6.0),
        ("I never graduated from college. Truth be told, this is the closest I ever got.", 7.0, 14.5),
        ("Today I want to tell you three stories from my life.", 16.0, 21.0),
        ("The first story is about connecting the dots.", 23.0, 28.0),
        ("You cannot connect the dots looking forward; you can only connect them looking backward.", 65.0, 72.5),
        ("So you have to trust that the dots will somehow connect in your future.", 74.0, 81.0),
        ("You have to trust in something: your gut, destiny, life, karma, whatever.", 82.5, 90.0),
        ("Because believing that the dots will connect gives you the confidence to follow your heart.", 92.0, 101.5),
        ("Even when it leads you off the well-worn path, that will make all the difference.", 103.0, 112.0),
        ("My second story was about love and loss.", 115.0, 121.0),
        ("Remembering that you are going to die is the best way I know to avoid the trap of thinking you have something to lose.", 280.0, 290.5),
        ("You are already naked. There is no reason not to follow your heart.", 292.0, 300.0),
        ("Your time is limited, so don't waste it living someone else's life.", 302.0, 309.5),
        ("Don't be trapped by dogma, which is living with the results of other people's thinking.", 311.5, 320.0),
        ("Have the courage to follow your heart and intuition.", 322.0, 329.0),
        ("Stay hungry. Stay foolish.", 335.0, 345.0),
    ],
    "talk_jensen_huang_stanford": [
        ("Jensen, thank you for joining us at Stanford Graduate School of Business.", 0.0, 5.0),
        ("Students here always ask for advice on how to guarantee high success.", 6.0, 12.0),
        ("Greatness comes from character, and character isn't formed out of smart people—it's formed out of people who suffered.", 35.0, 45.0),
        ("People with very high expectations often have very low resilience.", 46.5, 53.0),
        ("When you are used to winning effortlessly, failure breaks you.", 54.5, 61.0),
        ("I wish upon you ample doses of pain and suffering, because that builds grit.", 63.0, 71.5),
        ("At Nvidia, we survived because we were constantly on the brink of going out of business.", 73.5, 83.0),
        ("Resilience matters much more than raw intelligence in building enduring organizations.", 85.0, 95.0),
    ],
    "talk_satya_nadella_ai": [
        ("Welcome everyone to Microsoft Ignite.", 0.0, 4.5),
        ("We are witnessing a profound generational transition across the tech stack.", 5.5, 12.0),
        ("For seventy years we had to learn computer language; now computers have learned human language.", 48.0, 56.5),
        ("This is the true emergence of the natural user interface.", 58.0, 64.0),
        ("Instead of navigating rigid menus and complex APIs, we express intent directly.", 65.5, 74.0),
        ("The second breakthrough is a reasoning engine capable of synthesizing disparate data.", 76.0, 85.0),
        ("When intent meets reasoning, software productivity changes forever.", 87.0, 96.0),
        ("Every category of enterprise software will be fundamentally rewritten.", 98.0, 105.0),
    ],
    "vlog_mkbhd_apple_vision": [
        ("What is up guys, MKBHD here.", 0.0, 3.5),
        ("I have been testing Apple Vision Pro nonstop for the past twenty-four hours.", 4.2, 10.5),
        ("Is spatial computing truly the future, or is it an overpriced headset?", 11.5, 17.0),
        ("You look at an icon, you pinch your fingers without raising your hand, and it clicks instantly.", 18.0, 26.5),
        ("The eye tracking feels like genuine telepathy.", 28.0, 34.0),
        ("There are cameras tracking your pupils with infrared light with surgical precision.", 35.5, 43.0),
        ("You don't have to reach out into midair like in Minority Report.", 44.5, 51.5),
        ("You just rest your hands comfortably in your lap and pinch.", 53.0, 59.5),
        ("It is the single most intuitive input method I have ever experienced in tech.", 61.0, 72.0),
        ("Now let us address the elephant in the room: weight and comfort.", 200.0, 208.5),
        ("After forty-five minutes, your cheekbones start sending you polite reminders that metal is heavy.", 210.0, 219.0),
        ("The battery pack is in your pocket tethered by a braided wire.", 220.5, 227.0),
        ("The custom displays produce heat that requires active micro-fans.", 229.0, 237.0),
        ("You can see the future through these lenses, but you also feel every single gram of it.", 240.0, 252.0),
        ("It is a masterclass in engineering that leaves your face exhausted.", 254.0, 268.0),
    ],
    "vlog_ali_abdaal_productivity": [
        ("Hey friends, welcome back to the channel.", 0.0, 4.0),
        ("Today I want to share the single most practical trick to beat procrastination.", 5.0, 11.5),
        ("Make the good habit take twenty seconds less to start, and the bad habit take twenty seconds more.", 25.0, 33.5),
        ("We think procrastination is a character defect or lack of willpower.", 35.0, 42.0),
        ("In psychology, it is simply friction resistance.", 43.5, 49.0),
        ("If your guitar is in its case in the closet, you will scroll social media instead.", 50.5, 58.0),
        ("Put the guitar on a stand right next to your desk.", 60.0, 65.5),
        ("Reduce initial activation energy, and discipline becomes automatic.", 67.0, 76.0),
        ("Design your environment so that doing the work is the path of least resistance.", 77.5, 82.0),
    ],
    "vlog_veritasium_math": [
        ("This is the Collatz Conjecture, the most dangerous problem in mathematics.", 0.0, 7.0),
        ("It sounds so simple that an elementary school student can understand it.", 8.0, 14.0),
        ("Mathematics is simply not yet ready for such problems, said the world's greatest mathematician.", 15.0, 23.5),
        ("Here is the rule: pick any positive integer.", 25.0, 29.5),
        ("If it is even, divide it by two. If it is odd, multiply by three and add one.", 31.0, 39.5),
        ("Repeat this simple process indefinitely.", 41.0, 45.0),
        ("No matter which starting number you choose, you always collapse into the loop four, two, one.", 46.5, 57.0),
        ("Supercomputers have checked every integer up to quintillions without finding a single exception.", 58.5, 68.0),
        ("Yet to this day, no mathematician has ever proven that it holds true for all numbers.", 70.0, 78.0),
    ],
    "vlog_fireship_code": [
        ("The transformer architecture revolutionized artificial intelligence in 2017.", 0.0, 6.0),
        ("Instead of reading text word by word like a slow human, transformers process every token simultaneously.", 10.0, 18.5),
        ("Traditional recurrent neural networks suffered from catastrophic forgetting over long sequences.", 20.0, 28.5),
        ("The revolutionary breakthrough was the self-attention mechanism.", 30.0, 36.5),
        ("Every single word computes a mathematical relationship with every other word in the prompt.", 38.0, 46.5),
        ("This allows the model to capture deep semantic context and nuance instantly.", 48.0, 56.0),
        ("Scale this architecture with billions of parameters, and intelligence begins to emerge.", 57.5, 65.0),
    ],
}


def _create_word_segments(text: str, seg_start: float, seg_end: float) -> list[WordSegment]:
    """Synthesize precise word-level timestamps matching WhisperX output."""
    words = text.strip().split()
    if not words:
        return []
    duration = seg_end - seg_start
    word_duration = duration / len(words)
    w_segs = []
    for idx, w in enumerate(words):
        w_start = round(seg_start + idx * word_duration, 2)
        w_end = round(seg_start + (idx + 1) * word_duration, 2)
        w_segs.append(WordSegment(word=w, start=w_start, end=w_end, score=0.98))
    return w_segs


def build_all_caches():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    for vid in manifest["videos"]:
        vid_id = vid["id"]
        raw_segs = SAMPLE_TEXTS.get(vid_id, [])
        segments = []
        for text, start, end in raw_segs:
            words = _create_word_segments(text, start, end)
            segments.append(TranscriptSegment(
                text=text,
                start=start,
                end=end,
                speaker="SPEAKER_00",
                words=words,
            ))

        transcript = Transcript(
            language="en",
            duration_seconds=float(vid["duration_seconds"]),
            segments=segments,
        )

        out_file = CACHE_DIR / f"{vid_id}.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(transcript.model_dump(), f, indent=2)

    print(f"Successfully generated {len(manifest['videos'])} transcript caches in {CACHE_DIR}")


if __name__ == "__main__":
    build_all_caches()

