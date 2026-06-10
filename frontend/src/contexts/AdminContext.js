import { createContext, useContext } from 'react';

// Shares the admin's resolved user/permissions (fetched once by AdminRoute and
// provided by AdminLayout) so the sidebar and panel don't each re-fetch
// /api/auth/me. Value: { user } where user is the full /auth/me user object.
export const AdminContext = createContext({ user: null });

export const useAdmin = () => useContext(AdminContext);
