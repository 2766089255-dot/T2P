// src/context/UserContext.tsx
'use client';

import React, { createContext, useContext, useState, ReactNode } from 'react';
import axios from 'axios';
import { API_BASE } from '@/lib/config';

interface UserContextType {
  userId: string;
  setUserId: (id: string) => void;
  login: () => Promise<boolean>;
  logout: () => void;
}

const UserContext = createContext<UserContextType>({
  userId: '',
  setUserId: () => {},
  login: async () => false,
  logout: () => {}
});

export const useUser = () => useContext(UserContext);

export const UserProvider = ({ children }: { children: ReactNode }) => {
  const [userId, setUserId] = useState(() =>
    typeof window === 'undefined' ? '' : localStorage.getItem('t2p_user_id') || ''
  );

  const login = async (): Promise<boolean> => {
    if (!userId.trim()) return false;
    try {
      await axios.post(`${API_BASE}/user/login`, { user_id: userId.trim() });
      localStorage.setItem('t2p_user_id', userId.trim());
      return true;
    } catch (e) {
      console.error('Login failed', e);
      return false;
    }
  };

  const logout = () => {
    setUserId('');
    localStorage.removeItem('t2p_user_id');
  };

  return (
    <UserContext.Provider value={{ userId, setUserId, login, logout }}>
      {children}
    </UserContext.Provider>
  );
};
