"use client";

import { use } from "react";
import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  Clock,
  MessageSquare,
  ChevronLeft,
  ShieldCheck,
  Wrench,
  Activity,
} from "lucide-react";

interface NavItem {
  label: string;
  href: string;
  icon: React.ReactNode;
}

export default function AnalysisLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const bundleId = typeof id === "string" ? id : null;
  const pathname = usePathname();

  if (!bundleId) return null;

  const basePath = `/analysis/${bundleId}`;

  const navItems: NavItem[] = [
    { label: "Dashboard", href: basePath, icon: <BarChart3 size={18} /> },
    {
      label: "Validation",
      href: `${basePath}/validation`,
      icon: <ShieldCheck size={18} />,
    },
    {
      label: "Troubleshoot",
      href: `${basePath}/troubleshoot`,
      icon: <Wrench size={18} />,
    },
    {
      label: "Timeline",
      href: `${basePath}/timeline`,
      icon: <Clock size={18} />,
    },
    {
      label: "Ask",
      href: `${basePath}/interview`,
      icon: <MessageSquare size={18} />,
    },
  ];

  return (
    <div className="relative z-10 flex min-h-screen">
      {/* Sidebar */}
      <aside className="sidebar fixed top-0 left-0 flex h-screen w-56 flex-shrink-0 flex-col overflow-hidden">
        <div className="p-4 pb-2">
          <Link
            href="/"
            className="flex items-center gap-1.5 text-xs transition-all hover:opacity-80"
            style={{ color: "var(--muted)" }}
          >
            <ChevronLeft size={12} />
            Back
          </Link>
        </div>

        {/* Logo area */}
        <div className="mb-8 flex items-center gap-3 px-5 pt-2">
          <div className="flex h-9 w-9 items-center justify-center">
            <Image
              src="/logo.svg"
              alt="Bundle analyzer logo"
              width={36}
              height={36}
              className="h-9 w-9 object-contain"
            />
          </div>
          <div className="flex flex-col">
            <span
              className="text-sm font-bold tracking-tight"
              style={{ color: "var(--foreground-bright)" }}
            >
              Bundle
            </span>
            <span
              className="text-[10px] font-medium tracking-wider uppercase"
              style={{ color: "var(--accent-light)", opacity: 0.8 }}
            >
              Analyzer
            </span>
          </div>
        </div>

        <nav className="flex flex-col gap-1 px-3">
          {navItems.map((item) => {
            const isActive =
              item.href === basePath
                ? pathname === basePath
                : pathname.startsWith(item.href);

            return (
              <Link
                key={item.href}
                href={item.href}
                className={`nav-item ${isActive ? "active" : ""}`}
              >
                {item.icon}
                {item.label}
              </Link>
            );
          })}
        </nav>

        {/* Status indicator at bottom */}
        <div className="mt-auto p-4 flex flex-col gap-3">
          <div
            className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs"
            style={{ background: "rgba(16, 185, 129, 0.08)", color: "var(--success)" }}
          >
            <Activity size={12} />
            <span className="font-medium">Connected</span>
          </div>
          <p
            className="truncate text-[10px] font-mono px-1"
            style={{ color: "var(--muted)", opacity: 0.4 }}
          >
            {bundleId.slice(0, 16)}
          </p>
        </div>
      </aside>

      {/* Main content */}
      <main className="ml-56 flex-1 overflow-auto p-6">{children}</main>
    </div>
  );
}
