import { ApiError, apiGet } from "../api/client";
import type { Language } from "../i18n/dictionaries";

/** Types and client for `GET /api/articles` (backend #21/#22). */

export const CATEGORIES = ["Releases", "Features", "Security", "Use Cases", "Other"] as const;
export type Category = (typeof CATEGORIES)[number];
export type SortOrder = "recent" | "relevance";
export type ArticleStatus = "new" | "processing" | "analyzed" | "failed";
export type AnalysisBasis = "full_text" | "excerpt";

export interface Analysis {
  primaryCategory: Category;
  secondaryCategories: Category[];
  importance: number;
  relevance: number;
  basis: AnalysisBasis;
  summary: string;
  relevanceReason: string;
  analyzedAt: string;
}

/** One article. All text fields are untrusted and must be rendered as text. */
export interface Article {
  id: number;
  source: string;
  url: string;
  title: string;
  excerpt: string | null;
  publishedAt: string | null;
  collectedAt: string;
  status: ArticleStatus;
  analysis: Analysis | null;
}

export interface ArticlePage {
  items: Article[];
  total: number;
  nextSince: string;
}

export interface ArticleParams {
  lang: Language;
  q?: string;
  category?: Category;
  minRelevance?: number;
  publishedFrom?: string;
  publishedTo?: string;
  sort?: SortOrder;
  since?: string;
  limit: number;
  offset?: number;
}

type Json = Record<string, unknown>;

function isObject(value: unknown): value is Json {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isString(value: unknown): value is string {
  return typeof value === "string";
}

function isCategory(value: unknown): value is Category {
  return (CATEGORIES as readonly unknown[]).includes(value);
}

function isScore(value: unknown): value is number {
  return Number.isInteger(value) && (value as number) >= 1 && (value as number) <= 5;
}

function invalid(): never {
  throw new ApiError("Unexpected article response", 200);
}

function parseAnalysis(value: unknown): Analysis | null {
  if (value === null) {
    return null;
  }
  if (
    !isObject(value) ||
    !isCategory(value.primary_category) ||
    !Array.isArray(value.secondary_categories) ||
    !value.secondary_categories.every(isCategory) ||
    !isScore(value.importance) ||
    !isScore(value.relevance) ||
    (value.basis !== "full_text" && value.basis !== "excerpt") ||
    !isString(value.summary) ||
    !isString(value.relevance_reason) ||
    !isString(value.analyzed_at)
  ) {
    return invalid();
  }
  return {
    primaryCategory: value.primary_category,
    secondaryCategories: value.secondary_categories,
    importance: value.importance,
    relevance: value.relevance,
    basis: value.basis,
    summary: value.summary,
    relevanceReason: value.relevance_reason,
    analyzedAt: value.analyzed_at,
  };
}

const STATUSES: readonly unknown[] = ["new", "processing", "analyzed", "failed"];

function parseArticle(value: unknown): Article {
  if (
    !isObject(value) ||
    !Number.isInteger(value.id) ||
    !isString(value.source) ||
    !isString(value.url) ||
    !isString(value.title) ||
    !(value.excerpt === null || isString(value.excerpt)) ||
    !(value.published_at === null || isString(value.published_at)) ||
    !isString(value.collected_at) ||
    !STATUSES.includes(value.status)
  ) {
    return invalid();
  }
  return {
    id: value.id as number,
    source: value.source,
    url: value.url,
    title: value.title,
    excerpt: value.excerpt,
    publishedAt: value.published_at,
    collectedAt: value.collected_at,
    status: value.status as ArticleStatus,
    analysis: parseAnalysis(value.analysis),
  };
}

export function parseArticlePage(body: unknown): ArticlePage {
  if (
    !isObject(body) ||
    !Array.isArray(body.items) ||
    !Number.isInteger(body.total) ||
    !isString(body.next_since)
  ) {
    return invalid();
  }
  return {
    items: body.items.map(parseArticle),
    total: body.total as number,
    nextSince: body.next_since,
  };
}

export async function fetchArticles(
  params: ArticleParams,
  signal?: AbortSignal,
): Promise<ArticlePage> {
  const body = await apiGet("/api/articles", {
    signal,
    query: {
      lang: params.lang,
      q: params.q || undefined,
      category: params.category,
      min_relevance: params.minRelevance,
      published_from: params.publishedFrom,
      published_to: params.publishedTo,
      sort: params.sort,
      since: params.since,
      limit: params.limit,
      offset: params.offset || undefined,
    },
  });
  return parseArticlePage(body);
}
