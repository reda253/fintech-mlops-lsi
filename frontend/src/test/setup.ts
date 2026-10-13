import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { transferableAbortController } from 'node:util';
import { afterEach } from 'vitest';

/**
 * Node ≥ 22/24 : l'environnement jsdom remplace AbortController/AbortSignal par ceux de jsdom,
 * alors que `new Request(url, { signal })` (undici, utilisé par React Router lors de chaque
 * navigation) exige l'AbortSignal natif de Node → « Expected signal to be an instance of AbortSignal ».
 * On restaure ici les classes natives (accessibles via util.transferableAbortController).
 * Réglage de test uniquement : aucun impact sur l'application.
 */
const nativeController = transferableAbortController();
globalThis.AbortController = nativeController.constructor as typeof AbortController;
globalThis.AbortSignal = nativeController.signal.constructor as typeof AbortSignal;

afterEach(() => {
  cleanup();
  window.sessionStorage.clear();
});
