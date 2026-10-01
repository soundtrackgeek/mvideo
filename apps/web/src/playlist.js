// Move an existing track, or insert a new one before the target. IDs stay unique.
export function placeTrack(items, track, beforeId = null) {
  if (track.id === beforeId) return items;
  const next = items.filter((item) => item.id !== track.id);
  const index = beforeId
    ? next.findIndex((item) => item.id === beforeId)
    : next.length;
  next.splice(index < 0 ? next.length : index, 0, track);
  return next;
}
export function moveTrack(items, id, direction) {
  const index = items.findIndex((item) => item.id === id);
  const target = index + direction;
  if (index < 0 || target < 0 || target >= items.length) return items;
  const next = [...items];
  [next[index], next[target]] = [next[target], next[index]];
  return next;
}
export function draftKey(draft) {
  return JSON.stringify([
    draft.name,
    draft.description,
    draft.items.map((item) => item.id),
  ]);
}
