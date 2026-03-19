"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, ClipboardList, Eye, ShieldCheck, Users } from "lucide-react";

const navItems = [
  { href: "/dashboard", label: "Overview", icon: ShieldCheck },
  { href: "/live", label: "Live Feed", icon: Activity },
  { href: "/audit", label: "Audit Log", icon: ClipboardList },
  { href: "/agents", label: "Agents", icon: Users },
  { href: "/policies", label: "Policies", icon: Eye },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-64 border-r border-[#30363d] bg-[#0d1117] p-6">
      <div className="mb-10">
        <p className="text-xs uppercase tracking-widest text-[#8b949e]">AgentShield</p>
        <h1 className="mt-2 text-2xl font-semibold text-[#f0f6fc]">Dashboard</h1>
      </div>

      <nav className="space-y-2">
        {navItems.map(({ href, label, icon: Icon }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition ${
                active
                  ? "bg-[#1f6feb]/20 text-[#79c0ff]"
                  : "text-[#c9d1d9] hover:bg-[#161b22] hover:text-[#f0f6fc]"
              }`}
            >
              <Icon size={16} />
              {label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
