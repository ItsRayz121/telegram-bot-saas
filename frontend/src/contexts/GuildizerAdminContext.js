import { createContext, useContext } from 'react';

// Shares the Guildizer admin's resolved user/role (fetched once by
// GuildizerAdminLayout) so the sidebar and panel sections don't each re-fetch
// /auth/me. Value: { me, role, can } where `me` is the guildizer /auth/me object,
// `role` is 'super' | 'support' | null, and `can(superOnly)` gates super-only items.
export const GuildizerAdminContext = createContext({ me: null, role: null, can: () => true });

export const useGuildizerAdmin = () => useContext(GuildizerAdminContext);
