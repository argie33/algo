function ProtectedRoute({ children, requireAuth = false, _fallback = null }) {
  // Authentication disabled - all routes are now public
  return children;
}

export default ProtectedRoute;
