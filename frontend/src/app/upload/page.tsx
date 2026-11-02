// Clipedics – Upload page
import { UploadForm } from "@/components/UploadForm";

export const metadata = {
  title: "New Project — Clipedics",
};

export default function UploadPage() {
  return (
    <div className="max-w-xl mx-auto space-y-8">
      <div className="text-center space-y-2">
        <h1 className="text-3xl font-black text-white">New Project</h1>
        <p className="text-zinc-400">
          Paste a YouTube URL and let AI do the rest.
        </p>
      </div>
      <div className="bg-zinc-900/50 border border-zinc-800 rounded-2xl p-6">
        <UploadForm />
      </div>
    </div>
  );
}

