/** Rôles humains. SIMULATEUR est un compte technique : aucun espace React. */
export type Role = 'ADMIN' | 'ANALYSTE';

export interface AuthUser {
  username: string;
  displayName: string;
  initials: string;
  role: Role;
}

export interface Credentials {
  username: string;
  password: string;
}
