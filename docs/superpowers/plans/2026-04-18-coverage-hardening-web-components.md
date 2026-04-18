# Coverage Hardening for Web Component Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Raise deterministic coverage for the owned assessment run and scenario editor frontend components without changing runtime behavior.

**Architecture:** Keep the existing component code intact and focus on tests that exercise every meaningful branch, including success, failure, empty-state, and default-value paths. Use mocked API functions and fixed time control so the tests stay deterministic and only assert user-visible behavior.

**Tech Stack:** Next.js client components, React Testing Library, Vitest, mocked `next/navigation`, mocked `@/lib/landintel-api`.

---

### Task 1: Assessment run builder coverage

**Files:**
- Modify: `services/web/components/__tests__/assessment-run-builder.test.tsx`

- [ ] **Step 1: Add a deterministic default-date test**

```tsx
it('uses today when no as-of date is provided', () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date('2026-04-18T12:00:00.000Z'));

  render(<AssessmentRunBuilder initialScenarioId="scenario-1" initialSiteId="site-1" />);

  expect(screen.getByLabelText('As-of date')).toHaveValue('2026-04-18');

  vi.useRealTimers();
});
```

- [ ] **Step 2: Add an API-failure branch test**

```tsx
it('shows a failure message when assessment creation does not return an item', async () => {
  vi.mocked(createAssessment).mockResolvedValue({
    apiAvailable: true,
    item: null
  });

  render(
    <AssessmentRunBuilder
      initialAsOfDate="2026-04-15"
      initialScenarioId="scenario-1"
      initialSiteId="site-1"
    />
  );

  fireEvent.click(screen.getByRole('button', { name: 'Create assessment' }));

  await waitFor(() => {
    expect(screen.getByText('Assessment creation failed. Check that the scenario is current and confirmed.')).toBeInTheDocument();
  });
  expect(push).not.toHaveBeenCalled();
  expect(refresh).not.toHaveBeenCalled();
});
```

### Task 2: Site scenario editor coverage

**Files:**
- Modify: `services/web/components/__tests__/site-scenario-editor.test.tsx`

- [ ] **Step 1: Add status-tone coverage through rendered badges**

```tsx
it('renders scenario badges for success, warning, and danger statuses', () => {
  const scenarios = [
    { ...scenarioSummary, id: 'confirmed', status: 'ANALYST_CONFIRMED' },
    { ...scenarioSummary, id: 'review', status: 'ANALYST_REQUIRED' },
    { ...scenarioSummary, id: 'rejected', status: 'REJECTED' }
  ];

  render(<SiteScenarioEditor initialScenarios={scenarios} site={site} />);

  expect(screen.getByText('ANALYST_CONFIRMED')).toBeInTheDocument();
  expect(screen.getByText('ANALYST_REQUIRED')).toBeInTheDocument();
  expect(screen.getByText('REJECTED')).toBeInTheDocument();
});
```

- [ ] **Step 2: Add empty-state and selection-guard coverage**

```tsx
it('shows the empty state and blocks confirm without a selected scenario', async () => {
  render(<SiteScenarioEditor initialScenarios={[]} site={site} />);

  expect(screen.getByText('No scenarios are stored for this site yet.')).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'Confirm scenario' }));

  expect(screen.getByText('Select a scenario before confirming or rejecting.')).toBeInTheDocument();
  expect(confirmScenario).not.toHaveBeenCalled();
});
```

- [ ] **Step 3: Add suggestion failure coverage**

```tsx
it('reports when suggestion refresh returns no payload', async () => {
  vi.mocked(suggestSiteScenarios).mockResolvedValue({
    apiAvailable: true,
    item: null
  });

  render(<SiteScenarioEditor initialScenarios={[scenarioSummary]} site={site} />);

  fireEvent.click(screen.getByRole('button', { name: 'Refresh suggestions' }));

  await waitFor(() => {
    expect(screen.getByText('Scenario suggestion did not return an API payload.')).toBeInTheDocument();
  });
});
```

- [ ] **Step 4: Add confirm-reject branch coverage**

```tsx
it('submits a reject action and preserves the rejection message', async () => {
  vi.mocked(confirmScenario).mockResolvedValue({
    apiAvailable: true,
    item: { ...scenarioDetail, status: 'REJECTED' }
  });

  render(<SiteScenarioEditor initialScenarios={[scenarioSummary]} site={site} />);

  fireEvent.click(screen.getByRole('button', { name: 'Reject scenario' }));

  await waitFor(() => {
    expect(confirmScenario).toHaveBeenCalledWith(
      'scenario-1',
      expect.objectContaining({
        action: 'REJECT',
        units_assumed: undefined,
        route_assumed: undefined,
        height_band_assumed: undefined,
        net_developable_area_pct: undefined,
        parking_assumption: undefined,
        affordable_housing_assumption: undefined,
        access_assumption: undefined
      })
    );
  });
  expect(screen.getByText('Scenario rejected and removed from the current headline set.')).toBeInTheDocument();
});
```

- [ ] **Step 5: Add scenario-detail failure coverage**

```tsx
it('shows a detail-unavailable message when opening a scenario fails', async () => {
  vi.mocked(getScenario).mockResolvedValue({
    apiAvailable: true,
    item: null
  });

  render(<SiteScenarioEditor initialScenarios={[scenarioSummary]} site={site} />);

  fireEvent.click(screen.getByRole('button', { name: 'Open' }));

  await waitFor(() => {
    expect(screen.getByText('Scenario detail is unavailable.')).toBeInTheDocument();
  });
});
```

- [ ] **Step 6: Run the targeted Vitest slice**

Run: `cd services/web && npx vitest run components/__tests__/assessment-run-builder.test.tsx components/__tests__/site-scenario-editor.test.tsx --coverage`
Expected: all tests pass and the two owned component files reach full meaningful coverage with deterministic assertions.

