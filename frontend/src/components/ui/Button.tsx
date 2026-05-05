export default function Button({
  children,
  variant = 'primary',
  size = 'md',
  onClick,
  disabled = false,
  className = '',
}) {
  const variantStyles = {
    primary: 't-btn-primary',
    accent: 't-btn-primary',
    secondary: 't-btn-secondary',
    outline: 't-btn-secondary',
    ghost: 't-btn-ghost',
  };

  const sizeStyles = {
    sm: 'py-1.5 px-3 text-xs',
    md: 'py-2 px-4 text-sm',
    lg: 'py-2.5 px-5 text-sm',
  };

  return (
    <button
      className={`${variantStyles[variant]} ${sizeStyles[size]} font-medium disabled:opacity-40 disabled:cursor-not-allowed ${className}`.trim()}
      onClick={onClick}
      disabled={disabled}
    >
      {children}
    </button>
  );
}
