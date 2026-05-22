import { useMemo, useState } from "react";
import type { OutlookArchiveItem } from "@/lib/outlook-survey-data";
import { youtubeEmbedUrl, youtubeId, youtubeThumbnail } from "@/lib/youtube";

function pdfEmbedUrl(pdfUrl: string): string {
  return `https://docs.google.com/viewer?url=${encodeURIComponent(pdfUrl)}&embedded=true`;
}

type MediaKey = string;

type VideoEntry = { key: MediaKey; label: string; url: string; id: string; startSeconds?: number };

function buildVideos(item: OutlookArchiveItem): VideoEntry[] {
  const entries: VideoEntry[] = [];
  if (item.video) {
    const id = youtubeId(item.video);
    if (id) {
      entries.push({
        key: `${item.year}-main`,
        label: item.year === 2026 ? "Survey results (starts 12:12)" : "Presentation video",
        url: item.video,
        id,
        startSeconds: item.videoStartSeconds,
      });
    }
  }
  if (item.extra?.video) {
    const id = youtubeId(item.extra.video);
    if (id) {
      entries.push({
        key: `${item.year}-extra`,
        label: item.extra.label,
        url: item.extra.video,
        id,
      });
    }
  }
  return entries;
}

function SlideThumbnail({ year, label, active }: { year: number; label: string; active: boolean }) {
  return (
    <div
      className={`relative aspect-video w-full overflow-hidden rounded-xl border transition-all ${
        active ? "border-amber-400 ring-2 ring-amber-400/40" : "border-zinc-600 group-hover:border-amber-400/50"
      }`}
    >
      <div className="absolute inset-0 bg-gradient-to-br from-zinc-800 via-zinc-900 to-amber-950/80" />
      <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 p-4 text-center">
        <span className="flex h-14 w-14 items-center justify-center rounded-lg bg-red-600/90 text-xs font-bold uppercase tracking-wide text-white shadow-lg">
          PDF
        </span>
        <span className="text-2xl font-bold text-white/90">{year}</span>
        <span className="text-xs font-medium uppercase tracking-wider text-amber-200/80">Slide deck</span>
      </div>
      <span className="sr-only">{label} slides</span>
    </div>
  );
}

function VideoThumbnail({ id, label, active }: { id: string; label: string; active: boolean }) {
  return (
    <div
      className={`relative aspect-video w-full overflow-hidden rounded-xl border transition-all ${
        active ? "border-amber-400 ring-2 ring-amber-400/40" : "border-zinc-600 group-hover:border-amber-400/50"
      }`}
    >
      <img src={youtubeThumbnail(id)} alt="" className="absolute inset-0 h-full w-full object-cover" />
      <div className="absolute inset-0 bg-black/30 group-hover:bg-black/20 transition-colors" />
      <div className="absolute inset-0 flex items-center justify-center">
        <span
          className="flex h-14 w-14 items-center justify-center rounded-full bg-red-600 text-white shadow-lg group-hover:scale-105 transition-transform"
          aria-hidden
        >
          <svg className="h-6 w-6 ml-1" viewBox="0 0 24 24" fill="currentColor">
            <path d="M8 5v14l11-7z" />
          </svg>
        </span>
      </div>
      <p className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/90 to-transparent px-3 py-2 text-xs font-medium text-zinc-200 line-clamp-2">
        {label}
      </p>
    </div>
  );
}

type Props = { items: OutlookArchiveItem[] };

export default function OutlookPresentationArchive({ items }: Props) {
  const [activeMedia, setActiveMedia] = useState<{
    key: MediaKey;
    type: "video" | "slides";
    title: string;
    embedSrc: string;
    externalHref?: string;
  } | null>(null);

  const defaultMedia = useMemo(() => {
    for (const item of items) {
      const videos = buildVideos(item);
      if (videos[0]) {
        return {
          key: videos[0].key,
          type: "video" as const,
          title: `${item.year} — ${videos[0].label}`,
          embedSrc: youtubeEmbedUrl(videos[0].id, videos[0].startSeconds),
        };
      }
      if (item.slides) {
        return {
          key: `${item.year}-slides`,
          type: "slides" as const,
          title: `${item.year} — ${item.label}`,
          embedSrc: pdfEmbedUrl(item.slides),
          externalHref: item.slides,
        };
      }
    }
    return null;
  }, [items]);

  const displayed = activeMedia ?? defaultMedia;

  function selectVideo(entry: VideoEntry, year: number) {
    setActiveMedia({
      key: entry.key,
      type: "video",
      title: `${year} — ${entry.label}`,
      embedSrc: youtubeEmbedUrl(entry.id, entry.startSeconds),
      externalHref: entry.url,
    });
  }

  function selectSlides(item: OutlookArchiveItem) {
    if (!item.slides) return;
    setActiveMedia({
      key: `${item.year}-slides`,
      type: "slides",
      title: `${item.year} — Slide deck`,
      embedSrc: pdfEmbedUrl(item.slides),
      externalHref: item.slides,
    });
  }

  return (
    <div className="space-y-10">
      {displayed ? (
        <div className="rounded-2xl border border-zinc-700/80 bg-zinc-900/80 overflow-hidden shadow-xl shadow-black/20">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 px-4 py-3 border-b border-zinc-800 bg-zinc-950/60">
            <p className="text-sm font-medium text-zinc-200">{displayed.title}</p>
            {displayed.externalHref ? (
              <a
                href={displayed.externalHref}
                target="_blank"
                rel="noreferrer"
                className="text-xs font-semibold text-amber-400 hover:text-amber-300 shrink-0"
              >
                Open in new tab ↗
              </a>
            ) : null}
          </div>
          <div className="relative w-full bg-black aspect-video min-h-[280px] md:min-h-[420px]">
            <iframe
              key={displayed.key}
              src={displayed.embedSrc}
              title={displayed.title}
              className="absolute inset-0 h-full w-full"
              allow={
                displayed.type === "video"
                  ? "accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                  : undefined
              }
              allowFullScreen={displayed.type === "video"}
            />
          </div>
        </div>
      ) : null}

      <div className="space-y-8">
        {items.map((item) => {
          const videos = buildVideos(item);
          const hasSlides = Boolean(item.slides);
          if (videos.length === 0 && !hasSlides) return null;

          return (
            <article key={item.year} className="rounded-2xl border border-zinc-700/70 bg-zinc-900/60 p-5 md:p-6">
              <h3 className="text-lg font-semibold text-zinc-100 mb-4">{item.label}</h3>
              <div
                className={`grid gap-4 ${
                  videos.length + (hasSlides ? 1 : 0) > 1 ? "sm:grid-cols-2 lg:grid-cols-3" : "max-w-md"
                }`}
              >
                {videos.map((entry) => (
                  <button
                    key={entry.key}
                    type="button"
                    onClick={() => selectVideo(entry, item.year)}
                    className="group text-left rounded-xl focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-400"
                  >
                    <VideoThumbnail id={entry.id} label={entry.label} active={displayed?.key === entry.key} />
                  </button>
                ))}
                {hasSlides && item.slides ? (
                  <button
                    type="button"
                    onClick={() => selectSlides(item)}
                    className="group text-left rounded-xl focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-400"
                  >
                    <SlideThumbnail
                      year={item.year}
                      label={item.label}
                      active={displayed?.key === `${item.year}-slides`}
                    />
                  </button>
                ) : null}
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}
