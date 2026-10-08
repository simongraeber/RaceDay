import type { StatCard } from "./api"

export function shuffled<T>(items: readonly T[], random = Math.random): T[] {
  const copy = [...items]
  for (let i = copy.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1))
    ;[copy[i], copy[j]] = [copy[j], copy[i]]
  }
  return copy
}

export function selectWeeklyCards(cards: readonly StatCard[], count: number, random = Math.random): StatCard[] {
  const pool = shuffled(cards, random)
  const appearances = new Map<string, number>()
  const selected: StatCard[] = []
  const featuredCount = (name: string) => appearances.get(name) ?? 0
  const priority = (card: StatCard) => card.candidates?.length
    ? Math.min(...card.candidates.map((candidate) => featuredCount(candidate.name)))
    : 1

  while (pool.length && selected.length < count) {
    const bestPriority = Math.min(...pool.map(priority))
    const eligible = pool.filter((card) => priority(card) === bestPriority)
    // Preserve flexible ties until sole winners have had a chance to introduce each runner.
    const fewestCandidates = bestPriority === 0
      ? Math.min(...eligible.map((card) => card.candidates?.length || 1))
      : null
    const card = eligible.find((card) => fewestCandidates === null || card.candidates?.length === fewestCandidates)!
    pool.splice(pool.indexOf(card), 1)
    const candidates = card.candidates ?? []
    if (!candidates.length) {
      selected.push(card)
      continue
    }
    const fewest = Math.min(...candidates.map((candidate) => featuredCount(candidate.name)))
    const tied = candidates.filter((candidate) => featuredCount(candidate.name) === fewest)
    const winner = tied[Math.floor(random() * tied.length)]
    appearances.set(winner.name, featuredCount(winner.name) + 1)
    selected.push({ ...card, detail: winner.detail, image_url: winner.image_url })
  }
  return shuffled(selected, random)
}
