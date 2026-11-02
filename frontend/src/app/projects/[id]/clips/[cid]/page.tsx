// Clipedics – Single clip editor (player + metadata + download)
"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { ViralityBadge } from "@/components/ViralityBadge";
import { fmtDuration, copyText } from "@/lib/utils";
import type { Clip } from "@/lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function ClipPage() {
  const { id: projectId, cid: clipId } = useParams<{ id: string; cid: string }>();
  const [clip, setClip] = useState<Clip | null>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [caption, setCaption] = useState("");
  const [title, setTitle] = useState("");
  const [copied, setCopied] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.clips.get(clipId).then((c) => {
      setClip(c);
      setCaption(c.suggested_caption);
      setTitle(c.title);
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
      <Link href={`/projects/${projectId}`} className="text-xs text-zinc-500 hover:text-zinc-300 transition">
        ← Back to Project
      </Link>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Left: Video player */}
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

          {/* Download button */}
          <a
            href={api.clips.downloadUrl(clip.id)}
            download
            className="w-full max-w-xs py-3 rounded-xl bg-gradient-to-r from-violet-600 to-fuchsia-600 text-white font-semibold text-center hover:opacity-90 transition"
          >
            ⬇ Download MP4
          </a>
        </div>

        {/* Right: Metadata */}
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

