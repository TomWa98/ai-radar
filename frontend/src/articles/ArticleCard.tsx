import { fill } from "../i18n/dictionaries";
import { useLanguage } from "../i18n/language";
import type { Article } from "./api";
import { categoryLabel } from "./categories";
import { formatDateTime, plainText, safeHref } from "./format";

interface Props {
  article: Article;
  lead?: boolean;
}

/**
 * One article in the Editorial Grid. All article fields are untrusted and
 * rendered as text; only http(s) URLs become links.
 */
export function ArticleCard({ article, lead = false }: Props) {
  const { lang, t } = useLanguage();
  const titleId = `article-${article.id}-title`;
  const href = safeHref(article.url);
  const analysis = article.analysis;

  const published = formatDateTime(article.publishedAt, lang);
  const collected = formatDateTime(article.collectedAt, lang);
  const dateText = published
    ? published
    : collected
      ? fill(t.article.collected, { date: collected })
      : t.article.noDate;
  const dateTime = article.publishedAt ?? article.collectedAt;

  const excerpt = article.excerpt ? plainText(article.excerpt) : "";

  return (
    <article className={lead ? "card card--lead" : "card"} aria-labelledby={titleId}>
      <p className="card__meta">
        {analysis && (
          <span className="card__category">{categoryLabel(analysis.primaryCategory, t)}</span>
        )}
        <span className="card__source">{article.source}</span>
        <time dateTime={dateTime}>{dateText}</time>
      </p>

      <h2 className="card__title" id={titleId}>
        {href ? (
          <a href={href} target="_blank" rel="noopener noreferrer">
            {article.title}
            <span className="visually-hidden"> {t.article.opensInNewTab}</span>
          </a>
        ) : (
          article.title
        )}
      </h2>

      {analysis ? (
        <>
          <section className="card__summary" aria-label={t.article.aiSummary}>
            <p className="card__label">{t.article.aiSummary}</p>
            <p className="card__summary-text">{analysis.summary}</p>
          </section>
          <dl className="card__scores">
            <div>
              <dt>{t.article.relevance}</dt>
              <dd>{fill(t.article.score, { score: analysis.relevance })}</dd>
            </div>
            <div>
              <dt>{t.article.importance}</dt>
              <dd>{fill(t.article.score, { score: analysis.importance })}</dd>
            </div>
          </dl>
          <p className="card__reason">
            <span className="card__label">{t.article.reason}: </span>
            {analysis.relevanceReason}
          </p>
          {analysis.secondaryCategories.length > 0 && (
            <p className="card__secondary">
              {fill(t.article.also, {
                categories: analysis.secondaryCategories
                  .map((category) => categoryLabel(category, t))
                  .join(", "),
              })}
            </p>
          )}
          <p className="card__basis">
            {analysis.basis === "full_text" ? t.article.basisFullText : t.article.basisExcerpt}
          </p>
        </>
      ) : (
        <>
          <p className={`card__status card__status--${article.status}`}>
            {article.status === "analyzed" ? t.article.status.new : t.article.status[article.status]}
          </p>
          {excerpt && (
            <section className="card__excerpt" aria-label={t.article.excerpt}>
              <p className="card__label">{t.article.excerpt}</p>
              <p className="card__excerpt-text">{excerpt}</p>
            </section>
          )}
        </>
      )}
    </article>
  );
}
