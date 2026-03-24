// Abstract 3D particle sculpture — CSS-animated geometric art
// Evokes floating gold/bronze particles forming a cube-like structure

export default function ParticleArt() {
  return (
    <div className="relative w-full h-full flex items-center justify-center overflow-hidden select-none">
      {/* Background ambient glow */}
      <div className="absolute w-72 h-72 rounded-full opacity-20"
        style={{ background: 'radial-gradient(circle, #C9A96E 0%, transparent 70%)' }}
      />

      {/* Central geometric structure */}
      <div className="relative w-64 h-64 animate-float" style={{ animationDelay: '0s' }}>

        {/* Outer ring */}
        <svg
          viewBox="0 0 200 200"
          className="absolute inset-0 w-full h-full animate-rotate-slow"
          style={{ opacity: 0.35 }}
        >
          <ellipse
            cx="100" cy="100" rx="92" ry="40"
            fill="none" stroke="#8B6914" strokeWidth="1"
            strokeDasharray="4 6"
          />
          <ellipse
            cx="100" cy="100" rx="92" ry="40"
            fill="none" stroke="#C9A96E" strokeWidth="0.5"
            strokeDasharray="2 8"
            transform="rotate(60 100 100)"
          />
          <ellipse
            cx="100" cy="100" rx="92" ry="40"
            fill="none" stroke="#C9A96E" strokeWidth="0.5"
            strokeDasharray="2 8"
            transform="rotate(120 100 100)"
          />
        </svg>

        {/* Inner cube wireframe */}
        <svg
          viewBox="0 0 200 200"
          className="absolute inset-0 w-full h-full"
          style={{ opacity: 0.8 }}
        >
          {/* Cube faces - isometric projection */}
          {/* Top face */}
          <polygon
            points="100,50 140,70 100,90 60,70"
            fill="none" stroke="#C9A96E" strokeWidth="1.5"
          />
          {/* Left face */}
          <polygon
            points="60,70 100,90 100,140 60,120"
            fill="#8B6914" fillOpacity="0.12" stroke="#8B6914" strokeWidth="1.5"
          />
          {/* Right face */}
          <polygon
            points="100,90 140,70 140,120 100,140"
            fill="#C9A96E" fillOpacity="0.15" stroke="#C9A96E" strokeWidth="1.5"
          />
          {/* Inner depth lines */}
          <line x1="100" y1="50" x2="100" y2="90" stroke="#D4A853" strokeWidth="1" opacity="0.6" />
          <line x1="60" y1="70" x2="60" y2="120" stroke="#D4A853" strokeWidth="1" opacity="0.5" />
          <line x1="140" y1="70" x2="140" y2="120" stroke="#D4A853" strokeWidth="1" opacity="0.5" />
          <line x1="60" y1="120" x2="100" y2="140" stroke="#D4A853" strokeWidth="1" opacity="0.5" />
          <line x1="100" y1="140" x2="140" y2="120" stroke="#D4A853" strokeWidth="1" opacity="0.5" />
        </svg>

        {/* Orbiting particles */}
        <div className="absolute inset-0">
          {ORBIT_PARTICLES.map((p, i) => (
            <div
              key={i}
              className="absolute"
              style={{
                top: '50%',
                left: '50%',
                width: p.size,
                height: p.size,
                marginTop: -p.size / 2,
                marginLeft: -p.size / 2,
                animation: `orbit ${p.duration}s linear infinite ${p.reverse ? 'reverse' : 'normal'}`,
                animationDelay: `${p.delay}s`,
              }}
            >
              <div
                style={{
                  width: p.size,
                  height: p.size,
                  borderRadius: p.shape === 'circle' ? '50%' : '2px',
                  background: p.color,
                  opacity: p.opacity,
                  transform: `rotate(${p.rotation}deg)`,
                }}
              />
            </div>
          ))}
        </div>

        {/* Floating dot particles */}
        {FLOAT_PARTICLES.map((p, i) => (
          <div
            key={i}
            className="absolute rounded-full"
            style={{
              top: p.top,
              left: p.left,
              width: p.size,
              height: p.size,
              background: p.color,
              opacity: p.opacity,
              animation: `float ${p.duration}s ease-in-out infinite`,
              animationDelay: `${p.delay}s`,
            }}
          />
        ))}
      </div>

      {/* Bottom text */}
      <div className="absolute bottom-12 text-center">
        <p className="text-xs tracking-widest uppercase" style={{ color: '#8B6914', opacity: 0.6, letterSpacing: '0.2em' }}>
          GenPano
        </p>
        <p className="text-xs mt-1" style={{ color: '#A0845C', opacity: 0.5, fontSize: '10px' }}>
          GEO Monitoring
        </p>
      </div>
    </div>
  )
}

// Static particle data (avoids re-computation on render)
const ORBIT_PARTICLES = [
  { size: 6, duration: 10, delay: 0, reverse: false, color: '#C9A96E', opacity: 0.9, shape: 'circle', rotation: 0 },
  { size: 4, duration: 14, delay: -3, reverse: false, color: '#8B6914', opacity: 0.7, shape: 'square', rotation: 45 },
  { size: 5, duration: 8, delay: -5, reverse: true, color: '#D4A853', opacity: 0.8, shape: 'circle', rotation: 0 },
  { size: 3, duration: 16, delay: -2, reverse: true, color: '#5C4200', opacity: 0.5, shape: 'square', rotation: 30 },
  { size: 7, duration: 12, delay: -7, reverse: false, color: '#B8922D', opacity: 0.6, shape: 'circle', rotation: 0 },
]

const FLOAT_PARTICLES = [
  { top: '15%', left: '20%', size: 4, color: '#C9A96E', opacity: 0.6, duration: 7, delay: 0 },
  { top: '25%', left: '75%', size: 3, color: '#8B6914', opacity: 0.5, duration: 9, delay: -2 },
  { top: '70%', left: '15%', size: 5, color: '#D4A853', opacity: 0.7, duration: 6, delay: -4 },
  { top: '80%', left: '80%', size: 3, color: '#C9A96E', opacity: 0.4, duration: 8, delay: -1 },
  { top: '45%', left: '88%', size: 4, color: '#B8922D', opacity: 0.5, duration: 11, delay: -6 },
  { top: '60%', left: '8%', size: 2, color: '#8B6914', opacity: 0.6, duration: 5, delay: -3 },
  { top: '10%', left: '50%', size: 3, color: '#D4A853', opacity: 0.4, duration: 13, delay: -8 },
  { top: '85%', left: '45%', size: 5, color: '#C9A96E', opacity: 0.3, duration: 7, delay: -2 },
]
