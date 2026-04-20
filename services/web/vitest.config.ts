import path from 'node:path';

import { defineConfig } from 'vitest/config';

export default defineConfig({
  resolve: {
    alias: {
      '@': path.resolve(__dirname, '.')
    }
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./vitest.setup.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html', 'lcov'],
      reportsDirectory: './coverage',
      include: [
        'app/assessments/page.tsx',
        'app/admin/source-runs/page.tsx',
        'app/listing-clusters/page.tsx',
        'app/listings/page.tsx',
        'app/opportunities/page.tsx',
        'app/sites/page.tsx',
        'components/assessment-run-builder.tsx',
        'components/listing-run-panel.tsx',
        'components/site-scenario-editor.tsx',
        'lib/auth/session.ts',
        'lib/listing-source-console.ts'
      ],
      exclude: ['**/*.d.ts'],
      thresholds: {
        statements: 100,
        branches: 100,
        functions: 100,
        lines: 100
      }
    }
  }
});
