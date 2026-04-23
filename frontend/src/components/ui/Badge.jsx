export default function Badge({
  children,
  variant = 'default',
  size = 'md',
  className = '',
}) {
  const variantStyles = {
    default: 't-badge-default',
    secondary: 't-badge-default',
    blue: 't-badge-accent',
    accent: 't-badge-accent',
    green: 't-badge-success',
    red: 't-badge-danger',
    coral: 't-badge-danger',
    orange: 't-badge-warning',
    gold: 't-badge-warning',
    purple: 't-badge-accent',
    info: 't-badge-info',
  };

  const sizeStyles = {
    xs: 'text-[10px] px-1 py-0.5',
    sm: 'text-[11px] px-1.5 py-0.5',
    md: 'text-xs px-2.5 py-1',
  };

  return (
    <span className={`t-badge ${variantStyles[variant] || 't-badge-default'} ${sizeStyles[size]} ${className}`.trim()}>
      {children}
    </span>
  );
}
