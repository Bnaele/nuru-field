// Loading placeholders. No React import: the JSX runtime is automatic, so
// importing it only produced an unused-binding lint warning.

export const Skeleton = ({ className = '' }) => (
  <div className={`skeleton ${className}`} />
);

export const CardSkeleton = () => (
  <div className="skeleton-card">
    <Skeleton className="skeleton-title" />
    <Skeleton className="skeleton-line full" />
    <Skeleton className="skeleton-line medium" />
    <Skeleton className="skeleton-button" />
  </div>
);
