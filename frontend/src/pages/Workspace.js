import { Navigate } from 'react-router-dom';

// /workspace was the old hub entry point. Canonical route is now /hub.
export default function Workspace() {
  return <Navigate to="/hub" replace />;
}
