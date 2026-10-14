import {
  BarChart3,
  LayoutDashboard,
  type LucideIcon,
  Moon,
  Sun,
  Users,
  Waypoints,
} from "lucide-react";
import { NavLink, Route, Routes } from "react-router-dom";

import { useTheme } from "@/hooks/useTheme";
import { cn } from "@/lib/utils";
import { Overview } from "@/pages/Overview";

interface NavItem {
  label: string;
  to: string;
  icon: LucideIcon;
  disabled?: boolean;
}

/** Navegação. Overview está ativa; as demais são placeholders de fases futuras. */
const NAV_ITEMS: NavItem[] = [
  { label: "Visão geral", to: "/", icon: LayoutDashboard },
  { label: "Receita", to: "/receita", icon: BarChart3, disabled: true },
  { label: "Segmentos RFM", to: "/rfm", icon: Waypoints, disabled: true },
  { label: "Clientes", to: "/clientes", icon: Users, disabled: true },
];

function Sidebar() {
  const { theme, toggleTheme } = useTheme();

  return (
    <aside className="flex w-60 shrink-0 flex-col bg-sidebar text-sidebar-foreground">
      <div className="flex items-center gap-2.5 px-5 py-6">
        <span className="flex h-8 w-8 items-center justify-center rounded-md bg-teal-500/20 text-sm font-bold text-teal-100">
          CI
        </span>
        <div className="leading-tight">
          <p className="text-sm font-semibold text-sidebar-foreground">
            Intelligence Lab
          </p>
          <p className="text-[11px] text-sidebar-foreground/60">
            Customer Analytics
          </p>
        </div>
      </div>

      <nav className="flex-1 space-y-1 px-3 py-2">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          if (item.disabled) {
            return (
              <span
                key={item.to}
                aria-disabled
                title="Em breve"
                className="flex cursor-not-allowed items-center gap-3 rounded-md px-3 py-2 text-sm text-sidebar-foreground/35"
              >
                <Icon className="h-4 w-4" aria-hidden />
                {item.label}
                <span className="ml-auto text-[10px] uppercase tracking-wide">
                  Em breve
                </span>
              </span>
            );
          }
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                  isActive
                    ? "bg-sidebar-accent font-medium text-sidebar-foreground"
                    : "text-sidebar-foreground/70 hover:bg-sidebar-accent/60 hover:text-sidebar-foreground",
                )
              }
            >
              <Icon className="h-4 w-4" aria-hidden />
              {item.label}
            </NavLink>
          );
        })}
      </nav>

      <div className="border-t border-sidebar-border p-3">
        <button
          type="button"
          onClick={toggleTheme}
          className="flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm text-sidebar-foreground/70 transition-colors hover:bg-sidebar-accent/60 hover:text-sidebar-foreground"
          aria-label={
            theme === "dark" ? "Mudar para tema claro" : "Mudar para tema escuro"
          }
        >
          {theme === "dark" ? (
            <Sun className="h-4 w-4" aria-hidden />
          ) : (
            <Moon className="h-4 w-4" aria-hidden />
          )}
          {theme === "dark" ? "Tema claro" : "Tema escuro"}
        </button>
      </div>
    </aside>
  );
}

export function App() {
  return (
    <div className="flex min-h-screen bg-background">
      <Sidebar />
      <main className="flex-1 overflow-x-hidden px-6 py-8 md:px-10">
        <Routes>
          <Route path="/" element={<Overview />} />
        </Routes>
      </main>
    </div>
  );
}
