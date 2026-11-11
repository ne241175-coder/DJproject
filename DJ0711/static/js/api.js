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

export async function fetchGenreSections(genre, relativeToSectionId) {
  const url = `/api/genre/${encodeURIComponent(genre)}/sections?relative_to=${relativeToSectionId}`;
  const res = await fetch(url);
  return res.json();
}

export async function fetchNearestSection(fromSectionId, genre = null) {
  let url = `/api/nearest-section?from=${fromSectionId}`;
  if (genre) url += `&genre=${encodeURIComponent(genre)}`;
  const res = await fetch(url);
  return res.json();
}

export async function fetchHarmonicAdjustment(sectionId, relativeToTrackId) {
  const url = `/api/sections/${sectionId}/harmonic-adjustment?relative_to_track=${relativeToTrackId}`;
  const res = await fetch(url);
  return res.json();
}

export function matchedAudioUrl(sectionId, relativeToTrackId) {
  return `/api/sections/${sectionId}/matched-audio?relative_to_track=${relativeToTrackId}`;
}

export async function updateTrackGenre(trackId, genres) {
  const res = await fetch(`/api/tracks/${trackId}/genre`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ genres }),
  });
  return res.json();
}

export async function updateTrackTempo(trackId, bpm) {
  const res = await fetch(`/api/tracks/${trackId}/tempo`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ bpm }),
  });
  return res.json();
}

export async function deleteTrack(trackId) {
  const res = await fetch(`/api/tracks/${trackId}`, { method: "DELETE" });
  return res.json();
}
