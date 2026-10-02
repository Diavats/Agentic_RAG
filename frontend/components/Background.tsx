// Tiny outlined prisms drifting slowly up the pink background.
// They stay in the side margins (outside the 1152px content column) and only
// appear on wide screens, so they never drift through text.
// Pure CSS animation (runs off the main thread); switched off for reduced motion.
// Positions are fixed numbers, not random, so server and browser render the same thing.

const PRISMS = [
  { left: 1, size: 34, dur: 38, delay: -4, dx: 10, spin: 90, fill: "var(--sun)" },
  { left: 3, size: 22, dur: 46, delay: -20, dx: -8, spin: -120, fill: "var(--baby)" },
  { left: 2.5, size: 28, dur: 41, delay: -33, dx: 12, spin: 160, fill: "transparent" },
  { left: 96, size: 18, dur: 52, delay: -9, dx: -10, spin: 80, fill: "var(--mint)" },
  { left: 96.5, size: 30, dur: 44, delay: -27, dx: 8, spin: -90, fill: "transparent" },
  { left: 97.5, size: 24, dur: 49, delay: -14, dx: -12, spin: 140, fill: "var(--lilac)" },
  { left: 95.5, size: 32, dur: 40, delay: -36, dx: 6, spin: -150, fill: "var(--sun)" },
];

export default function Background() {
  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 hidden overflow-hidden xl:block">
      {PRISMS.map((p, i) => (
        <svg
          key={i}
          viewBox="0 0 40 40"
          width={p.size}
          height={p.size}
          className="drift absolute"
          style={{
            left: `${p.left}%`,
            top: "105vh",
            ["--dur" as string]: `${p.dur}s`,
            ["--delay" as string]: `${p.delay}s`,
            ["--dx" as string]: `${p.dx}px`,
            ["--spin" as string]: `${p.spin}deg`,
          }}
        >
          <polygon points="20,3 37,35 3,35" fill={p.fill} stroke="#000" strokeWidth="3" strokeLinejoin="round" />
        </svg>
      ))}
    </div>
  );
}
