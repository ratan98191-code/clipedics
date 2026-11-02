// Clipedics – Auth context + JWT storage
"use client";
import { createContext, useContext, useState, useEffect, ReactNode } from "react";

interface AuthUser {
  user_id: string;
  email: string;
  display_name: string;
  token: string;
}

interface AuthCtx {
  user: AuthUser | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, name?: string) => Promise<void>;
  logout: () => void;
  loading: boolean;
}

const AuthContext = createContext<AuthCtx | null>(null);
const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const TOKEN_KEY = "clipedics_token";

async function apiAuth(path: string, body: object) {
  const isLogin = path.includes("login");
  let res: Response;

  if (isLogin) {
    // OAuth2 form-encoded for /api/auth/login
    const form = new URLSearchParams();
    Object.entries(body).forEach(([k, v]) => form.append(k === "email" ? "username" : k, String(v)));
    res = await fetch(`${API}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: form,
    });
  } else {
    res = await fetch(`${API}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Auth failed");
  }
  return res.json();
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Restore from localStorage
    const raw = localStorage.getItem(TOKEN_KEY);
    if (raw) {
      try {
        setUser(JSON.parse(raw));
      } catch {
        localStorage.removeItem(TOKEN_KEY);
      }
    }
    setLoading(false);
  }, []);

  const persist = (u: AuthUser) => {
    setUser(u);
    localStorage.setItem(TOKEN_KEY, JSON.stringify(u));
  };

  const login = async (email: string, password: string) => {
    const data = await apiAuth("/api/auth/login", { email, password });
    persist({ user_id: data.user_id, email: data.email, display_name: data.display_name, token: data.access_token });
  };

  const register = async (email: string, password: string, name?: string) => {
    const data = await apiAuth("/api/auth/register", { email, password, display_name: name ?? "" });
    persist({ user_id: data.user_id, email: data.email, display_name: data.display_name, token: data.access_token });
  };

  const logout = () => {
    setUser(null);
    localStorage.removeItem(TOKEN_KEY);
  };

  return (
    <AuthContext.Provider value={{ user, login, register, logout, loading }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}

