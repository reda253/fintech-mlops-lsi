import { ApiError } from '@/api/errors';
import { createDemoAuthService } from './authService';

describe('demoAuthService', () => {
  const service = createDemoAuthService(0);

  it('connecte un ADMIN et un ANALYSTE sans jeton', async () => {
    const admin = await service.login({ username: 'admin1', password: 'demo' });
    expect(admin.role).toBe('ADMIN');
    const analyste = await service.login({ username: 'analyste1', password: 'demo' });
    expect(analyste.role).toBe('ANALYSTE');
    expect(JSON.stringify(admin)).not.toMatch(/password|token/i);
  });

  it('rejette de mauvais identifiants avec une 401', async () => {
    await expect(service.login({ username: 'analyste1', password: 'x' })).rejects.toMatchObject({
      status: 401,
    });
    await expect(service.login({ username: 'inconnu', password: 'demo' })).rejects.toBeInstanceOf(ApiError);
  });

  it('restaure puis efface la session', async () => {
    await service.login({ username: 'admin1', password: 'demo' });
    expect((await service.restore())?.username).toBe('admin1');
    await service.logout();
    expect(await service.restore()).toBeNull();
  });

  it('ne stocke que l’identifiant public (jamais le mot de passe)', async () => {
    await service.login({ username: 'admin1', password: 'demo' });
    const stored = Object.values(window.sessionStorage).join('|');
    expect(stored).toBe('admin1');
    expect(window.localStorage.length).toBe(0);
  });
});
