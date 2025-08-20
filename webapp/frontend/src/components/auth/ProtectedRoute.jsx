
function ProtectedRoute({ children, requireAuth = false, fallback = null }) {
  // Authentication disabled - all routes are now public
  return children;
}

export default ProtectedRoute;
