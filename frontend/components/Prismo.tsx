// Prismo: PRISM's guide. A little prism crystal drawn in SVG (no image files).
// Its mood changes its face: idle, thinking, happy, sorry, waving.

export type Mood = "idle" | "thinking" | "happy" | "sorry" | "waving";

export default function Prismo({ mood = "idle", size = 96, className = "" }: { mood?: Mood; size?: number; className?: string }) {
  return (
    <svg
      viewBox="0 0 120 120"
      width={size}
      height={size}
      role="img"
      aria-label={`Prismo, looking ${mood}`}
      className={`${mood === "idle" || mood === "waving" ? "bob" : ""} ${className}`}
      style={{ overflow: "visible" }}
    >
      {/* Shadow: the same hard offset shadow every sticker has. */}
      <polygon points="64,14 116,108 12,108" fill="#000" />

      {/* Body: the triangle, plus a lilac facet on its right side. */}
      <polygon points="60,10 112,104 8,104" fill="var(--hot)" stroke="#000" strokeWidth="5" strokeLinejoin="round" />
      <polygon points="60,10 84,104 60,104" fill="var(--lilac)" stroke="#000" strokeWidth="4" strokeLinejoin="round" />

      {/* While thinking, a light beam splits into colours (it's a prism!). */}
      {mood === "thinking" && (
        <g className="prismo-anim" style={{ transformOrigin: "60px 60px", animation: "think 1.4s linear infinite" }}>
          <line x1="60" y1="60" x2="118" y2="40" stroke="var(--sun)" strokeWidth="5" strokeLinecap="round" />
          <line x1="60" y1="60" x2="118" y2="60" stroke="var(--baby)" strokeWidth="5" strokeLinecap="round" />
          <line x1="60" y1="60" x2="118" y2="80" stroke="var(--mint)" strokeWidth="5" strokeLinecap="round" />
        </g>
      )}

      {/* Eyes: open dots, happy arcs, or sorry slants. */}
      {mood === "happy" ? (
        <>
          <path d="M38 70 q6 -8 12 0" stroke="#000" strokeWidth="5" fill="none" strokeLinecap="round" />
          <path d="M62 70 q6 -8 12 0" stroke="#000" strokeWidth="5" fill="none" strokeLinecap="round" />
        </>
      ) : mood === "sorry" ? (
        <>
          <path d="M38 66 l12 4" stroke="#000" strokeWidth="5" strokeLinecap="round" />
          <path d="M74 66 l-12 4" stroke="#000" strokeWidth="5" strokeLinecap="round" />
        </>
      ) : (
        <>
          <circle cx="44" cy="70" r="5.5" fill="#000" />
          <circle cx="68" cy="70" r="5.5" fill="#000" />
          <circle cx="46" cy="68" r="1.8" fill="#fff" />
          <circle cx="70" cy="68" r="1.8" fill="#fff" />
        </>
      )}

      {/* Mouth: smile, or a small wobble when sorry. */}
      {mood === "sorry" ? (
        <path d="M48 88 q8 -6 16 0" stroke="#000" strokeWidth="4.5" fill="none" strokeLinecap="round" />
      ) : (
        <path d="M47 82 q9 9 18 0" stroke="#000" strokeWidth="4.5" fill="none" strokeLinecap="round" />
      )}

      {/* Cheeks. */}
      <circle cx="33" cy="80" r="5" fill="var(--sun)" />
      <circle cx="79" cy="80" r="5" fill="var(--sun)" />

      {/* A waving arm, only when greeting. */}
      {mood === "waving" && (
        <g className="prismo-anim" style={{ transformOrigin: "100px 78px", animation: "wave 1.2s var(--ease-out) infinite" }}>
          <path d="M100 78 q14 -10 16 -28" stroke="#000" strokeWidth="5" fill="none" strokeLinecap="round" />
          <circle cx="116" cy="48" r="7" fill="var(--hot)" stroke="#000" strokeWidth="4" />
        </g>
      )}
      <style>{`@keyframes wave { 50% { transform: rotate(-18deg); } } @media (prefers-reduced-motion: reduce) { .prismo-anim { animation: none !important; } }`}</style>
    </svg>
  );
}
