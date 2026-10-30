/** API-shaped article fixtures (snake_case, as returned by the backend). */

let nextId = 1;

export interface ArticleFixture {
  id: number;
  source: string;
  url: string;
  title: string;
  excerpt: string | null;
  published_at: string | null;
  collected_at: string;
  status: string;
  analysis_error: string | null;
  has_full_text: boolean;
  analysis: Record<string, unknown> | null;
  feedback: string | null;
  changed_at: string;
}

export function analysis(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    primary_category: "Releases",
    secondary_categories: [],
    importance: 3,
    relevance: 4,
    topics: ["llm"],
    basis: "full_text",
    summary: "A new model was released.",
    relevance_reason: "Matches your interest in models.",
    analyzed_at: "2026-10-30T11:00:00Z",
    ...overrides,
  };
}

export function article(overrides: Partial<ArticleFixture> = {}): ArticleFixture {
  const id = overrides.id ?? nextId++;
  return {
    id,
    source: "Example Feed",
    url: `https://example.com/${id}`,
    title: `Headline ${id}`,
    excerpt: `<p>Excerpt ${id}</p>`,
    published_at: "2026-10-30T10:00:00Z",
    collected_at: "2026-10-30T10:05:00Z",
    status: "analyzed",
    analysis_error: null,
    has_full_text: true,
    analysis: analysis(),
    feedback: null,
    changed_at: "2026-10-30T11:00:00Z",
    ...overrides,
  };
}

export function page(items: ArticleFixture[], total = items.length) {
  return {
    items,
    total,
    limit: 25,
    offset: 0,
    next_since: "2026-10-30T12:00:00+00:00",
  };
}
