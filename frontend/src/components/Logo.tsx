/**
 * The EvalNova mark.
 *
 * Traced from `EvalNova-icon-light.svg` in the brand kit, with one change:
 * the scan brackets and the document are drawn in `currentColor` instead of
 * a fixed navy, so a single component serves both themes. The brand kit ships
 * two files for exactly this reason, and two files drift - the light one gets
 * a fix the dark one does not.
 *
 * The beam and the pixel squares keep their brand colours. Cyan on navy is
 * 8.21:1 and cyan on white is a graphic element rather than text, so both
 * read correctly without being themed.
 */
export function Logo({ size = 28, className = "" }: { size?: number; className?: string }) {
  return (
    <svg
      viewBox="132 353 344 337"
      width={size}
      height={size}
      className={className}
      role="img"
      aria-label="EvalNova"
    >
      <defs>
        <linearGradient id="ev-fold" gradientUnits="userSpaceOnUse" x1="368" y1="409" x2="418" y2="459">
          <stop offset="0" stopColor="#0b6ffc" />
          <stop offset="1" stopColor="#0358e5" />
        </linearGradient>
      </defs>

      {/* The four scan brackets framing the page. */}
      <g fill="none" stroke="currentColor" strokeWidth="20" strokeLinecap="round" strokeLinejoin="round">
        <path d="M212 376L166 376L166 422" />
        <path d="M388 376L434 376L434 422" />
        <path d="M212 664L166 664L166 618" />
        <path d="M388 664L434 664L434 618" />
      </g>

      {/* The document, split by the beam: upper half with its folded corner... */}
      <path
        d="M233 423A14 14 0 0 1 247 409L368 409L418 459L418 511L233 511ZM260.5 444L335.5 444A5.5 5.5 0 0 1 341 449.5L341 449.5A5.5 5.5 0 0 1 335.5 455L260.5 455A5.5 5.5 0 0 1 255 449.5L255 449.5A5.5 5.5 0 0 1 260.5 444ZM260.5 476L355.5 476A5.5 5.5 0 0 1 361 481.5L361 481.5A5.5 5.5 0 0 1 355.5 487L260.5 487A5.5 5.5 0 0 1 255 481.5L255 481.5A5.5 5.5 0 0 1 260.5 476Z"
        fill="currentColor"
        fillRule="evenodd"
      />
      {/* ...and the lower half. */}
      <path
        d="M233 531L418 531L418 619A14 14 0 0 1 404 633L247 633A14 14 0 0 1 233 619ZM260.5 549L355.5 549A5.5 5.5 0 0 1 361 554.5L361 554.5A5.5 5.5 0 0 1 355.5 560L260.5 560A5.5 5.5 0 0 1 255 554.5L255 554.5A5.5 5.5 0 0 1 260.5 549ZM260.5 574L335.5 574A5.5 5.5 0 0 1 341 579.5L341 579.5A5.5 5.5 0 0 1 335.5 585L260.5 585A5.5 5.5 0 0 1 255 579.5L255 579.5A5.5 5.5 0 0 1 260.5 574ZM260.5 599L345.5 599A5.5 5.5 0 0 1 351 604.5L351 604.5A5.5 5.5 0 0 1 345.5 610L260.5 610A5.5 5.5 0 0 1 255 604.5L255 604.5A5.5 5.5 0 0 1 260.5 599Z"
        fill="currentColor"
        fillRule="evenodd"
      />
      <path d="M368 409L418 459L368 459Z" fill="url(#ev-fold)" />

      {/* The beam crossing the page, and the pixels it throws off. */}
      <path d="M155 516L413 516A5 5 0 0 1 418 521L418 521A5 5 0 0 1 413 526L155 526A5 5 0 0 1 150 521L150 521A5 5 0 0 1 155 516Z" fill="#06b9f9" />
      <path d="M433 516L461 516A5 5 0 0 1 466 521L466 521A5 5 0 0 1 461 526L433 526A5 5 0 0 1 428 521L428 521A5 5 0 0 1 433 516Z" fill="#06b9f9" />
      <path d="M428 482L440 482A4 4 0 0 1 444 486L444 498A4 4 0 0 1 440 502L428 502A4 4 0 0 1 424 498L424 486A4 4 0 0 1 428 482Z" fill="#1e6ef2" />
      <path d="M454.5 462L461.5 462A2.5 2.5 0 0 1 464 464.5L464 471.5A2.5 2.5 0 0 1 461.5 474L454.5 474A2.5 2.5 0 0 1 452 471.5L452 464.5A2.5 2.5 0 0 1 454.5 462Z" fill="#06b9f9" />
      <path d="M430.5 442L435.5 442A2.5 2.5 0 0 1 438 444.5L438 449.5A2.5 2.5 0 0 1 435.5 452L430.5 452A2.5 2.5 0 0 1 428 449.5L428 444.5A2.5 2.5 0 0 1 430.5 442Z" fill="#58a6f8" />
      <path d="M428 538L440 538A4 4 0 0 1 444 542L444 554A4 4 0 0 1 440 558L428 558A4 4 0 0 1 424 554L424 542A4 4 0 0 1 428 538Z" fill="#06b9f9" />
      <path d="M454.5 566L461.5 566A2.5 2.5 0 0 1 464 568.5L464 575.5A2.5 2.5 0 0 1 461.5 578L454.5 578A2.5 2.5 0 0 1 452 575.5L452 568.5A2.5 2.5 0 0 1 454.5 566Z" fill="#1e6ef2" />
      <path d="M430.5 588L435.5 588A2.5 2.5 0 0 1 438 590.5L438 595.5A2.5 2.5 0 0 1 435.5 598L430.5 598A2.5 2.5 0 0 1 428 595.5L428 590.5A2.5 2.5 0 0 1 430.5 588Z" fill="#58a6f8" />
    </svg>
  );
}
