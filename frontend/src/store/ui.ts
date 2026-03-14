import { create } from "zustand";

interface UiState {
  selectedFindingId: string | null;
  sidebarCollapsed: boolean;
  severityFilter: string[];

  selectFinding: (id: string | null) => void;
  toggleSidebar: () => void;
  setSeverityFilter: (filter: string[]) => void;
  toggleSeverity: (severity: string) => void;
}

export const useUiStore = create<UiState>((set) => ({
  selectedFindingId: null,
  sidebarCollapsed: false,
  severityFilter: [],

  selectFinding: (id) => set({ selectedFindingId: id }),

  toggleSidebar: () =>
    set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),

  setSeverityFilter: (filter) => set({ severityFilter: filter }),

  toggleSeverity: (severity) =>
    set((s) => ({
      severityFilter: s.severityFilter.includes(severity)
        ? s.severityFilter.filter((f) => f !== severity)
        : [...s.severityFilter, severity],
    })),
}));
