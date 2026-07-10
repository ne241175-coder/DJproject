// バックエンドAPIの薄いラッパー群。

export async function fetchTracks() {
  const res = await fetch("/api/tracks");
  return res.json();
}

export async function fetchTrackDetail(trackId) {
  const res = await fetch(`/api/tracks/${trackId}`);
  return res.json();
}

export function trackAudioUrl(trackId) {
  return `/api/tracks/${trackId}/audio`;
}

export async function fetchNetwork() {
  const res = await fetch("/api/network");
  return res.json();
}

export async function fetchGenreTracks(genre, relativeToTrackId) {
  const url = `/api/genre/${encodeURIComponent(genre)}/tracks?relative_to=${relativeToTrackId}`;
  const res = await fetch(url);
  return res.json();
}

export async function fetchNearestTrack(fromTrackId, genre = null) {
  let url = `/api/nearest-track?from=${fromTrackId}`;
  if (genre) url += `&genre=${encodeURIComponent(genre)}`;
  const res = await fetch(url);
  return res.json();
}
