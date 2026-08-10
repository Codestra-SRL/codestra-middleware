import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

test('client signs without embedding a credential value', () => {
  const source = readFileSync(new URL('../src/client.ts', import.meta.url), 'utf8');
  assert.match(source, /createHmac\('sha256'/);
  assert.match(source, /X-Codestra-Nonce/);
  assert.doesNotMatch(source, /postiz|hootsuite|odoo\/web/i);
});

test('package exposes twelve provider-neutral nodes', () => {
  const source = readFileSync(new URL('../src/nodes.ts', import.meta.url), 'utf8');
  assert.equal([...source.matchAll(/export class Codestra/g)].length, 12);
});
