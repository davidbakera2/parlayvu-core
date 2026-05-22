/** Extract YouTube video ID from watch or youtu.be URLs. */
export function youtubeId(url: string): string | null {
  try {
    const parsed = new URL(url);
    if (parsed.hostname.includes("youtu.be")) {
      return parsed.pathname.slice(1).split("/")[0] || null;
    }
    const v = parsed.searchParams.get("v");
    if (v) return v;
    const embed = parsed.pathname.match(/\/embed\/([^/?]+)/);
    return embed?.[1] ?? null;
  } catch {
    return null;
  }
}

export function youtubeThumbnail(id: string, quality: "hq" | "max" = "hq"): string {
  return quality === "max"
    ? `https://i.ytimg.com/vi/${id}/maxresdefault.jpg`
    : `https://i.ytimg.com/vi/${id}/hqdefault.jpg`;
}

export function youtubeEmbedUrl(id: string, startSeconds?: number): string {
  const params = new URLSearchParams({ rel: "0" });
  if (startSeconds != null && startSeconds > 0) {
    params.set("start", String(Math.floor(startSeconds)));
  }
  return `https://www.youtube-nocookie.com/embed/${id}?${params.toString()}`;
}
