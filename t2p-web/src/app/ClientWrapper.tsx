// src/app/ClientWrapper.tsx
'use client';

import { UserProvider } from '@/context/UserContext';

export default function ClientWrapper({ children }: { children: React.ReactNode }) {
  return <UserProvider>{children}</UserProvider>;
}