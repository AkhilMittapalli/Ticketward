const PLANNED_SCREENS = [
  { name: "Inbox and Ticket Workspace", phase: "P8" },
  { name: "Escalations (CSM and engineering briefs)", phase: "P8" },
  { name: "Ops and evaluation dashboard", phase: "P8" },
  { name: "Knowledge-base admin", phase: "P8" },
] as const;

export default function Home() {
  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-8 px-6 py-12">
      <div
        role="status"
        className="rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-500/40 dark:bg-amber-950/40 dark:text-amber-100"
      >
        <strong>Synthetic data only.</strong> This is a technical demonstration. No real customer
        data is used, and no reply is ever sent automatically: an agent approves every message.
      </div>

      <header className="flex flex-col gap-3">
        <h1 className="text-3xl font-semibold tracking-tight">Ticketward</h1>
        <p className="text-base leading-7 text-neutral-700 dark:text-neutral-300">
          Ticketward is a human-in-the-loop customer-support resolution copilot. It fine-tunes a
          compact language model for ticket triage, retrieves approved knowledge with citations,
          drafts agent-reviewed replies, and produces context-preserving escalation briefs.
        </p>
      </header>

      <section aria-labelledby="status-heading" className="flex flex-col gap-3">
        <h2 id="status-heading" className="text-lg font-medium">
          Status: foundation (P0)
        </h2>
        <p className="text-sm leading-6 text-neutral-700 dark:text-neutral-300">
          The API skeleton, data contracts and tooling are in place. The agent workspace arrives in
          later phases:
        </p>
        <ul className="list-disc pl-6 text-sm leading-6 text-neutral-700 dark:text-neutral-300">
          {PLANNED_SCREENS.map((screen) => (
            <li key={screen.name}>
              {screen.name} <span className="text-neutral-500">(planned in {screen.phase})</span>
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
