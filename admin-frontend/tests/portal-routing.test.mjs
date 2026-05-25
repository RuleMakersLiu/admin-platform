import assert from 'node:assert/strict'
import { pathToFileURL } from 'node:url'
import { mkdtemp, readFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { build } from 'esbuild'

const storage = new Map()

globalThis.localStorage = {
  getItem: (key) => storage.get(key) ?? null,
  setItem: (key, value) => storage.set(key, String(value)),
  removeItem: (key) => storage.delete(key),
  clear: () => storage.clear(),
}

const tmp = await mkdtemp(path.join(tmpdir(), 'portal-routing-'))
const output = path.join(tmp, 'entry.mjs')

await build({
  stdin: {
    contents: "export { resolveLandingPath, saveLastPortalPath, getLastPortalPath } from './src/stores/auth.ts'\n",
    resolveDir: process.cwd(),
    sourcefile: 'portal-routing-entry.ts',
    loader: 'ts',
  },
  outfile: output,
  bundle: true,
  platform: 'node',
  format: 'esm',
  sourcemap: false,
  absWorkingDir: process.cwd(),
})

const { resolveLandingPath, saveLastPortalPath, getLastPortalPath } = await import(pathToFileURL(output).href)

const baseUser = {
  adminId: 42,
  username: 'tester',
  realName: 'Tester',
  tenantId: 7,
  permissions: [],
}

const userWith = (permissions, overrides = {}) => ({
  ...baseUser,
  permissions,
  ...overrides,
})

storage.clear()
assert.equal(resolveLandingPath(userWith(['portal:developer'])), '/project/access')
assert.equal(resolveLandingPath(userWith(['portal:product'])), '/pipeline/requirement')
assert.equal(resolveLandingPath(userWith(['flow:pipeline:match'])), '/pipeline/requirement')
assert.equal(resolveLandingPath(userWith(['project:create'])), '/project/access')
assert.equal(resolveLandingPath(userWith(['flow:pipeline:list'])), '/pipeline/development')

const multiRoleUser = userWith(['portal:developer', 'portal:product', 'flow:pipeline:list'])
storage.clear()
assert.equal(resolveLandingPath(multiRoleUser), '/portal-select')

saveLastPortalPath(multiRoleUser, '/project/access')
assert.equal(getLastPortalPath(multiRoleUser), '/project/access')
assert.equal(resolveLandingPath(multiRoleUser), '/project/access')

saveLastPortalPath(multiRoleUser, '/developer')
assert.equal(getLastPortalPath(multiRoleUser), '/project/access')

saveLastPortalPath(multiRoleUser, '/pipeline/requirement')
assert.equal(resolveLandingPath(multiRoleUser), '/pipeline/requirement')

saveLastPortalPath(multiRoleUser, '/pipeline/development')
assert.equal(resolveLandingPath(multiRoleUser), '/pipeline/development')

saveLastPortalPath(multiRoleUser, '/system/admin')
assert.equal(getLastPortalPath(multiRoleUser), null)
assert.equal(resolveLandingPath(multiRoleUser), '/portal-select')

assert.equal(resolveLandingPath(userWith(['portal:developer'], { isSuper: true })), '/portal-select')
assert.equal(resolveLandingPath(userWith([])), '/project/create')

const productPortalSource = await readFile('src/pages/portal/product/index.tsx', 'utf8')
assert.ok(productPortalSource.includes('pipelineApi.matchProjectSkill'))
assert.ok(!productPortalSource.includes('<Select'))
assert.ok(!productPortalSource.includes('generatorApi.getProjects'))
