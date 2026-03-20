"use client";

import { usePathname } from "next/navigation";

import { Sidebar } from "@/components/sidebar";
import { ShieldChatPanel } from "@/components/shield-chat";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isLanding = pathname === "/";

  if (isLanding) {
    return <main className="min-h-screen bg-[#0a0a0a]">{children}</main>;
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="min-w-0 flex-1 overflow-y-auto bg-[#0d1117] p-4 sm:p-8">{children}</main>
      <ShieldChatPanel />
    </div>
  );
}
