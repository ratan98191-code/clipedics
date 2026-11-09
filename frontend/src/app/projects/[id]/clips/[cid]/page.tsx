// Clipedics – Single clip editor (player + metadata + trim/swap editor + feedback)
"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { ViralityBadge } from "@/components/ViralityBadge";
import { fmtDuration, copyText } from "@/lib/utils";
import type { Clip } from "@/lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface BeatItem {
  id: number;
  role: string;
  name: string;
}

export default function ClipPage() {
  const { id: projectId, cid: clipId } = useParams<{ id: string; cid: string }>();
  const [clip, setClip] = useState<Clip | null>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [caption, setCaption] = useState("");
  const [title, setTitle] = useState("");
  const [copied, setCopied] = useState(false);
  const [saving, setSaving] = useState(false);

  // Editor states (Phase 7)
  const [trimStart, setTrimStart] = useState<number>(0);
  const [trimEnd, setTrimEnd] = useState<number>(0);
  const [trimming, setTrimming] = useState(false);
  const [feedbackAction, setFeedbackAction] = useState<string | null>(null);
  const [userRating, setUserRating] = useState<number>(0);
  const [subStyle, setSubStyle] = useState("hormozi");
  const [layoutMode, setLayoutMode] = useState("center_crop");
  const [rerendering, setRerendering] = useState(false);

  // Default beats representation
  const [beats, setBeats] = useState<BeatItem[]>([
    { id: 1, role: "hook", name: "Opening Hook (3-5s)" },
    { id: 2, role: "build", name: "Narrative Build" },
    { id: 3, role: "peak", name: "Climax / Peak Insight" },
    { id: 4, role: "cliffhanger", name: "Cliffhanger / Takeaway" },
  ]);

  useEffect(() => {
    api.clips.get(clipId).then((c) => {
      setClip(c);
      setCaption(c.suggested_caption);
      setTitle(c.title);
      setTrimStart(c.start_seconds);
      setTrimEnd(c.end_seconds);
      setLoading(false);
    });
  }, [clipId]);

  const handleSave = async () => {
    if (!clip) return;
    setSaving(true);
    const updated = await api.clips.update(clip.id, { title, suggested_caption: caption });
    setClip(updated);
    setEditing(false);
    setSaving(false);
  };

  const handleCopy = async () => {
    if (!clip) return;
    await copyText(`${clip.suggested_caption}\n\n${clip.hashtags.map(h => `#${h.replace(/^#/, "")}`).join(" ")}`);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Phase 7: Trim handler
  const handleApplyTrim = async () => {
    if (!clip || trimStart >= trimEnd) return;
    setTrimming(true);
    try {
      const updated = await api.clips.trim(clip.id, trimStart, trimEnd);
      setClip(updated);
      setFeedbackAction("Trim saved & re-rendered!");
      setTimeout(() => setFeedbackAction(null), 3000);
    } finally {
      setTrimming(false);
    }
  };

  // Phase 7: Swap beats handler
  const moveBeat = (index: number, direction: "up" | "down") => {
    const newIdx = direction === "up" ? index - 1 : index + 1;
    if (newIdx < 0 || newIdx >= beats.length) return;
    const reordered = [...beats];
    const temp = reordered[index];
    reordered[index] = reordered[newIdx];
    reordered[newIdx] = temp;
    setBeats(reordered);
  };

  const handleApplyBeats = async () => {
    if (!clip) return;
    setRerendering(true);
    try {
      const order = beats.map((b) => b.id);
      const updated = await api.clips.swapBeats(clip.id, order);
      setClip(updated);
      setFeedbackAction("Beats reordered & rendered!");
      setTimeout(() => setFeedbackAction(null), 3000);
    } finally {
      setRerendering(false);
    }
  };

  // Phase 7: Feedback logging handler
  const handleFeedback = async (action: string, rating?: number) => {
    if (!clip) return;
    await api.clips.feedback(clip.id, action, rating);
    if (rating) setUserRating(rating);
    setFeedbackAction(`Logged ${action.toUpperCase()}`);
    setTimeout(() => setFeedbackAction(null), 2500);
  };

  // Phase 7: Re-render handler
  const handleRerender = async () => {
    if (!clip) return;
    setRerendering(true);
    try {
      const updated = await api.clips.rerender(clip.id, subStyle, layoutMode);
      setClip(updated);
      setFeedbackAction("Re-render complete!");
      setTimeout(() => setFeedbackAction(null), 3000);
    } finally {
      setRerendering(false);
    }
  };

  if (loading) return (
    <div className="flex items-center justify-center py-32 text-zinc-500">
      <div className="w-6 h-6 border-2 border-zinc-600 border-t-violet-500 rounded-full animate-spin mr-3" />
      Loading clip…
    </div>
  );

  if (!clip) return (
    <div className="text-center py-20 text-red-400">Clip not found.</div>
  );

  const videoSrc = clip.output_mp4_path
    ? `${API_BASE}/output/${clip.output_mp4_path.split(/[/\\]output[/\\]/)[1] ?? clip.output_mp4_path}`
    : "";

  return (
    <div className="space-y-6">
      {/* Back */}
      <div className="flex items-center justify-between">
        <Link href={`/projects/${projectId}`} className="text-xs text-zinc-500 hover:text-zinc-300 transition">
          ← Back to Project
        </Link>
        {feedbackAction && (
          <span className="text-xs text-green-400 bg-green-500/10 border border-green-500/20 px-3 py-1 rounded-full animate-fade-in">
            ✓ {feedbackAction}
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Left: Video player & Editor Controls */}
        <div className="flex flex-col items-center gap-4">
          <div className="w-full max-w-xs aspect-[9/16] bg-zinc-900 rounded-2xl overflow-hidden border border-zinc-800 shadow-xl">
            {videoSrc ? (
              <video
                src={videoSrc}
                controls
                autoPlay
                loop
                className="w-full h-full object-cover"
              />
            ) : (
              <div className="w-full h-full flex items-center justify-center text-5xl opacity-20">🎬</div>
            )}
          </div>

          {/* Action Row: Accept / Reject / Rating */}
          <div className="w-full max-w-xs flex items-center justify-between bg-zinc-900 border border-zinc-800 p-2.5 rounded-xl">
            <button
              onClick={() => handleFeedback("accept")}
              className="px-3 py-1.5 text-xs bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 rounded-lg hover:bg-emerald-500/30 transition"
            >
              👍 Accept
            </button>
            <button
              onClick={() => handleFeedback("reject")}
              className="px-3 py-1.5 text-xs bg-rose-500/20 text-rose-400 border border-rose-500/30 rounded-lg hover:bg-rose-500/30 transition"
            >
              👎 Reject
            </button>
            <div className="flex items-center gap-1">
              {[1, 2, 3, 4, 5].map((star) => (
                <button
                  key={star}
                  onClick={() => handleFeedback("rate", star)}
                  className={`text-xs ${star <= userRating ? "text-amber-400" : "text-zinc-600"} hover:text-amber-300`}
                >
                  ★
                </button>
              ))}
            </div>
          </div>

          {/* Phase 7: Interactive Boundary Trim Panel */}
          <div className="w-full max-w-xs bg-zinc-900 border border-zinc-800 rounded-xl p-4 space-y-3">
            <p className="text-xs font-semibold text-zinc-300">✂️ Boundary Trim Editor</p>
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div>
                <label className="text-zinc-500">Start (s)</label>
                <input
                  type="number"
                  step="0.5"
                  value={trimStart}
                  onChange={(e) => setTrimStart(parseFloat(e.target.value) || 0)}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-white mt-1"
                />
              </div>
              <div>
                <label className="text-zinc-500">End (s)</label>
                <input
                  type="number"
                  step="0.5"
                  value={trimEnd}
                  onChange={(e) => setTrimEnd(parseFloat(e.target.value) || 0)}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-white mt-1"
                />
              </div>
            </div>
            <button
              onClick={handleApplyTrim}
              disabled={trimming}
              className="w-full py-2 bg-violet-600/30 hover:bg-violet-600/50 border border-violet-500/40 text-violet-200 text-xs font-semibold rounded-lg transition"
            >
              {trimming ? "Trimming…" : "Apply Boundary Trim"}
            </button>
          </div>

          {/* Phase 7: Narrative Beat Swap Panel */}
          <div className="w-full max-w-xs bg-zinc-900 border border-zinc-800 rounded-xl p-4 space-y-3">
            <div className="flex items-center justify-between">
              <p className="text-xs font-semibold text-zinc-300">🔀 Narrative Arc Beats</p>
              <button
                onClick={handleApplyBeats}
                disabled={rerendering}
                className="text-[11px] text-violet-400 hover:text-violet-300 underline"
              >
                Re-render Order
              </button>
            </div>
            <div className="space-y-1.5 text-xs">
              {beats.map((b, idx) => (
                <div
                  key={b.id}
                  className="flex items-center justify-between bg-zinc-800/80 px-2.5 py-1.5 rounded-lg border border-zinc-700/50"
                >
                  <span className="text-zinc-300">
                    <span className="text-violet-400 font-bold mr-1.5">B{idx + 1}</span>
                    {b.name}
                  </span>
                  <div className="flex gap-1">
                    <button
                      onClick={() => moveBeat(idx, "up")}
                      disabled={idx === 0}
                      className="px-1 text-zinc-400 hover:text-white disabled:opacity-30"
                    >
                      ▲
                    </button>
                    <button
                      onClick={() => moveBeat(idx, "down")}
                      disabled={idx === beats.length - 1}
                      className="px-1 text-zinc-400 hover:text-white disabled:opacity-30"
                    >
                      ▼
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Download button */}
          <a
            href={api.clips.downloadUrl(clip.id)}
            download
            className="w-full max-w-xs py-3 rounded-xl bg-gradient-to-r from-violet-600 to-fuchsia-600 text-white font-semibold text-center hover:opacity-90 transition text-sm"
          >
            ⬇ Download MP4
          </a>
        </div>

        {/* Right: Metadata & Style Presets */}
        <div className="space-y-5">
          {/* Title */}
          <div className="space-y-1">
            <label className="text-xs text-zinc-500">Title</label>
            {editing ? (
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-violet-500"
              />
            ) : (
              <h1 className="text-xl font-bold text-white leading-snug">{clip.title}</h1>
            )}
          </div>

          {/* Stats row */}
          <div className="flex items-center gap-4 flex-wrap">
            <ViralityBadge score={clip.virality_score} />
            <span className="text-sm text-zinc-400">
              ⏱ {fmtDuration(clip.start_seconds)} – {fmtDuration(clip.end_seconds)}
              <span className="ml-2 text-zinc-600">({fmtDuration(clip.duration_seconds)})</span>
            </span>
          </div>

          {/* Style & Layout Re-render Panel */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 space-y-3">
            <p className="text-xs font-semibold text-zinc-300">🎨 Subtitle & Layout Customizer</p>
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div>
                <label className="text-zinc-500">Subtitle Style</label>
                <select
                  value={subStyle}
                  onChange={(e) => setSubStyle(e.target.value)}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded px-2.5 py-1.5 text-white mt-1"
                >
                  <option value="hormozi">Alex Hormozi (Yellow Pop)</option>
                  <option value="beast">MrBeast (Bright White/Blue)</option>
                  <option value="neon">Cyberpunk Neon</option>
                </select>
              </div>
              <div>
                <label className="text-zinc-500">Reframe Layout</label>
                <select
                  value={layoutMode}
                  onChange={(e) => setLayoutMode(e.target.value)}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded px-2.5 py-1.5 text-white mt-1"
                >
                  <option value="center_crop">Center Crop (Speaker Track)</option>
                  <option value="split_screen">Split Screen (Dual Speaker)</option>
                  <option value="blur_background">Blurred Background Fit</option>
                </select>
              </div>
            </div>
            <button
              onClick={handleRerender}
              disabled={rerendering}
              className="w-full py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-semibold rounded-lg transition"
            >
              {rerendering ? "Re-rendering MP4…" : "Re-render with Presets"}
            </button>
          </div>

          {/* Virality rationale */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
            <p className="text-xs text-zinc-500 mb-1">Why it&apos;s viral</p>
            <p className="text-sm text-zinc-200">{clip.virality_rationale}</p>
          </div>

          {/* Hook */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
            <p className="text-xs text-zinc-500 mb-1">Opening hook</p>
            <p className="text-sm text-zinc-200 italic">&ldquo;{clip.hook_sentence}&rdquo;</p>
          </div>

          {/* Caption */}
          <div className="space-y-1">
            <label className="text-xs text-zinc-500">Social Caption</label>
            {editing ? (
              <textarea
                value={caption}
                onChange={(e) => setCaption(e.target.value)}
                rows={4}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-violet-500 resize-none"
              />
            ) : (
              <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
                <p className="text-sm text-zinc-200 whitespace-pre-wrap">{clip.suggested_caption}</p>
              </div>
            )}
          </div>

          {/* Hashtags */}
          <div className="flex flex-wrap gap-2">
            {clip.hashtags.map((h) => (
              <span key={h} className="text-xs bg-violet-500/10 border border-violet-500/20 text-violet-300 px-2.5 py-1 rounded-full">
                #{h.replace(/^#/, "")}
              </span>
            ))}
          </div>

          {/* Actions */}
          <div className="flex gap-3">
            <button
              onClick={handleCopy}
              className="flex-1 py-2.5 rounded-xl border border-zinc-700 text-zinc-300 text-sm hover:border-zinc-500 hover:text-white transition"
            >
              {copied ? "✓ Copied!" : "Copy Caption"}
            </button>
            {editing ? (
              <>
                <button
                  onClick={() => setEditing(false)}
                  className="py-2.5 px-4 rounded-xl border border-zinc-700 text-zinc-400 text-sm hover:border-zinc-500 transition"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSave}
                  disabled={saving}
                  className="flex-1 py-2.5 rounded-xl bg-violet-600 hover:bg-violet-500 text-white text-sm font-medium transition disabled:opacity-50"
                >
                  {saving ? "Saving…" : "Save"}
                </button>
              </>
            ) : (
              <button
                onClick={() => setEditing(true)}
                className="flex-1 py-2.5 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-white text-sm font-medium transition"
              >
                ✏ Edit
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
