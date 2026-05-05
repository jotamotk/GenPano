export default function Card({
  children,
  className = '',
  onClick,
  hover = false,
  style,
}) {
  const interactive = hover || onClick;
  const cursorStyles = onClick ? 'cursor-pointer' : '';

  return (
    <div
      className={`t-card ${interactive ? 't-card-interactive' : ''} ${cursorStyles} ${className}`.trim()}
      onClick={onClick}
      style={style}
    >
      {children}
    </div>
  );
}
