/**
 * Compteurs affichés dans la sidebar et la topbar (revues ouvertes, notifications non lues).
 * Lot 1 : valeurs fictives des maquettes. Lot 5 : alimentés par /risk/reviews et le flux SSE.
 */
export interface ShellCounters {
  openReviews: number;
  unreadNotifications: number;
}

export function useShellCounters(): ShellCounters {
  return { openReviews: 38, unreadNotifications: 5 };
}
