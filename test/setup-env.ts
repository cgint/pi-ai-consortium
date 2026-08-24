// Test setup: runs before every test file (via vitest `setupFiles`).
//
// Deletes ambient CONSORTIUM_* environment variables so that module-load-time
// reads in src/config.ts (CONSORTIUM_EXECUTION_MODE, CONSORTIUM_REASONING) and
// call-time reads in index.ts (CONSORTIUM_MODEL) are deterministic regardless
// of the developer's shell environment.
//
// No restore: the vitest worker's process.env is disposable, and tests that
// need a specific value set process.env.CONSORTIUM_* explicitly in-test.

delete process.env.CONSORTIUM_MODEL;
delete process.env.CONSORTIUM_REASONING;
delete process.env.CONSORTIUM_EXECUTION_MODE;
