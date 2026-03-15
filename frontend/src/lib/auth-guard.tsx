"use client";

import { useEffect, type ReactNode } from "react";
import { useRouter, usePathname } from "next/navigation";
import { Loader2 } from "lucide-react";
import { useAuth } from "./auth-context";

const PUBLIC_PATHS = ["/login", "/about"];

export function AuthGuard({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  const isPublic = PUBLIC_PATHS.includes(pathname);

  useEffect(() => {
    if (loading) return;
    if (!user && !isPublic) {
      router.replace("/login");
    }
    if (user && isPublic) {
      router.replace("/");
    }
  }, [user, loading, isPublic, router]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Loader2
          size={28}
          className="animate-spin"
          style={{ color: "var(--accent-light)" }}
        />
      </div>
    );
  }

  if (!user && !isPublic) return null;
  if (user && isPublic) return null;

  return <>{children}</>;
}
