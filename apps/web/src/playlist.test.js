import test from "node:test";
import assert from "node:assert/strict";
import { placeTrack, moveTrack, draftKey } from "./playlist.js";
const tracks = ["a", "b", "c"].map((id) => ({ id }));
test("drag reorder inserts before target without duplicates", () => {
  assert.deepEqual(
    placeTrack(tracks, tracks[2], "a").map((v) => v.id),
    ["c", "a", "b"],
  );
  assert.deepEqual(
    placeTrack(tracks, tracks[0]).map((v) => v.id),
    ["b", "c", "a"],
  );
  assert.deepEqual(placeTrack(tracks, tracks[1], "b"), tracks);
  assert.deepEqual(
    placeTrack(tracks, { id: "d" }, "b").map((v) => v.id),
    ["a", "d", "b", "c"],
  );
});
test("keyboard moves preserve boundaries and input", () => {
  assert.deepEqual(moveTrack(tracks, "a", -1), tracks);
  assert.deepEqual(
    moveTrack(tracks, "b", 1).map((v) => v.id),
    ["a", "c", "b"],
  );
  assert.deepEqual(
    tracks.map((v) => v.id),
    ["a", "b", "c"],
  );
});
test("dirty detection tracks order and text, not rotating image tickets", () => {
  const draft = { name: "Mix", description: "Test", items: tracks };
  assert.equal(
    draftKey(draft),
    draftKey({
      ...draft,
      items: tracks.map((v) => ({ ...v, thumbnail: "new" })),
    }),
  );
  assert.notEqual(
    draftKey(draft),
    draftKey({ ...draft, items: [...tracks].reverse() }),
  );
});
