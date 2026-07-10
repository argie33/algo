import ErrorBoundary from "./ErrorBoundary";

/**
 * FormErrorBoundary — wrapper for form-specific error handling.
 * Uses the consolidated ErrorBoundary with variant="form" for minimal UI.
 *
 * @deprecated Use <ErrorBoundary variant="form"> directly instead.
 * This wrapper is maintained for backwards compatibility only.
 *
 * Example:
 *   <ErrorBoundary variant="form">
 *     <MyForm />
 *   </ErrorBoundary>
 */
export default function FormErrorBoundary({ children, onError, ...props }) {
  return (
    <ErrorBoundary variant="form" {...props}>
      {children}
    </ErrorBoundary>
  );
}
