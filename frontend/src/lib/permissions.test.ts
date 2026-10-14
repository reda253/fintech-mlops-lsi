import { can } from './permissions';

describe('matrice des droits', () => {
  it("l'ADMIN ne peut ni lire ni décider une revue", () => {
    expect(can('ADMIN', 'reviews:decide')).toBe(false);
    expect(can('ADMIN', 'reviews:read')).toBe(false);
  });

  it("l'ANALYSTE peut décider mais pas administrer", () => {
    expect(can('ANALYSTE', 'reviews:decide')).toBe(true);
    for (const p of ['users:manage', 'audit:read', 'monitoring:read', 'customers:write'] as const) {
      expect(can('ANALYSTE', p)).toBe(false);
    }
  });

  it("l'ADMIN gère clients, utilisateurs, audit et monitoring", () => {
    for (const p of ['customers:write', 'users:manage', 'audit:read', 'monitoring:read'] as const) {
      expect(can('ADMIN', p)).toBe(true);
    }
  });

  it('un visiteur anonyme n’a aucun droit', () => {
    expect(can(undefined, 'customers:read')).toBe(false);
  });
});
