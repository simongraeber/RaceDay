import assert from "node:assert/strict"
import { test } from "node:test"
import type { StatCard } from "../src/lib/api.js"
import { selectWeeklyCards } from "../src/lib/weeklyHighlights.js"

function randomFrom(seed: number): () => number {
  return () => {
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0
    return seed / 4294967296
  }
}

function card(key: string, names: string[] = [], artwork = true): StatCard {
  return {
    key, icon: "calendar", label: key, value: "3 days",
    detail: names[0] ?? "Team total",
    image_url: artwork ? `/art/${key}/${names[0] ?? "team"}` : null,
    candidates: names.map((name) => ({
      name, detail: name, image_url: artwork ? `/art/${key}/${name}` : null,
    })),
  }
}

test("tied winners vary on repeated visits with the same cached response", () => {
  const input = [card("consistency", ["Simon", "Jonathan"])]
  const random = randomFrom(42)
  const counts = new Map<string, number>()
  for (let visit = 0; visit < 2000; visit++) {
    const [winner] = selectWeeklyCards(input, 8, random)
    counts.set(winner.detail, (counts.get(winner.detail) ?? 0) + 1)
    assert.equal(winner.image_url, `/art/consistency/${winner.detail}`)
    assert.equal(winner.value, "3 days")
  }
  for (const name of ["Simon", "Jonathan"]) {
    assert.ok((counts.get(name) ?? 0) > 850)
    assert.ok((counts.get(name) ?? 0) < 1150)
  }
  assert.equal(input[0].detail, "Simon")
})

test("eight cards represent all four eligible runners, even without their artwork", () => {
  const input = [
    ...Array.from({ length: 6 }, (_, i) => card(`simon-${i}`, ["Simon"])),
    ...Array.from({ length: 6 }, (_, i) => card(`team-${i}`)),
    card("longest", ["Jonathan"]),
    card("endurance", ["Thomas"]),
    card("rhythm", ["Jonathan", "Theo"], false),
    card("outings", ["Simon", "Jonathan"]),
  ]
  for (let seed = 0; seed < 100; seed++) {
    const result = selectWeeklyCards(input, 8, randomFrom(seed))
    assert.equal(result.length, 8)
    assert.equal(new Set(result.map((item) => item.key)).size, 8)
    const names = new Set(result.filter((item) => item.candidates?.length).map((item) => item.detail))
    assert.deepEqual([...names].sort(), ["Jonathan", "Simon", "Theo", "Thomas"])
  }
})

test("ties favor a runner who has not already appeared", () => {
  const result = selectWeeklyCards([
    card("pace", ["Simon"]),
    card("outings", ["Simon", "Jonathan"]),
  ], 8, randomFrom(1))
  assert.equal(result.find((item) => item.key === "outings")?.detail, "Jonathan")
})

test("tied categories are not starved by a large pool of artwork cards", () => {
  const input = [
    card("pace", ["Simon"]),
    card("volume", ["Jonathan"]),
    card("endurance", ["Thomas"]),
    card("rhythm", ["Theo"]),
    ...Array.from({ length: 8 }, (_, i) => card(`team-${i}`)),
    card("outings", ["Simon", "Jonathan"], false),
    card("consistency", ["Simon", "Jonathan"], false),
  ]
  const winners = new Map<string, Set<string>>()
  const random = randomFrom(100)
  for (let visit = 0; visit < 200; visit++) {
    for (const selected of selectWeeklyCards(input, 8, random)) {
      if (!["outings", "consistency"].includes(selected.key)) continue
      const names = winners.get(selected.key) ?? new Set<string>()
      names.add(selected.detail)
      winners.set(selected.key, names)
    }
  }
  for (const key of ["outings", "consistency"]) {
    assert.deepEqual([...(winners.get(key) ?? [])].sort(), ["Jonathan", "Simon"])
  }
})

test("missing artwork never falls back to another runner's image", () => {
  const input = card("outings", ["Simon", "Jonathan"])
  input.candidates![1].image_url = null
  const [result] = selectWeeklyCards([input], 8, () => 0.99)
  assert.equal(result.detail, "Jonathan")
  assert.equal(result.image_url, null)
})

test("empty, small and older API responses remain supported", () => {
  assert.deepEqual(selectWeeklyCards([], 8), [])
  const legacy = card("team")
  delete legacy.candidates
  assert.deepEqual(selectWeeklyCards([legacy], 8), [legacy])
  assert.deepEqual(selectWeeklyCards([legacy], 0), [])
})

test("kudos keeps its detail prefix and the selected runner's art", () => {
  const input = card("kudos", ["Simon", "Jonathan"])
  for (const candidate of input.candidates!) candidate.detail = `Most loved: ${candidate.name}`
  const [result] = selectWeeklyCards([input], 8, () => 0.99)
  assert.equal(result.detail, "Most loved: Jonathan")
  assert.equal(result.image_url, "/art/kudos/Jonathan")
})
