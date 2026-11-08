import type { Article } from "../articles/api";
import { categoryLabel } from "../articles/categories";
import { formatDateTime } from "../articles/format";
import { fill } from "../i18n/dictionaries";
import { useLanguage } from "../i18n/language";

interface Props {
  article: Article;
  lead: boolean;
  highlighted: boolean;
}

/** One article on the wall: read-only, with all fields rendered as text. */
export function WallCard({ article, lead, highlighted }: Props) {
  const { lang, t } = useLanguage();
  const analysis = article.analysis;
  const titleId = `wall-article-${article.id}-title`;
  const date =
    formatDateTime(article.publishedAt, lang) ??
    formatDateTime(article.collectedAt, lang) ??
    t.article.noDate;
  const classes = ["wall-card"];
  if (lead) classes.push("wall-card--lead");
  if (highlighted) classes.push("wall-card--highlighted");

  return (
    <article className={classes.join(" ")} aria-labelledby={titleId}>
      <p className="wall-card__meta">
        {highlighted && <strong className="wall-card__badge">{t.wall.highlight}</strong>}
        {analysis && <span>{categoryLabel(analysis.primaryCategory, t)}</span>}
        <span>{article.source}</span>
        <span>{date}</span>
      </p>
      <h2 className="wall-card__title" id={titleId}>
        {article.title}
      </h2>
      {analysis && (
        <>
          <div className="wall-card__summary">
            <p>{analysis.summary}</p>
          </div>
          <dl className="wall-card__scores">
            <div>
              <dt>{t.article.relevance}</dt>
              <dd>{fill(t.article.score, { score: analysis.relevance })}</dd>
            </div>
            <div>
              <dt>{t.article.importance}</dt>
              <dd>{fill(t.article.score, { score: analysis.importance })}</dd>
            </div>
          </dl>
          <p className="wall-card__basis">
            {analysis.basis === "full_text" ? t.article.basisFullText : t.article.basisExcerpt}
          </p>
        </>
      )}
    </article>
  );
}
